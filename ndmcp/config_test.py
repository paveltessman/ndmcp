import pytest

from ndmcp.config import ConfigError
from ndmcp.config import load_settings

REQUIRED = {
    "NDMCP_URL": "https://music.example.com",
    "NDMCP_USERNAME": "user",
    "NDMCP_PASSWORD": "hunter2",
}


def test_required_only_gives_defaults():
    settings = load_settings(REQUIRED)

    assert str(settings.url) == "https://music.example.com/"
    assert settings.username == "user"
    assert settings.password.get_secret_value() == "hunter2"
    assert settings.timeout == 10.0
    assert settings.cache_ttl == 300.0
    assert settings.verify_tls is True
    assert settings.log_level == "INFO"


def test_optional_values_are_parsed():
    settings = load_settings(
        REQUIRED
        | {
            "NDMCP_TIMEOUT": "2.5",
            "NDMCP_CACHE_TTL": "0",
            "NDMCP_VERIFY_TLS": "false",
            "NDMCP_LOG_LEVEL": "debug",
        }
    )

    assert settings.timeout == 2.5
    assert settings.cache_ttl == 0
    assert settings.verify_tls is False
    assert settings.log_level == "DEBUG"


def test_empty_value_uses_default():
    settings = load_settings(REQUIRED | {"NDMCP_TIMEOUT": ""})

    assert settings.timeout == 10.0


def test_missing_values_are_named():
    with pytest.raises(ConfigError) as info:
        load_settings({"NDMCP_URL": "https://music.example.com"})

    assert str(info.value) == ("NDMCP_USERNAME is not set.\nNDMCP_PASSWORD is not set.")


def test_bad_values_are_named():
    with pytest.raises(ConfigError) as info:
        load_settings(REQUIRED | {"NDMCP_URL": "music", "NDMCP_TIMEOUT": "0"})

    message = str(info.value)
    assert "NDMCP_URL is not valid" in message
    assert "NDMCP_TIMEOUT is not valid" in message


def test_password_is_not_in_error_or_repr():
    with pytest.raises(ConfigError) as info:
        load_settings(REQUIRED | {"NDMCP_TIMEOUT": "hunter2"})

    assert "hunter2" not in str(info.value)
    assert "hunter2" not in repr(load_settings(REQUIRED))
