from pathlib import Path

from cjs.observability.logging import get_logger
from cjs.utils.ffmpeg import FFmpegError, extract_frames_ffmpeg

logger = get_logger(__name__)


def extract_keyframes(video_path: Path, num_frames: int, out_dir: Path) -> list[Path]:
    """Extract num_frames evenly-spaced keyframes. Tries OpenCV first, falls back to ffmpeg."""
    try:
        return _extract_with_opencv(video_path, num_frames, out_dir)
    except ImportError:
        logger.warning("opencv_not_installed", fallback="ffmpeg", video=str(video_path))
    except Exception as exc:
        logger.warning("opencv_extraction_failed", error=str(exc), fallback="ffmpeg")

    try:
        return extract_frames_ffmpeg(video_path, num_frames, out_dir)
    except FFmpegError as exc:
        logger.warning("ffmpeg_extraction_failed", error=str(exc))
        return []


def _extract_with_opencv(video_path: Path, num_frames: int, out_dir: Path) -> list[Path]:
    import cv2  # type: ignore[import-untyped]

    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    indices = [int(i * total_frames / num_frames) for i in range(num_frames)]
    frame_paths: list[Path] = []

    for i, idx in enumerate(indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue
        out_path = out_dir / f"frame_{i:04d}.png"
        cv2.imwrite(str(out_path), frame)
        frame_paths.append(out_path)

    cap.release()
    logger.info("opencv_frames_extracted", video=str(video_path), count=len(frame_paths))
    return frame_paths
