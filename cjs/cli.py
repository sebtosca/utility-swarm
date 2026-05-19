import json
import os
import shutil
import sys
from pathlib import Path

import click
import typer
from rich.console import Console

from cjs.config import ConfigError, Settings, get_config_path, load_config, save_config
from cjs.pipelines.brief_ingest import (
    BriefIngestError,
    extract_brief_raw,
    generate_rubric,
    generate_starter_brand_yaml,
    load_brand_rules_from_yaml,
    parse_brief,
)
from cjs.pipelines.video_analysis import VideoAnalysisError, analyze_video
from cjs.router.model_router import ModelRouter
from cjs.storage.runs import (
    copy_brief_into_run,
    copy_videos_into_run,
    create_run_folder,
    get_runs_dir,
)

app = typer.Typer(no_args_is_help=True)
config_app = typer.Typer(help="Manage CLI configuration.")
brand_app = typer.Typer(help="Brand pack utilities.")
app.add_typer(config_app, name="config")
app.add_typer(brand_app, name="brand")


# Output helper for plain and JSON modes.
def output_result(data: object, json_mode: bool) -> None:
    if json_mode:
        typer.echo(json.dumps(data))
        return
    typer.echo(data)


# Read root-level JSON mode from Typer context.
def is_json_mode(ctx: typer.Context | None) -> bool:
    if ctx is None:
        return False
    obj = ctx.obj if isinstance(ctx.obj, dict) else {}
    return bool(obj.get("json_mode", False))


# Resolve a dot-path key from a nested dictionary and return its value.
def get_nested_value(data: dict[str, object], key_path: str) -> object:
    current: object = data
    for key in key_path.split("."):
        if not isinstance(current, dict) or key not in current:
            raise KeyError(key_path)
        current = current[key]
    return current


# Set a dot-path key in a nested dictionary; all intermediate keys must exist.
def set_nested_value(data: dict[str, object], key_path: str, value: object) -> None:
    keys = key_path.split(".")
    current: object = data
    for key in keys[:-1]:
        if not isinstance(current, dict) or key not in current:
            raise KeyError(key_path)
        current = current[key]
    if not isinstance(current, dict) or keys[-1] not in current:
        raise KeyError(key_path)
    current[keys[-1]] = value


# Coerce config-set input values by key namespace.
def coerce_config_value(key_path: str, value: str) -> object:
    if key_path.startswith("limits."):
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"Expected integer for {key_path}") from exc
    return value


# Print full config state for now (scaffold for key-based config get).
@config_app.command("get")
def config_get(
    ctx: typer.Context,
    key: str | None = typer.Argument(None, help="Optional dot-path key, e.g. models.text"),
) -> None:
    """Get full config or a single dot-path value."""
    json_mode = is_json_mode(ctx)
    try:
        config = load_config() or Settings()
    except ConfigError as exc:
        if json_mode:
            output_result({"ok": False, "error": str(exc)}, json_mode=True)
        else:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    data = config.model_dump()
    if key is None:
        output_result(data, json_mode=json_mode)
        return

    try:
        value = get_nested_value(data, key)
    except KeyError:
        message = f"Unknown config key: {key}"
        if json_mode:
            output_result({"ok": False, "error": message, "key": key}, json_mode=True)
        else:
            typer.secho(message, err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    output_result(value, json_mode=json_mode)


# Validate key/value inputs for config set (scaffold; no mutation yet).
@config_app.command("set")
def config_set(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Dot-path key, e.g. models.text"),
    value: str = typer.Argument(..., help="New value as string."),
) -> None:
    """Set a single config value by dot-path key."""
    json_mode = is_json_mode(ctx)
    try:
        config = load_config() or Settings()
    except ConfigError as exc:
        if json_mode:
            output_result({"ok": False, "error": str(exc)}, json_mode=True)
        else:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    data = config.model_dump()
    try:
        get_nested_value(data, key)
    except KeyError:
        message = f"Unknown config key: {key}"
        if json_mode:
            output_result({"ok": False, "error": message, "key": key}, json_mode=True)
        else:
            typer.secho(message, err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    try:
        parsed_value = coerce_config_value(key, value)
    except ValueError as exc:
        if json_mode:
            output_result({"ok": False, "error": str(exc), "key": key}, json_mode=True)
        else:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    set_nested_value(data, key, parsed_value)
    try:
        updated_config = Settings.model_validate(data)
    except Exception as exc:
        message = f"Invalid value for {key}: {exc}"
        if json_mode:
            output_result({"ok": False, "error": message, "key": key}, json_mode=True)
        else:
            typer.secho(message, err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    save_config(updated_config)
    if json_mode:
        output_result(
            {"ok": True, "key": key, "value": parsed_value, "config_path": str(get_config_path())},
            json_mode=True,
        )
    else:
        typer.echo(f"Set {key}={parsed_value}")
        typer.secho(f"Config saved to {get_config_path()}", fg=typer.colors.GREEN)


# Root callback: CLI description.
@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logs"),
    json_mode: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Creative Jury Swarm CLI. Run `cjs configure` once, then `cjs run --brief ... --videos ...`."""
    ctx.obj = {"verbose": verbose, "json_mode": json_mode}

    if ctx.invoked_subcommand is None:
        # Show help when no command is provided
        typer.echo(ctx.get_help())
        raise typer.Exit()

    if verbose:
        typer.echo("Verbose mode enabled")


# Run environment checks (ffmpeg, API key, etc.).
@app.command()
def doctor(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", help="Auto-apply safe fixes."),
) -> None:
    """Run environment checks."""
    json_mode = is_json_mode(ctx)
    checks: list[dict[str, str]] = []
    fixes_applied: list[str] = []

    required = (3, 10)
    current = sys.version_info[:3]
    status = "ok" if current >= required else "error"
    message = (
        f"Python {current[0]}.{current[1]}.{current[2]} (required >= {required[0]}.{required[1]})"
    )
    checks.append({"check": "python_version", "status": status, "message": message})

    ffmpeg_path = shutil.which("ffmpeg")
    ffmpeg_status = "ok" if ffmpeg_path else "warning"
    ffmpeg_message = f"ffmpeg found at {ffmpeg_path}" if ffmpeg_path else "ffmpeg not found on PATH"
    checks.append({"check": "ffmpeg", "status": ffmpeg_status, "message": ffmpeg_message})

    try:
        __import__("whisper")
        whisper_status = "ok"
        whisper_message = "whisper import available"
    except ImportError:
        whisper_status = "warning"
        whisper_message = "whisper not installed"
    checks.append({"check": "whisper", "status": whisper_status, "message": whisper_message})

    try:
        doctor_config = load_config()
        if doctor_config is None:
            if yes:
                doctor_config = Settings()
                save_config(doctor_config)
                fixes_applied.append("created_default_config")
                config_status = "ok"
                config_message = f"Config created at {get_config_path()}"
            else:
                config_status = "warning"
                config_message = "Config file not found. Run `cjs configure`."
        else:
            config_status = "ok"
            config_message = f"Config is valid at {get_config_path()}"
    except ConfigError as exc:
        doctor_config = None
        config_status = "error"
        config_message = f"Config invalid: {exc}"
    checks.append({"check": "config", "status": config_status, "message": config_message})

    if doctor_config is None:
        api_key_status = "warning"
        api_key_message = "API key env check skipped (configure first)"
    else:
        env_name = doctor_config.auth.api_key_env
        env_value = os.environ.get(env_name, "")
        if env_value:
            api_key_status = "ok"
            api_key_message = f"{env_name} is set"
        else:
            api_key_status = "warning"
            api_key_message = f"{env_name} is not set"
    checks.append({"check": "api_key_env", "status": api_key_status, "message": api_key_message})

    if doctor_config is None:
        runs_dir_status = "warning"
        runs_dir_message = "Runs dir check skipped (configure first)"
    else:
        try:
            runs_dir = get_runs_dir(doctor_config)
            probe_path = runs_dir / ".cjs_write_probe"
            probe_path.write_text("ok")
            probe_path.unlink()
            runs_dir_status = "ok"
            runs_dir_message = f"Runs dir writable: {runs_dir}"
        except OSError as exc:
            if yes:
                try:
                    Path(doctor_config.run.out_dir).expanduser().mkdir(parents=True, exist_ok=True)
                    runs_dir = get_runs_dir(doctor_config)
                    probe_path = runs_dir / ".cjs_write_probe"
                    probe_path.write_text("ok")
                    probe_path.unlink()
                    fixes_applied.append("ensured_runs_dir_writable")
                    runs_dir_status = "ok"
                    runs_dir_message = f"Runs dir writable after fix: {runs_dir}"
                except OSError as retry_exc:
                    runs_dir_status = "error"
                    runs_dir_message = f"Runs dir not writable: {retry_exc}"
            else:
                runs_dir_status = "error"
                runs_dir_message = f"Runs dir not writable: {exc}"
    checks.append({"check": "runs_dir", "status": runs_dir_status, "message": runs_dir_message})

    if yes:
        checks.append(
            {"check": "auto_fix", "status": "ok", "message": "Applied safe fixes where possible"}
        )

    if any(check["status"] == "error" for check in checks):
        overall_status = "error"
    elif any(check["status"] == "warning" for check in checks):
        overall_status = "warning"
    else:
        overall_status = "ok"
    summary = {"status": overall_status, "total_checks": len(checks)}
    if yes:
        summary["fixes_applied"] = fixes_applied

    if json_mode:
        output_result({"summary": summary, "checks": checks}, json_mode=True)
    else:
        summary_color = (
            typer.colors.GREEN
            if overall_status == "ok"
            else typer.colors.YELLOW
            if overall_status == "warning"
            else typer.colors.RED
        )
        typer.secho(
            f"Doctor summary: {overall_status.upper()} ({len(checks)} checks)", fg=summary_color
        )
        for check in checks:
            color = (
                typer.colors.GREEN
                if check["status"] == "ok"
                else typer.colors.YELLOW
                if check["status"] == "warning"
                else typer.colors.RED
            )
            typer.secho(
                f"[{check['status'].upper()}] {check['check']}: {check['message']}", fg=color
            )

    if overall_status == "error":
        raise typer.Exit(1)


@app.command()
# Interactive setup flow that collects config values and writes config.yaml.
def configure(
    ctx: typer.Context,
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Save config without prompts."
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        help="Model provider.",
        case_sensitive=False,
        show_choices=True,
        click_type=click.Choice(["openai", "anthropic", "ollama", "openai-compatible"]),
    ),
    text_model: str | None = typer.Option(None, "--text-model", help="Text model name."),
    vision_model: str | None = typer.Option(None, "--vision-model", help="Vision model name."),
    api_key_env: str | None = typer.Option(
        None, "--api-key-env", help="API key environment variable name."
    ),
    out_dir: Path | None = typer.Option(None, "--out-dir", help="Output directory for runs."),
    max_videos: int | None = typer.Option(None, "--max-videos", help="Maximum videos per run."),
    max_duration_sec: int | None = typer.Option(
        None, "--max-duration-sec", help="Maximum video duration in seconds."
    ),
    max_frames: int | None = typer.Option(
        None, "--max-frames", help="Maximum extracted frames per video."
    ),
) -> None:
    """One-time setup: choose provider, models, and limits; write ~/.cjs/config.yaml."""
    json_mode = is_json_mode(ctx)
    try:
        config = load_config() or Settings()
    except ConfigError as exc:
        if json_mode:
            output_result({"ok": False, "error": str(exc)}, json_mode=True)
        else:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    if provider is not None:
        config.provider = provider
    if text_model is not None:
        config.models.text = text_model
    if vision_model is not None:
        config.models.vision = vision_model
    if api_key_env is not None:
        config.auth.api_key_env = api_key_env
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        config.run.out_dir = str(out_dir)
    if max_videos is not None:
        config.limits.max_videos = max_videos
    if max_duration_sec is not None:
        config.limits.max_duration_sec = max_duration_sec
    if max_frames is not None:
        config.limits.max_frames = max_frames

    has_explicit_overrides = any(
        value is not None
        for value in (
            provider,
            text_model,
            vision_model,
            api_key_env,
            out_dir,
            max_videos,
            max_duration_sec,
            max_frames,
        )
    )

    if non_interactive or has_explicit_overrides:
        save_config(config)
        if json_mode:
            output_result({"ok": True, "config_path": str(get_config_path())}, json_mode=True)
        else:
            typer.secho(f"Config saved to {get_config_path()}", fg=typer.colors.GREEN)
        return

    config.provider = typer.prompt(
        "Provider",
        default=config.provider,
        type=click.Choice(["openai", "anthropic", "ollama", "openai-compatible"]),
    )

    config.models.text = typer.prompt("Text model name", default=config.models.text)
    config.models.vision = typer.prompt("Vision model name", default=config.models.vision)

    config.auth.api_key_env = typer.prompt(
        "API key env var name",
        default=config.auth.api_key_env,
    )

    prompted_out_dir = Path(typer.prompt("Output directory for runs", default=config.run.out_dir))
    prompted_out_dir.mkdir(parents=True, exist_ok=True)
    config.run.out_dir = str(prompted_out_dir)

    config.limits.max_videos = typer.prompt(
        "Max videos per run", default=config.limits.max_videos, type=int
    )
    config.limits.max_duration_sec = typer.prompt(
        "Max video duration (seconds)",
        default=config.limits.max_duration_sec,
        type=int,
    )
    config.limits.max_frames = typer.prompt(
        "Max frames per video", default=config.limits.max_frames, type=int
    )

    save_config(config)

    if json_mode:
        output_result({"ok": True, "config_path": str(get_config_path())}, json_mode=True)
        return

    typer.secho(f"Config saved to {get_config_path()}", fg=typer.colors.GREEN)

    typer.echo("\nNext steps:")
    typer.echo(f"  1. Set your API key: export {config.auth.api_key_env}=<your-key>")
    typer.echo("  2. Run the jury: cjs run --brief path/to/brief.pdf --videos ad1.mp4 ad2.mp4")
    typer.echo("  3. Check env: cjs doctor")


# Show configured text and vision model names.
@app.command()
def models(ctx: typer.Context) -> None:
    """Show configured text and vision model names."""
    json_mode = is_json_mode(ctx)
    try:
        config = load_config()
    except ConfigError as exc:
        if json_mode:
            output_result({"ok": False, "error": str(exc)}, json_mode=True)
        else:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    if config is None:
        message = "Run `cjs configure` first."
        if json_mode:
            output_result({"ok": False, "error": message}, json_mode=True)
        else:
            typer.secho(message, err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    payload = {"text": config.models.text, "vision": config.models.vision}
    if json_mode:
        output_result(payload, json_mode=True)
    else:
        typer.echo(f"Text: {payload['text']}, Vision: {payload['vision']}")


# List run folders sorted by most recent modification time.
@app.command()
def runs(ctx: typer.Context) -> None:
    """List previous run IDs (newest first)."""
    json_mode = is_json_mode(ctx)
    try:
        config = load_config()
    except ConfigError as exc:
        if json_mode:
            output_result({"ok": False, "error": str(exc)}, json_mode=True)
        else:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    if config is None:
        message = "Run `cjs configure` first."
        if json_mode:
            output_result({"ok": False, "error": message}, json_mode=True)
        else:
            typer.secho(message, err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    runs_dir = get_runs_dir(config)
    run_dirs = sorted(
        [path for path in runs_dir.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    payload = [{"run_id": path.name, "path": str(path)} for path in run_dirs]

    if json_mode:
        output_result(payload, json_mode=True)
    else:
        for item in payload:
            typer.echo(item["run_id"])


# Show report status for a specific run ID.
@app.command()
def report(
    ctx: typer.Context,
    run_id: str = typer.Argument(..., help="Run ID to inspect (folder name under runs/)."),
) -> None:
    """Open or print the report for a run."""
    json_mode = is_json_mode(ctx)
    try:
        config = load_config()
    except ConfigError as exc:
        if json_mode:
            output_result({"ok": False, "error": str(exc)}, json_mode=True)
        else:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    if config is None:
        message = "Run `cjs configure` first."
        if json_mode:
            output_result({"ok": False, "error": message}, json_mode=True)
        else:
            typer.secho(message, err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    run_folder = get_runs_dir(config) / run_id
    if not run_folder.exists() or not run_folder.is_dir():
        message = f"Run not found: {run_id}"
        if json_mode:
            output_result({"ok": False, "error": message, "run_id": run_id}, json_mode=True)
        else:
            typer.secho(message, err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    report_path = run_folder / "results" / "report.md"
    exists = report_path.exists()
    if json_mode:
        output_result(
            {"run_id": run_id, "report_path": str(report_path), "exists": exists}, json_mode=True
        )
        return

    if exists:
        typer.echo(str(report_path))
    else:
        typer.echo("No report yet for this run")


# Run the jury: brief + videos; optional brand pack and output dir override.
@app.command()
def run(
    ctx: typer.Context,
    brief: Path = typer.Option(
        ...,
        help="Path to the creative brief PDF.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    videos: list[Path] = typer.Option(
        ...,
        help="Paths to video ads (2 or more).",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    brand: Path = typer.Option(
        ...,
        help="Path to brand pack YAML (required). Generate one with `cjs brand init --brief brief.pdf`.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    out: Path | None = typer.Option(
        None,
        help="Override output directory for this run.",
        file_okay=False,
        dir_okay=True,
    ),
    strict_confidence: bool = typer.Option(
        False,
        "--strict-confidence",
        help="Exit with error if verdict confidence is below 70%.",
    ),
) -> None:
    """Run the jury pipeline: brief + videos → winner + report."""
    json_mode = is_json_mode(ctx)
    try:
        config = load_config()
    except ConfigError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    if config is None:
        typer.secho("Run `cjs configure` first.", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    if len(videos) < 2:
        raise typer.BadParameter("Provide at least 2 videos.", param_hint="--videos")

    max_videos = config.limits.max_videos
    if len(videos) > max_videos:
        raise typer.BadParameter(f"Too many videos (max {max_videos}).", param_hint="--videos")

    if brief.suffix.lower() != ".pdf":
        raise typer.BadParameter("Brief must be a PDF file.", param_hint="--brief")

    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        config.run.out_dir = str(out)

    run_folder = create_run_folder(config)
    run_id = run_folder.name
    copied_brief = copy_brief_into_run(brief, run_folder)
    copied_videos = copy_videos_into_run(videos, run_folder)

    if not json_mode:
        console = Console()
        console.print(
            "[bold]Pipeline:[/bold] [Brief] → [Video Analysis] → [Jury] → [Auction] → [Report]"
        )

    # --- Phase 9: Brief ingestion (LLM) ---
    router = ModelRouter(run_id=run_id, run_folder=run_folder, config=config)
    brief_dir = run_folder / "brief"

    try:
        raw_text = extract_brief_raw(
            pdf_path=copied_brief,
            run_folder=run_folder,
            max_pages=config.limits.max_pdf_pages,
        )
        if not json_mode:
            typer.echo("[1/3] Parsing brief...")
        parsed_brief = parse_brief(raw_text=raw_text, router=router)
        (brief_dir / "brief.json").write_text(parsed_brief.model_dump_json(indent=2))

        if not json_mode:
            typer.echo("[2/3] Generating rubric...")
        rubric = generate_rubric(brief=parsed_brief, router=router)
        (brief_dir / "rubric.json").write_text(rubric.model_dump_json(indent=2))

        if not json_mode:
            typer.echo("[3/3] Loading brand rules...")
        brand_rules = load_brand_rules_from_yaml(brand)
        (brief_dir / "brand_rules.json").write_text(brand_rules.model_dump_json(indent=2))

    except BriefIngestError as exc:
        if json_mode:
            output_result({"status": "error", "run_id": run_id, "error": str(exc)}, json_mode=True)
        else:
            typer.secho(f"Brief ingestion failed: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    if not json_mode:
        typer.secho("Brief ingestion complete.", fg=typer.colors.GREEN)

    # --- Phase 10: Video analysis ---
    dossiers = []
    for i, video_path in enumerate(copied_videos, start=1):
        if not json_mode:
            typer.echo(f"[Video {i}/{len(copied_videos)}] Analysing {video_path.name}...")
        try:
            dossier = analyze_video(
                video_path=video_path,
                run_folder=run_folder,
                router=router,
                config=config,
            )
            dossiers.append(dossier)
        except VideoAnalysisError as exc:
            if json_mode:
                output_result(
                    {"status": "error", "run_id": run_id, "error": str(exc)}, json_mode=True
                )
            else:
                typer.secho(f"Video analysis failed: {exc}", err=True, fg=typer.colors.RED)
            raise typer.Exit(1)

    if not json_mode:
        typer.secho(
            f"Video analysis complete. {len(dossiers)} dossier(s) written.", fg=typer.colors.GREEN
        )

    # --- Phase 11: LangGraph jury swarm ---
    import json as _json
    from langgraph.checkpoint.sqlite import SqliteSaver
    from cjs.graph.jury_graph import build_jury_graph
    from cjs.graph.state import JuryState

    if not json_mode:
        typer.echo("[Jury] Running jury swarm...")

    initial_jury_state: JuryState = {
        "run_id": run_id,
        "brief": parsed_brief.model_dump(),
        "rubric": rubric.model_dump(),
        "brand_rules": brand_rules.model_dump(),
        "video_dossiers": [d.model_dump() for d in dossiers],
        "initial_judgements": {},
        "consistency_report": None,
        "final_judgements": {},
        "verdict": None,
    }

    checkpoints_db = run_folder / "checkpoints.db"
    saver = SqliteSaver.from_conn_string(str(checkpoints_db))
    compiled = build_jury_graph().compile(checkpointer=saver)
    thread_config = {"configurable": {"thread_id": run_id, "router": router, "strict_confidence": strict_confidence}}

    from cjs.escalation.human_review import HumanReviewRejectedError
    from cjs.escalation.confidence_gate import LowConfidenceError
    try:
        final_state = compiled.invoke(initial_jury_state, config=thread_config)
    except HumanReviewRejectedError:
        if json_mode:
            output_result({"status": "paused", "run_id": run_id,
                           "reason": "human_review_rejected"}, json_mode=True)
        else:
            typer.secho(
                f"Run paused at human review gate. Resume with: cjs resume {run_id}",
                fg=typer.colors.YELLOW,
            )
        raise typer.Exit(0)
    except LowConfidenceError as exc:
        if json_mode:
            output_result({"status": "error", "run_id": run_id, "error": str(exc)}, json_mode=True)
        else:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as exc:
        if json_mode:
            output_result({"status": "error", "run_id": run_id, "error": str(exc)}, json_mode=True)
        else:
            typer.secho(f"Jury swarm failed: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    from cjs.auction.engine import run_auction
    auction_verdict = run_auction(final_state, run_folder)

    if not json_mode:
        typer.secho(f"Winner: {auction_verdict['winner_video']}", fg=typer.colors.GREEN)
        typer.secho("Run complete.", fg=typer.colors.GREEN)

    if json_mode:
        output_result(
            {
                "status": "ok",
                "run_id": run_id,
                "run_folder": str(run_folder),
                "winner": auction_verdict["winner_video"],
                "verdict": str(run_folder / "results" / "verdict.json"),
                "scorecards": str(run_folder / "results" / "scorecards.json"),
            },
            json_mode=True,
        )


@brand_app.command("init")
def brand_init(
    ctx: typer.Context,
    brief: Path = typer.Option(
        ...,
        help="Path to the creative brief PDF.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    out: Path = typer.Option(
        Path("brand.yaml"),
        help="Output path for the generated brand YAML.",
    ),
) -> None:
    """Generate a starter brand YAML from a brief PDF. Review and edit before using with cjs run."""
    json_mode = is_json_mode(ctx)
    try:
        config = load_config()
    except ConfigError as exc:
        if json_mode:
            output_result({"ok": False, "error": str(exc)}, json_mode=True)
        else:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    if config is None:
        message = "Run `cjs configure` first."
        if json_mode:
            output_result({"ok": False, "error": message}, json_mode=True)
        else:
            typer.secho(message, err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    import tempfile

    tmp_dir = Path(tempfile.mkdtemp())
    run_id = "brand_init_tmp"
    router = ModelRouter(run_id=run_id, run_folder=tmp_dir, config=config)

    try:
        raw_text = extract_brief_raw(
            pdf_path=brief, run_folder=tmp_dir, max_pages=config.limits.max_pdf_pages
        )
        yaml_content = generate_starter_brand_yaml(raw_text=raw_text, router=router)
    except BriefIngestError as exc:
        if json_mode:
            output_result({"ok": False, "error": str(exc)}, json_mode=True)
        else:
            typer.secho(f"Brand init failed: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    out.write_text(yaml_content)

    if json_mode:
        output_result({"ok": True, "path": str(out)}, json_mode=True)
    else:
        typer.secho(f"Starter brand YAML written to {out}", fg=typer.colors.GREEN)
        typer.echo("Review and edit before passing to `cjs run --brand`.")


@app.command()
def audit(
    ctx: typer.Context,
    run_id: str = typer.Argument(..., help="Run ID to inspect."),
) -> None:
    """Print the LLM audit log for a run as a table."""
    import json as _json

    from rich.console import Console as RichConsole
    from rich.table import Table

    json_mode = is_json_mode(ctx)
    try:
        config = load_config()
    except ConfigError as exc:
        if json_mode:
            output_result({"ok": False, "error": str(exc)}, json_mode=True)
        else:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    if config is None:
        message = "Run `cjs configure` first."
        if json_mode:
            output_result({"ok": False, "error": message}, json_mode=True)
        else:
            typer.secho(message, err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    audit_path = get_runs_dir(config) / run_id / "audit.jsonl"
    if not audit_path.exists():
        message = f"No audit log found for run: {run_id}"
        if json_mode:
            output_result({"ok": False, "error": message, "run_id": run_id}, json_mode=True)
        else:
            typer.secho(message, err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    entries = []
    for line in audit_path.read_text().splitlines():
        line = line.strip()
        if line:
            entries.append(_json.loads(line))

    if json_mode:
        output_result(entries, json_mode=True)
        return

    console = RichConsole()
    table = Table(title=f"Audit log — {run_id}", show_lines=False)
    table.add_column("Timestamp", style="dim", no_wrap=True)
    table.add_column("Node")
    table.add_column("Agent")
    table.add_column("Model")
    table.add_column("In", justify="right")
    table.add_column("Out", justify="right")
    table.add_column("ms", justify="right")
    table.add_column("Hash", style="dim")
    table.add_column("Error", style="red")

    for e in entries:
        table.add_row(
            e.get("ts", "")[:19].replace("T", " "),
            e.get("node", ""),
            e.get("agent") or "",
            e.get("model", ""),
            str(e.get("tokens_in", "")),
            str(e.get("tokens_out", "")),
            str(e.get("latency_ms", "")),
            e.get("prompt_hash", ""),
            e.get("error") or "",
        )

    console.print(table)


@app.command()
def resume(
    run_id: str = typer.Argument(..., help="Run ID to resume (the folder name under runs/)."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
    strict_confidence: bool = typer.Option(
        False,
        "--strict-confidence",
        help="Exit with error if verdict confidence is below 70%.",
    ),
) -> None:
    """Resume a run from its last LangGraph checkpoint."""
    import json as _json
    from langgraph.checkpoint.sqlite import SqliteSaver
    from cjs.graph.jury_graph import build_jury_graph

    config = load_config()
    run_folder = get_runs_dir(config) / run_id

    if not run_folder.exists() or not run_folder.is_dir():
        message = f"Run not found: {run_id}"
        if json_output:
            output_result({"ok": False, "error": message, "run_id": run_id}, json_mode=True)
        else:
            typer.secho(f"Error: {message}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    checkpoints_db = run_folder / "checkpoints.db"
    if not checkpoints_db.exists():
        message = f"No checkpoint found for run: {run_id}. Was this run started with Phase 11?"
        if json_output:
            output_result({"ok": False, "error": message, "run_id": run_id}, json_mode=True)
        else:
            typer.secho(f"Error: {message}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    router = ModelRouter(run_id=run_id, run_folder=run_folder, config=config)
    saver = SqliteSaver.from_conn_string(str(checkpoints_db))
    compiled = build_jury_graph().compile(checkpointer=saver)
    thread_config = {"configurable": {"thread_id": run_id, "router": router, "strict_confidence": strict_confidence}}

    if not json_output:
        typer.echo(f"Resuming run {run_id}...")

    from cjs.escalation.human_review import HumanReviewRejectedError
    from cjs.escalation.confidence_gate import LowConfidenceError
    try:
        final_state = compiled.invoke(None, config=thread_config)
    except HumanReviewRejectedError:
        if json_output:
            output_result({"ok": False, "status": "paused", "run_id": run_id,
                           "reason": "human_review_rejected"}, json_mode=True)
        else:
            typer.secho(
                f"Run paused at human review gate. Resume again with: cjs resume {run_id}",
                fg=typer.colors.YELLOW,
            )
        raise typer.Exit(0)
    except LowConfidenceError as exc:
        if json_output:
            output_result({"ok": False, "error": str(exc), "run_id": run_id}, json_mode=True)
        else:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as exc:
        if json_output:
            output_result({"ok": False, "error": str(exc), "run_id": run_id}, json_mode=True)
        else:
            typer.secho(f"Resume failed: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    from cjs.auction.engine import run_auction
    auction_verdict = run_auction(final_state, run_folder) if final_state else {}

    if json_output:
        output_result(
            {
                "ok": True, "run_id": run_id,
                "winner": auction_verdict.get("winner_video"),
            },
            json_mode=True,
        )
    else:
        winner = auction_verdict.get("winner_video", "unknown")
        typer.secho(f"Run {run_id} complete. Winner: {winner}", fg=typer.colors.GREEN)


# Keep top-level command help ordered by the expected workflow.
def _apply_command_order() -> None:
    order = {
        "configure": 1,
        "config": 2,
        "brand": 3,
        "run": 4,
        "runs": 5,
        "report": 6,
        "audit": 7,
        "models": 8,
        "doctor": 9,
    }

    def _cmd_name(command: object) -> str:
        name = getattr(command, "name", None)
        if name:
            return name
        cb = getattr(command, "callback", None)
        return getattr(cb, "__name__", "") if cb else ""

    app.registered_commands.sort(key=lambda c: order.get(_cmd_name(c), 999))
    app.registered_groups.sort(key=lambda g: order.get(getattr(g, "name", "") or "", 999))


_apply_command_order()

if __name__ == "__main__":
    app(prog_name="cjs")
