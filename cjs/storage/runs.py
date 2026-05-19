import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

from cjs.config import Settings


# Generate a unique run ID: YYYYMMDD_HHMMSS plus 4 random hex chars.
def generate_run_id() -> str:
    """Generate a unique run ID: YYYYMMDD_HHMMSS + 4 random hex chars (UTC)."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = secrets.token_hex(2)  # 4 hex chars
    return f"{timestamp}_{suffix}"


# Return resolved path to the runs output directory from config.
def get_runs_dir(config: Settings) -> Path:
    """Return the resolved runs directory, creating it if necessary."""
    runs_dir = Path(config.run.out_dir).expanduser().resolve()
    runs_dir.mkdir(parents=True, exist_ok=True)
    return runs_dir


# Create a new run directory with input/, brief/, dossiers/, judgements/, results/; return its path.
def create_run_folder(config: Settings) -> Path:
    """
    Create a new run directory with the expected subfolder structure
    and return the run folder path.
    """
    base_dir = get_runs_dir(config)
    run_id = generate_run_id()
    run_folder = base_dir / run_id

    # Run folder should be unique → fail if it already exists
    run_folder.mkdir(parents=True, exist_ok=False)

    subdirs = [
        "input",
        "input/videos",
        "brief",
        "dossiers",
        "judgements",
        "results",
    ]

    for subdir in subdirs:
        (run_folder / subdir).mkdir(parents=True, exist_ok=True)

    return run_folder


# Copy brief file to run_folder/input/; return destination path.
def copy_brief_into_run(brief_path: Path, run_folder: Path) -> Path:
    """
    Copy the creative brief into run_folder/input and return destination path.
    Prevents overwriting by renaming if needed.
    """
    if not brief_path.exists():
        raise FileNotFoundError(f"Brief not found: {brief_path}")

    dest_dir = run_folder / "input"
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / brief_path.name

    # Avoid overwriting existing file
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{brief_path.stem}_{counter}{brief_path.suffix}"
        counter += 1

    shutil.copy2(brief_path, dest)
    return dest


# Copy video files to run_folder/input/videos and return resolved destination list.
def copy_videos_into_run(video_paths: list[Path], run_folder: Path) -> list[Path]:
    """
    Copy video files into run_folder/input/videos and return destination paths.
    Ensures filenames do not collide.
    """
    videos_dir = run_folder / "input" / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    destinations: list[Path] = []

    for path in video_paths:
        if not path.exists():
            raise FileNotFoundError(f"Video not found: {path}")

        dest = videos_dir / path.name

        # Avoid overwriting if filename already exists
        counter = 1
        while dest.exists():
            dest = videos_dir / f"{path.stem}_{counter}{path.suffix}"
            counter += 1

        shutil.copy2(path, dest)
        destinations.append(dest)

    return destinations
