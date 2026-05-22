import json
import os
import re
from pathlib import Path

from typer.testing import CliRunner

from cjs.cli import app
from cjs.config import ConfigError, ModelSettings, Settings

runner = CliRunner(env={"NO_COLOR": "1"})

_ANSI = re.compile(r"\x1b\[[0-9;]*[mGKH]")


def _plain(text: str) -> str:
    """Strip ANSI escape codes. Newer Rich emits bold codes even with NO_COLOR."""
    return _ANSI.sub("", text)


def _combined_output(result) -> str:
    """Return user-facing CLI output across Click versions with different stderr capture."""
    try:
        stderr = result.stderr
    except (AttributeError, ValueError):
        stderr = ""
    return result.stdout + stderr


# Verify `cjs config get models.text` returns the configured text model.
def test_config_get_models_text(monkeypatch) -> None:
    config = Settings(models=ModelSettings(text="test-model", vision="vision-model"))
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)

    result = runner.invoke(app, ["config", "get", "models.text"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "test-model"


# Verify JSON mode emits machine-readable value for `config get models.text`.
def test_config_get_models_text_json(monkeypatch) -> None:
    config = Settings(models=ModelSettings(text="test-model", vision="vision-model"))
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)

    result = runner.invoke(app, ["--json", "config", "get", "models.text"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == "test-model"


# Verify `--json config get` returns the full config object.
def test_config_get_full_json(monkeypatch) -> None:
    config = Settings(models=ModelSettings(text="text-model", vision="vision-model"))
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)

    result = runner.invoke(app, ["--json", "config", "get"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["provider"] == config.provider
    assert payload["models"]["text"] == "text-model"
    assert payload["models"]["vision"] == "vision-model"


# Verify `config set` coerces limits values to int before saving.
def test_config_set_limits_max_videos_coerces_int(monkeypatch) -> None:
    config = Settings()
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)

    saved: dict[str, Settings] = {}

    def fake_save_config(new_config: Settings) -> None:
        saved["config"] = new_config

    monkeypatch.setattr("cjs.cli.save_config", fake_save_config)

    result = runner.invoke(app, ["config", "set", "limits.max_videos", "5"])

    assert result.exit_code == 0
    assert "config" in saved
    assert saved["config"].limits.max_videos == 5


# Verify `config set` fails when a limits value is not an integer.
def test_config_set_limits_max_videos_invalid_int(monkeypatch) -> None:
    config = Settings()
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)

    result = runner.invoke(app, ["config", "set", "limits.max_videos", "abc"])

    assert result.exit_code != 0


# Verify `runs --json` returns an empty list when there are no run directories.
def test_runs_json_empty_list(monkeypatch, tmp_path: Path) -> None:
    config = Settings()
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)
    monkeypatch.setattr("cjs.cli.get_runs_dir", lambda _config: tmp_path)

    result = runner.invoke(app, ["--json", "runs"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


# Verify `runs --json` returns a machine-readable error when config is missing.
def test_runs_json_missing_config(monkeypatch) -> None:
    monkeypatch.setattr("cjs.cli.load_config", lambda: None)

    result = runner.invoke(app, ["--json", "runs"])

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "Run `cjs configure` first." in payload["error"]


# Verify `runs --json` sorts run directories by newest mtime first.
def test_runs_json_sorted_newest_first(monkeypatch, tmp_path: Path) -> None:
    config = Settings()
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)
    monkeypatch.setattr("cjs.cli.get_runs_dir", lambda _config: tmp_path)

    older = tmp_path / "older-run"
    newer = tmp_path / "newer-run"
    older.mkdir()
    newer.mkdir()
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_800_000_000, 1_800_000_000))

    result = runner.invoke(app, ["--json", "runs"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [item["run_id"] for item in payload] == ["newer-run", "older-run"]


# Verify `models --json` returns text/vision model names.
def test_models_json_output(monkeypatch) -> None:
    config = Settings(models=ModelSettings(text="text-model", vision="vision-model"))
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)

    result = runner.invoke(app, ["--json", "models"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"text": "text-model", "vision": "vision-model"}


# Verify `models --json` returns a machine-readable error when config is missing.
def test_models_json_missing_config(monkeypatch) -> None:
    monkeypatch.setattr("cjs.cli.load_config", lambda: None)

    result = runner.invoke(app, ["--json", "models"])

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "Run `cjs configure` first." in payload["error"]


# Verify `report --json` returns an error payload when run folder is missing.
def test_report_json_missing_run(monkeypatch, tmp_path: Path) -> None:
    config = Settings()
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)
    monkeypatch.setattr("cjs.cli.get_runs_dir", lambda _config: tmp_path)

    result = runner.invoke(app, ["--json", "report", "missing-run"])

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["run_id"] == "missing-run"
    assert "Run not found" in payload["error"]


# Verify `report --json` returns a machine-readable error when config is missing.
def test_report_json_missing_config(monkeypatch) -> None:
    monkeypatch.setattr("cjs.cli.load_config", lambda: None)

    result = runner.invoke(app, ["--json", "report", "any-run"])

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "Run `cjs configure` first." in payload["error"]


# Verify `report --json` returns exists=true when results/report.md is present.
def test_report_json_existing_report(monkeypatch, tmp_path: Path) -> None:
    config = Settings()
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)
    monkeypatch.setattr("cjs.cli.get_runs_dir", lambda _config: tmp_path)

    run_id = "run-123"
    report_path = tmp_path / run_id / "results" / "report.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Report")

    result = runner.invoke(app, ["--json", "report", run_id])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["run_id"] == run_id
    assert payload["exists"] is True
    assert payload["report_path"] == str(report_path)


# Verify explicit configure options trigger non-interactive save behavior.
def test_configure_with_provider_saves_without_prompts(monkeypatch) -> None:
    monkeypatch.setattr("cjs.cli.load_config", lambda: Settings())
    monkeypatch.setattr("cjs.cli.get_config_path", lambda: Path("/tmp/test-config.yaml"))

    saved: dict[str, Settings] = {}

    def fake_save_config(new_config: Settings) -> None:
        saved["config"] = new_config

    monkeypatch.setattr("cjs.cli.save_config", fake_save_config)

    result = runner.invoke(app, ["configure", "--provider", "anthropic"])

    assert result.exit_code == 0
    assert "config" in saved
    assert saved["config"].provider == "anthropic"


# Verify configure --non-interactive saves immediately without prompt input.
def test_configure_non_interactive_saves_without_prompts(monkeypatch) -> None:
    monkeypatch.setattr("cjs.cli.load_config", lambda: Settings())
    monkeypatch.setattr("cjs.cli.get_config_path", lambda: Path("/tmp/test-config.yaml"))

    saved: dict[str, Settings] = {}

    def fake_save_config(new_config: Settings) -> None:
        saved["config"] = new_config

    monkeypatch.setattr("cjs.cli.save_config", fake_save_config)

    result = runner.invoke(app, ["configure", "--non-interactive"])

    assert result.exit_code == 0
    assert "config" in saved


# Verify configure respects global --json and emits machine-readable output.
def test_configure_json_mode_emits_json(monkeypatch) -> None:
    monkeypatch.setattr("cjs.cli.load_config", lambda: Settings())
    monkeypatch.setattr("cjs.cli.get_config_path", lambda: Path("/tmp/test-config.yaml"))
    monkeypatch.setattr("cjs.cli.save_config", lambda _config: None)

    result = runner.invoke(app, ["--json", "configure", "--non-interactive"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {"ok": True, "config_path": "/tmp/test-config.yaml"}


# Verify configure explicit override path emits machine-readable success in --json mode.
def test_configure_json_mode_with_override_emits_json(monkeypatch) -> None:
    monkeypatch.setattr("cjs.cli.load_config", lambda: Settings())
    monkeypatch.setattr("cjs.cli.get_config_path", lambda: Path("/tmp/test-config.yaml"))
    monkeypatch.setattr("cjs.cli.save_config", lambda _config: None)

    result = runner.invoke(app, ["--json", "configure", "--provider", "anthropic"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {"ok": True, "config_path": "/tmp/test-config.yaml"}


# Verify configure emits machine-readable errors in --json mode.
def test_configure_json_mode_emits_json_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "cjs.cli.load_config", lambda: (_ for _ in ()).throw(ConfigError("bad config"))
    )

    result = runner.invoke(app, ["--json", "configure", "--non-interactive"])

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"] == "bad config"


# Verify `run --json` returns the expected machine-readable payload shape.
def test_run_json_output_shape(monkeypatch, tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from cjs.schemas.brand_rules import BrandRules
    from cjs.schemas.brief import Brief
    from cjs.schemas.rubric import Rubric

    config = Settings()
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)
    monkeypatch.setattr("cjs.cli.extract_brief_raw", lambda **kw: "raw brief")
    monkeypatch.setattr("cjs.cli.ModelRouter", MagicMock())
    monkeypatch.setattr(
        "cjs.cli.parse_brief",
        lambda raw_text, router: Brief(
            brand="X",
            objective="O",
            platform="TikTok",
            audience="A",
            tone="T",
            key_message="M",
            primary_kpi="awareness",
        ),
    )
    monkeypatch.setattr(
        "cjs.cli.generate_rubric",
        lambda brief, router: Rubric(weights={"brief_compliance": 1.0}),
    )
    monkeypatch.setattr(
        "cjs.cli.load_brand_rules_from_yaml",
        lambda path: BrandRules(brand_name="X", source="yaml"),
    )

    from cjs.schemas.video_dossier import VideoDossier

    monkeypatch.setattr(
        "cjs.cli.analyze_video",
        lambda video_path, run_folder, router, config: VideoDossier(
            video_path=str(video_path),
            duration_sec=15.0,
            transcript="",
        ),
    )

    _fake_verdict = {
        "winner_video": "a.mp4",
        "winner_rationale": "Best.",
        "ranking": ["a.mp4", "b.mp4"],
        "per_video_notes": {"a.mp4": "Good.", "b.mp4": "Ok."},
        "confidence": 0.9,
        "flags_resolved": [],
    }
    mock_compiled = MagicMock()
    mock_compiled.invoke.return_value = {
        "verdict": _fake_verdict,
        "rubric": {"weights": {"brief_compliance": 1.0}},
        "final_judgements": {},
    }
    mock_graph = MagicMock()
    mock_graph.compile.return_value = mock_compiled
    monkeypatch.setattr("cjs.graph.jury_graph.build_jury_graph", lambda: mock_graph)

    brief = tmp_path / "brief.pdf"
    brand = tmp_path / "brand.yaml"
    video1 = tmp_path / "a.mp4"
    video2 = tmp_path / "b.mp4"
    brief.write_text("brief")
    brand.write_text("brand:\n  name: X\n")
    video1.write_text("v1")
    video2.write_text("v2")

    result = runner.invoke(
        app,
        [
            "--json",
            "run",
            "--brief",
            str(brief),
            "--brand",
            str(brand),
            "--videos",
            str(video1),
            "--videos",
            str(video2),
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["run_id"]
    assert payload["winner"] == "a.mp4"
    run_folder = Path(payload["run_folder"])
    assert run_folder.exists()
    assert run_folder.parent.name == "runs"
    assert (run_folder / "config_snapshot.yaml").exists()


# Verify `run --json` fails validation when fewer than 2 videos are provided.
def test_run_json_fails_with_single_video(monkeypatch, tmp_path: Path) -> None:
    config = Settings()
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)

    brief = tmp_path / "brief.pdf"
    video1 = tmp_path / "a.mp4"
    brief.write_text("brief")
    video1.write_text("v1")

    result = runner.invoke(
        app,
        [
            "--json",
            "run",
            "--brief",
            str(brief),
            "--videos",
            str(video1),
        ],
    )

    assert result.exit_code != 0


# Verify non-JSON run output includes pipeline stages and completion message.
def test_run_non_json_prints_pipeline_and_placeholder(monkeypatch, tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from cjs.schemas.brand_rules import BrandRules
    from cjs.schemas.brief import Brief
    from cjs.schemas.rubric import Rubric

    config = Settings()
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)
    monkeypatch.setattr("cjs.cli.extract_brief_raw", lambda **kw: "raw brief")
    monkeypatch.setattr("cjs.cli.ModelRouter", MagicMock())
    monkeypatch.setattr(
        "cjs.cli.parse_brief",
        lambda raw_text, router: Brief(
            brand="X",
            objective="O",
            platform="TikTok",
            audience="A",
            tone="T",
            key_message="M",
            primary_kpi="awareness",
        ),
    )
    monkeypatch.setattr(
        "cjs.cli.generate_rubric",
        lambda brief, router: Rubric(weights={"brief_compliance": 1.0}),
    )
    monkeypatch.setattr(
        "cjs.cli.load_brand_rules_from_yaml",
        lambda path: BrandRules(brand_name="X", source="yaml"),
    )

    from cjs.schemas.video_dossier import VideoDossier

    monkeypatch.setattr(
        "cjs.cli.analyze_video",
        lambda video_path, run_folder, router, config: VideoDossier(
            video_path=str(video_path),
            duration_sec=15.0,
            transcript="",
        ),
    )

    _fake_verdict = {
        "winner_video": "a.mp4",
        "winner_rationale": "Best.",
        "ranking": ["a.mp4", "b.mp4"],
        "per_video_notes": {"a.mp4": "Good."},
        "confidence": 0.9,
        "flags_resolved": [],
    }
    mock_compiled = MagicMock()
    mock_compiled.invoke.return_value = {
        "verdict": _fake_verdict,
        "rubric": {"weights": {"brief_compliance": 1.0}},
        "final_judgements": {},
    }
    mock_graph = MagicMock()
    mock_graph.compile.return_value = mock_compiled
    monkeypatch.setattr("cjs.graph.jury_graph.build_jury_graph", lambda: mock_graph)

    brief = tmp_path / "brief.pdf"
    brand = tmp_path / "brand.yaml"
    video1 = tmp_path / "a.mp4"
    video2 = tmp_path / "b.mp4"
    brief.write_text("brief")
    brand.write_text("brand:\n  name: X\n")
    video1.write_text("v1")
    video2.write_text("v2")

    result = runner.invoke(
        app,
        [
            "run",
            "--brief",
            str(brief),
            "--brand",
            str(brand),
            "--videos",
            str(video1),
            "--videos",
            str(video2),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Pipeline:" in result.stdout
    assert "Brief ingestion complete" in result.stdout
    assert "Video analysis complete" in result.stdout
    assert "Run complete" in result.stdout


# Verify run enforces config max_videos limit in JSON mode.
def test_run_json_fails_when_video_count_exceeds_max(monkeypatch, tmp_path: Path) -> None:
    config = Settings()
    config.limits.max_videos = 2
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)

    brief = tmp_path / "brief.pdf"
    video1 = tmp_path / "a.mp4"
    video2 = tmp_path / "b.mp4"
    video3 = tmp_path / "c.mp4"
    brief.write_text("brief")
    video1.write_text("v1")
    video2.write_text("v2")
    video3.write_text("v3")

    result = runner.invoke(
        app,
        [
            "--json",
            "run",
            "--brief",
            str(brief),
            "--videos",
            str(video1),
            "--videos",
            str(video2),
            "--videos",
            str(video3),
        ],
    )

    assert result.exit_code != 0


# Verify top-level help includes the expected command surface.
def test_cli_help_lists_expected_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("configure", "config", "doctor", "runs", "report", "models", "run"):
        assert command in result.stdout


# Verify config command help includes get/set subcommands.
def test_config_help_lists_subcommands() -> None:
    result = runner.invoke(app, ["config", "--help"])

    assert result.exit_code == 0
    assert "get" in result.stdout
    assert "set" in result.stdout


# Verify run help includes the expected options.
def test_run_help_lists_expected_options() -> None:
    result = runner.invoke(app, ["run", "--help"])

    assert result.exit_code == 0
    stdout = _plain(result.stdout)
    for option in ("--brief", "--videos", "--brand", "--out"):
        assert option in stdout


# Verify configure help includes expected non-interactive and override options.
def test_configure_help_lists_expected_options() -> None:
    result = runner.invoke(app, ["configure", "--help"])

    assert result.exit_code == 0
    stdout = _plain(result.stdout)
    for option in (
        "--non-interactive",
        "--provider",
        "--text-model",
        "--vision-model",
        "--api-key-env",
        "--out-dir",
        "--max-videos",
        "--max-duration-sec",
        "--max-frames",
    ):
        assert option in stdout


# Verify help output remains standard CLI help even when --json is set globally.
def test_configure_help_with_json_still_shows_help_text() -> None:
    result = runner.invoke(app, ["--json", "configure", "--help"])

    assert result.exit_code == 0
    stdout = _plain(result.stdout)
    assert "One-time setup: choose provider, models, and limits" in stdout
    assert "--provider" in stdout


# Verify `doctor --json` emits checks including python_version status.
def test_doctor_json_includes_python_check() -> None:
    result = runner.invoke(app, ["--json", "doctor"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["status"] in {"ok", "warning", "error"}
    checks = payload["checks"]
    assert isinstance(checks, list)
    python_check = next((item for item in checks if item.get("check") == "python_version"), None)
    assert python_check is not None
    assert python_check["status"] in {"ok", "warning", "error"}


# Verify `doctor --yes --json` includes an auto-fix status check.
def test_doctor_yes_json_includes_auto_fix_check() -> None:
    result = runner.invoke(app, ["--json", "doctor", "--yes"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "fixes_applied" in payload["summary"]
    assert isinstance(payload["summary"]["fixes_applied"], list)
    auto_fix_check = next(
        (item for item in payload["checks"] if item.get("check") == "auto_fix"), None
    )
    assert auto_fix_check is not None
    assert auto_fix_check["status"] in {"ok", "warning", "error"}


# Verify doctor records created_default_config fix when config is missing with --yes.
def test_doctor_yes_json_records_created_default_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("cjs.cli.load_config", lambda: None)
    monkeypatch.setattr("cjs.cli.get_runs_dir", lambda _config: tmp_path)
    monkeypatch.setattr("cjs.cli.save_config", lambda _config: None)

    result = runner.invoke(app, ["--json", "doctor", "--yes"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "created_default_config" in payload["summary"]["fixes_applied"]


# Verify doctor records runs-dir recovery fix when --yes retry succeeds.
def test_doctor_yes_json_records_runs_dir_recovery(monkeypatch, tmp_path: Path) -> None:
    config = Settings()
    config.run.out_dir = str(tmp_path / "configured-runs")
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)

    calls = {"count": 0}

    def flaky_get_runs_dir(_config: Settings) -> Path:
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("simulated write failure")
        tmp_path.mkdir(parents=True, exist_ok=True)
        return tmp_path

    monkeypatch.setattr("cjs.cli.get_runs_dir", flaky_get_runs_dir)

    result = runner.invoke(app, ["--json", "doctor", "--yes"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "ensured_runs_dir_writable" in payload["summary"]["fixes_applied"]


# Verify non-JSON doctor output prints an overall summary line.
def test_doctor_non_json_prints_summary_line() -> None:
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Doctor summary:" in result.stdout


# Verify doctor JSON includes all core check names.
def test_doctor_json_includes_expected_check_names() -> None:
    result = runner.invoke(app, ["--json", "doctor"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    check_names = {item["check"] for item in payload["checks"]}
    assert {
        "python_version",
        "ffmpeg",
        "whisper",
        "config",
        "api_key_env",
        "runs_dir",
    } <= check_names


# Verify doctor JSON envelope contains required summary/check keys.
def test_doctor_json_envelope_shape() -> None:
    result = runner.invoke(app, ["--json", "doctor"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == {"summary", "checks"}
    assert {"status", "total_checks"} <= set(payload["summary"].keys())
    assert isinstance(payload["checks"], list)
    if payload["checks"]:
        assert {"check", "status", "message"} <= set(payload["checks"][0].keys())


# Verify doctor --yes JSON envelope keeps shape and includes fixes_applied.
def test_doctor_yes_json_envelope_includes_fixes_applied() -> None:
    result = runner.invoke(app, ["--json", "doctor", "--yes"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == {"summary", "checks"}
    assert {"status", "total_checks", "fixes_applied"} <= set(payload["summary"].keys())
    assert isinstance(payload["summary"]["fixes_applied"], list)
    assert isinstance(payload["checks"], list)


# Verify `config get` fails with a clear message for unknown keys.
def test_config_get_unknown_key(monkeypatch) -> None:
    monkeypatch.setattr("cjs.cli.load_config", lambda: Settings())

    result = runner.invoke(app, ["config", "get", "unknown.key"])

    assert result.exit_code != 0
    assert "Unknown config key: unknown.key" in _combined_output(result)


# Verify `--json config get` returns machine-readable error payload for unknown keys.
def test_config_get_unknown_key_json(monkeypatch) -> None:
    monkeypatch.setattr("cjs.cli.load_config", lambda: Settings())

    result = runner.invoke(app, ["--json", "config", "get", "unknown.key"])

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"] == "Unknown config key: unknown.key"


# --- audit command tests ---


# Verify `audit --json` returns a machine-readable error when config is missing.
def test_audit_json_missing_config(monkeypatch) -> None:
    monkeypatch.setattr("cjs.cli.load_config", lambda: None)

    result = runner.invoke(app, ["--json", "audit", "some-run"])

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "Run `cjs configure` first." in payload["error"]


# Verify `audit --json` returns an error when the run folder has no audit.jsonl.
def test_audit_json_missing_audit_file(monkeypatch, tmp_path: Path) -> None:
    config = Settings()
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)
    monkeypatch.setattr("cjs.cli.get_runs_dir", lambda _config: tmp_path)

    run_folder = tmp_path / "missing-run"
    run_folder.mkdir()

    result = runner.invoke(app, ["--json", "audit", "missing-run"])

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "missing-run" in payload["error"]


# Verify `audit --json` returns parsed entries from audit.jsonl.
def test_audit_json_returns_entries(monkeypatch, tmp_path: Path) -> None:
    config = Settings()
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)
    monkeypatch.setattr("cjs.cli.get_runs_dir", lambda _config: tmp_path)

    run_folder = tmp_path / "run-abc"
    run_folder.mkdir()
    audit_path = run_folder / "audit.jsonl"
    entry = {
        "ts": "2026-01-01T00:00:00+00:00",
        "run_id": "run-abc",
        "trace_id": "",
        "node": "brief_ingest",
        "agent": None,
        "model": "claude-sonnet-4-6",
        "prompt_hash": "abc123",
        "tokens_in": 100,
        "tokens_out": 200,
        "latency_ms": 350.5,
    }
    audit_path.write_text(json.dumps(entry) + "\n")

    result = runner.invoke(app, ["--json", "audit", "run-abc"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["node"] == "brief_ingest"
    assert payload[0]["tokens_in"] == 100


# Verify non-JSON audit renders a Rich table without crashing.
def test_audit_non_json_renders_table(monkeypatch, tmp_path: Path) -> None:
    config = Settings()
    monkeypatch.setattr("cjs.cli.load_config", lambda: config)
    monkeypatch.setattr("cjs.cli.get_runs_dir", lambda _config: tmp_path)

    run_folder = tmp_path / "run-xyz"
    run_folder.mkdir()
    audit_path = run_folder / "audit.jsonl"
    entry = {
        "ts": "2026-01-01T12:00:00+00:00",
        "run_id": "run-xyz",
        "trace_id": "",
        "node": "jury",
        "agent": "creative_strategist",
        "model": "claude-sonnet-4-6",
        "prompt_hash": "deadbeef",
        "tokens_in": 50,
        "tokens_out": 75,
        "latency_ms": 120.0,
    }
    audit_path.write_text(json.dumps(entry) + "\n")

    result = runner.invoke(app, ["audit", "run-xyz"])

    assert result.exit_code == 0
    assert "Audit log" in result.stdout
    assert "jury" in result.stdout


# Verify `audit` help lists the run_id argument.
def test_audit_help_lists_run_id() -> None:
    result = runner.invoke(app, ["audit", "--help"])

    assert result.exit_code == 0
    assert "RUN_ID" in result.stdout


def test_resume_missing_run_exits_nonzero(tmp_path, monkeypatch):
    from cjs.config import Settings

    monkeypatch.setattr("cjs.cli.load_config", lambda: Settings())
    monkeypatch.setattr("cjs.cli.get_runs_dir", lambda _config: tmp_path / ".cjs" / "runs")
    (tmp_path / ".cjs" / "runs").mkdir(parents=True)

    result = runner.invoke(app, ["resume", "nonexistent_run_id"])
    assert result.exit_code != 0


def test_resume_missing_checkpoint_exits_nonzero(tmp_path, monkeypatch):
    from cjs.config import Settings

    runs_dir = tmp_path / ".cjs" / "runs"
    monkeypatch.setattr("cjs.cli.load_config", lambda: Settings())
    monkeypatch.setattr("cjs.cli.get_runs_dir", lambda _config: runs_dir)
    # Create a run folder but no checkpoints.db
    run_folder = runs_dir / "20260518_120000_abcd"
    run_folder.mkdir(parents=True)

    result = runner.invoke(app, ["resume", "20260518_120000_abcd"])
    assert result.exit_code != 0
