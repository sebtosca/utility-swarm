import pytest

from cjs.cli import coerce_config_value, get_nested_value, set_nested_value


# Verify dot-path lookup returns nested values.
def test_get_nested_value_returns_nested_value() -> None:
    data = {"models": {"text": "gpt-4o-mini"}}
    assert get_nested_value(data, "models.text") == "gpt-4o-mini"


# Verify dot-path lookup raises for missing keys.
def test_get_nested_value_raises_for_missing_key() -> None:
    data = {"models": {"text": "gpt-4o-mini"}}
    with pytest.raises(KeyError):
        get_nested_value(data, "models.vision")


# Verify strict set updates existing nested keys.
def test_set_nested_value_updates_existing_key() -> None:
    data = {"limits": {"max_videos": 3}}
    set_nested_value(data, "limits.max_videos", 5)
    assert data["limits"]["max_videos"] == 5


# Verify strict set rejects unknown nested keys.
def test_set_nested_value_raises_for_missing_key() -> None:
    data = {"limits": {"max_videos": 3}}
    with pytest.raises(KeyError):
        set_nested_value(data, "limits.max_frames", 12)


# Verify limits values are coerced to integers.
def test_coerce_config_value_converts_limits_to_int() -> None:
    assert coerce_config_value("limits.max_videos", "7") == 7


# Verify invalid limits integers raise a value error.
def test_coerce_config_value_raises_for_invalid_int() -> None:
    with pytest.raises(ValueError):
        coerce_config_value("limits.max_videos", "abc")


# Verify non-limits values remain strings.
def test_coerce_config_value_leaves_non_limits_as_string() -> None:
    assert coerce_config_value("models.text", "gpt-4.1-mini") == "gpt-4.1-mini"
