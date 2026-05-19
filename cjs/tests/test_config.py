from pathlib import Path

import pytest

from cjs import config as config_module
from cjs.config import ConfigError, load_config


# Verify missing config file returns None (initial setup state).
def test_load_config_returns_none_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_path = tmp_path / "missing.yaml"
    monkeypatch.setattr(config_module, "get_config_path", lambda: missing_path)
    assert load_config() is None


# Verify malformed YAML raises ConfigError.
def test_load_config_raises_on_invalid_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("provider: [")
    monkeypatch.setattr(config_module, "get_config_path", lambda: config_path)

    with pytest.raises(ConfigError):
        load_config()


# Verify schema/type validation errors raise ConfigError.
def test_load_config_raises_on_invalid_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("limits:\n  max_videos: not-an-int\n")
    monkeypatch.setattr(config_module, "get_config_path", lambda: config_path)

    with pytest.raises(ConfigError):
        load_config()
