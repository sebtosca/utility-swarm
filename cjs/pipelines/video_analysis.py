from pathlib import Path

from cjs.config import Settings
from cjs.constants import ALLOWED_EXTENSIONS
from cjs.observability.logging import get_logger
from cjs.router.model_router import ModelRouter
from cjs.schemas.video_dossier import VideoDossier, VideoVisualAnalysis
from cjs.utils.ffmpeg import FFmpegError, extract_audio, get_video_duration_sec
from cjs.utils.frames import extract_keyframes
from cjs.utils.whisper_stt import transcribe

logger = get_logger(__name__)

VIDEO_EXTENSIONS = tuple(ext for ext in ALLOWED_EXTENSIONS if ext != ".pdf")

_VISION_SYSTEM = """\
You are a visual advertising analyst examining keyframes from a video advertisement.
The frames are provided in chronological order. Use them alongside the transcript to produce
a structured breakdown that other jury agents will use to evaluate the creative.

Analyse what you see across all frames and produce:
- hook_summary: what the ad does in the first 3 seconds to earn attention
- scenes: an ordered breakdown — what happens, at roughly what timestamp
- pacing: your overall assessment (fast / medium / slow)
- logo_first_appearance_sec: estimate when the brand logo first appears (use frame order + total
  duration to estimate). Set to null if no logo is visible.
- cta_detected: whether a call-to-action is visible or strongly implied
- cta_text: the exact CTA text if visible, otherwise null

Be specific. Cite what you actually see in the frames — not generic advertising language.\
"""


class VideoAnalysisError(Exception):
    """Raised when video analysis fails at any step."""


def _validate_video(video_path: Path, config: Settings) -> None:
    if video_path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise VideoAnalysisError(
            f"Unsupported format '{video_path.suffix}'. Allowed: {VIDEO_EXTENSIONS}"
        )
    size_mb = video_path.stat().st_size / (1024 * 1024)
    if size_mb > config.limits.max_file_mb:
        raise VideoAnalysisError(
            f"{video_path.name} is {size_mb:.1f} MB — exceeds limit of {config.limits.max_file_mb} MB"
        )


def _get_duration(video_path: Path, config: Settings) -> float:
    try:
        duration = get_video_duration_sec(video_path)
    except FFmpegError as exc:
        logger.warning("duration_check_skipped", video=str(video_path), reason=str(exc))
        return 0.0
    if duration > config.limits.max_duration_sec:
        raise VideoAnalysisError(
            f"{video_path.name} is {duration:.1f}s — exceeds limit of {config.limits.max_duration_sec}s"
        )
    return duration


def _extract_transcript(video_path: Path, work_dir: Path) -> str:
    audio_path = work_dir / "audio.wav"
    try:
        extract_audio(video_path, audio_path)
    except FFmpegError as exc:
        logger.warning("audio_extraction_skipped", video=str(video_path), reason=str(exc))
        return ""
    return transcribe(audio_path)


def _run_vision_analysis(
    frame_paths: list[Path],
    duration_sec: float,
    transcript: str,
    router: ModelRouter,
    video_path: Path,
) -> VideoVisualAnalysis:
    transcript_block = f"Transcript:\n{transcript}" if transcript else "Transcript: (not available)"
    user = (
        f"Analyse this ad:\n"
        f"- Total duration: {duration_sec:.1f} seconds\n"
        f"- Frames provided: {len(frame_paths)} (chronological order)\n"
        f"- {transcript_block}\n"
    )
    result = router.call_structured(
        system=_VISION_SYSTEM,
        user=user,
        node="video_analysis",
        schema=VideoVisualAnalysis.model_json_schema(),
        schema_name="VideoVisualAnalysis",
        images=frame_paths if frame_paths else None,
    )
    try:
        return VideoVisualAnalysis.model_validate_json(result.content)
    except Exception as exc:
        raise VideoAnalysisError(
            f"Failed to parse vision analysis for {video_path.name}: {exc}"
        ) from exc


def analyze_video(
    video_path: Path,
    run_folder: Path,
    router: ModelRouter,
    config: Settings,
) -> VideoDossier:
    """Full video analysis pipeline: validate → audio → transcribe → frames → vision → dossier."""
    logger.info("video_analysis_start", video=str(video_path))

    _validate_video(video_path, config)

    work_dir = run_folder / "dossiers" / video_path.stem
    work_dir.mkdir(parents=True, exist_ok=True)

    duration_sec = _get_duration(video_path, config)
    transcript = _extract_transcript(video_path, work_dir)

    frames_dir = work_dir / "frames"
    frame_paths = extract_keyframes(video_path, config.limits.max_frames, frames_dir)

    visual = _run_vision_analysis(frame_paths, duration_sec, transcript, router, video_path)

    dossier = VideoDossier(
        video_path=str(video_path),
        duration_sec=duration_sec,
        transcript=transcript,
        hook_summary=visual.hook_summary,
        scenes=visual.scenes,
        pacing=visual.pacing,
        logo_first_appearance_sec=visual.logo_first_appearance_sec,
        cta_detected=visual.cta_detected,
        cta_text=visual.cta_text,
        frames_analyzed=len(frame_paths),
        metadata={"frames_dir": str(frames_dir)},
    )

    dossier_path = run_folder / "dossiers" / f"{video_path.stem}_dossier.json"
    dossier_path.write_text(dossier.model_dump_json(indent=2))
    logger.info("video_analysis_complete", video=str(video_path), dossier=str(dossier_path))

    return dossier
