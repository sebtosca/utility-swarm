import json
import shutil
import subprocess
from pathlib import Path

from cjs.observability.logging import get_logger

logger = get_logger(__name__)

FFMPEG_AVAILABLE = bool(shutil.which("ffmpeg"))
FFPROBE_AVAILABLE = bool(shutil.which("ffprobe"))


class FFmpegError(Exception):
    """Raised when an ffmpeg or ffprobe operation fails."""


def get_video_duration_sec(path: Path) -> float:
    """Return video duration in seconds using ffprobe."""
    if not FFPROBE_AVAILABLE:
        raise FFmpegError("ffprobe not found on PATH")
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise FFmpegError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    return float(json.loads(result.stdout)["format"]["duration"])


def extract_audio(video_path: Path, out_path: Path) -> None:
    """Extract mono 16kHz WAV audio from a video file."""
    if not FFMPEG_AVAILABLE:
        raise FFmpegError("ffmpeg not found on PATH")
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise FFmpegError(f"Audio extraction failed for {video_path}: {result.stderr.strip()}")


def extract_frames_ffmpeg(video_path: Path, num_frames: int, out_dir: Path) -> list[Path]:
    """Extract num_frames evenly-spaced frames as PNG images using ffmpeg."""
    if not FFMPEG_AVAILABLE:
        raise FFmpegError("ffmpeg not found on PATH")
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = get_video_duration_sec(video_path)
    fps = num_frames / max(duration, 1.0)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps={fps:.4f}",
            str(out_dir / "frame_%04d.png"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise FFmpegError(f"Frame extraction failed for {video_path}: {result.stderr.strip()}")
    frames = sorted(out_dir.glob("frame_*.png"))
    logger.info("ffmpeg_frames_extracted", video=str(video_path), count=len(frames))
    return frames
