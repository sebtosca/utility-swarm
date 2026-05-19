from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from cjs.constants import MAX_DURATION_SEC, MAX_FILE_MB, MAX_FRAMES, MAX_PDF_PAGES, MAX_VIDEOS


class ConfigError(Exception):
    """Raised when config exists but cannot be loaded or validated."""


class ModelSettings(BaseModel):
    text: str = "claude-sonnet-4-6"
    vision: str = "claude-sonnet-4-6"
    extended_thinking: str = "claude-opus-4-7"


class AuthSettings(BaseModel):
    api_key_env: str = "ANTHROPIC_API_KEY"


class LimitSettings(BaseModel):
    max_videos: int = MAX_VIDEOS
    max_duration_sec: int = MAX_DURATION_SEC
    max_frames: int = MAX_FRAMES
    max_pdf_pages: int = MAX_PDF_PAGES
    max_file_mb: int = MAX_FILE_MB


class RunSettings(BaseModel):
    out_dir: str = "./runs"


# Path to the user's config file: ~/.cjs/config.yaml.
def get_config_path() -> Path:
    config_path = Path.home() / ".cjs" / "config.yaml"
    return config_path


# Create ~/.cjs directory if it does not exist.
def ensure_config_path() -> None:
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)


# Config model: provider, models, auth, limits, run (loaded from/saved to YAML).
class Settings(BaseModel):
    provider: str = Field(default="anthropic")
    models: ModelSettings = Field(default_factory=ModelSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    limits: LimitSettings = Field(default_factory=LimitSettings)
    run: RunSettings = Field(default_factory=RunSettings)


# Load config from ~/.cjs/config.yaml; return None if missing.
def load_config() -> Settings | None:
    path = get_config_path()
    if not path.exists():
        return None

    try:
        raw = path.read_text()
        data = yaml.safe_load(raw)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Could not read config file at {path}: {exc}") from exc

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config root at {path} must be a mapping")

    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid config values at {path}: {exc}") from exc


# Write config to ~/.cjs/config.yaml.
def save_config(config: Settings) -> None:
    ensure_config_path()
    path = get_config_path()
    data = config.model_dump()
    path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))
