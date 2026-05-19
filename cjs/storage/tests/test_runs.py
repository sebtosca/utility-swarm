import re
from pathlib import Path

from cjs.config import Settings
from cjs.storage.runs import (
    copy_brief_into_run,
    copy_videos_into_run,
    create_run_folder,
    generate_run_id,
    get_runs_dir,
)

# --- generate_run_id ---


# Check that generate_run_id returns a string.
def test_generate_run_id_returns_string() -> None:
    assert isinstance(generate_run_id(), str)


# Check that run ID matches YYYYMMDD_HHMMSS_xxxx (timestamp + 4 hex chars).
def test_generate_run_id_format() -> None:
    run_id = generate_run_id()
    pattern = r"^\d{8}_\d{6}_[a-f0-9]{4}$"
    assert re.match(pattern, run_id), f"Expected format YYYYMMDD_HHMMSS_xxxx, got {run_id!r}"


# --- get_runs_dir ---


# Check that get_runs_dir returns a Path.
def test_get_runs_dir_returns_path(tmp_path: Path) -> None:
    config = Settings()
    config.run.out_dir = str(tmp_path / "runs")
    result = get_runs_dir(config)
    assert isinstance(result, Path)
    assert result.is_absolute()
    assert result.is_dir()


# Check that get_runs_dir returns resolved path from config.run.out_dir.
def test_get_runs_dir_uses_config_out_dir() -> None:
    config = Settings()
    config.run.out_dir = "./my_runs"
    result = get_runs_dir(config)
    assert result.name == "my_runs"
    assert result.is_absolute()


# --- create_run_folder ---


# Check that create_run_folder returns a path that exists and is a directory.
def test_create_run_folder_returns_existing_dir(tmp_path: Path) -> None:
    config = Settings()
    config.run.out_dir = str(tmp_path)
    run_folder = create_run_folder(config)
    assert run_folder.exists()
    assert run_folder.is_dir()


# Check that create_run_folder creates required subdirs.
def test_create_run_folder_creates_subdirs(tmp_path: Path) -> None:
    config = Settings()
    config.run.out_dir = str(tmp_path)
    run_folder = create_run_folder(config)
    expected = ["input", "brief", "dossiers", "judgements", "results"]
    for name in expected:
        subdir = run_folder / name
        assert subdir.is_dir(), f"Missing subdir: {name}"
    assert (run_folder / "input" / "videos").is_dir()


# --- copy_brief_into_run ---


# Check that copy_brief_into_run returns destination path under run_folder/input/.
def test_copy_brief_into_run_returns_dest_path(tmp_path: Path) -> None:
    brief = tmp_path / "brief.pdf"
    brief.write_text("fake pdf content")
    run_folder = tmp_path / "run"
    run_folder.mkdir()
    dest = copy_brief_into_run(brief, run_folder)
    assert dest == run_folder / "input" / "brief.pdf"


# Check that copy_brief_into_run copies file content.
def test_copy_brief_into_run_copies_content(tmp_path: Path) -> None:
    brief = tmp_path / "brief.pdf"
    content = "fake pdf content"
    brief.write_text(content)
    run_folder = tmp_path / "run"
    run_folder.mkdir()
    copy_brief_into_run(brief, run_folder)
    dest = run_folder / "input" / "brief.pdf"
    assert dest.read_text() == content


# --- copy_videos_into_run ---


# Check that copy_videos_into_run returns one path per input.
def test_copy_videos_into_run_returns_one_per_input(tmp_path: Path) -> None:
    v1 = tmp_path / "a.mp4"
    v2 = tmp_path / "b.mp4"
    v1.write_text("video1")
    v2.write_text("video2")
    run_folder = tmp_path / "run"
    run_folder.mkdir()
    dests = copy_videos_into_run([v1, v2], run_folder)
    assert len(dests) == 2
    assert dests[0].name == "a.mp4"
    assert dests[1].name == "b.mp4"


# Check that copy_videos_into_run puts files under run_folder/input/videos/.
def test_copy_videos_into_run_puts_in_videos_dir(tmp_path: Path) -> None:
    v1 = tmp_path / "ad.mp4"
    v1.write_text("video")
    run_folder = tmp_path / "run"
    run_folder.mkdir()
    dests = copy_videos_into_run([v1], run_folder)
    assert len(dests) == 1
    assert dests[0].parent == run_folder / "input" / "videos"
    assert dests[0].read_text() == "video"
