import pytest

from extension_template.errors import ExtensionError
from extension_template.host_runtime import HostRuntimeClient
from extension_template.settings import Settings, load_settings

pytestmark = pytest.mark.unit


def test_env_precedence_and_no_secret_representation(tmp_path):
    (tmp_path / ".env").write_text("EXTENSION_HOST_API_KEY=file-secret\nEXTENSION_TIMEOUT_SECONDS=25\n")
    (tmp_path / ".env.local").write_text(
        "EXTENSION_HOST_API_KEY=local-secret\nEXTENSION_TIMEOUT_SECONDS=50\n"
    )
    settings = load_settings(tmp_path, environ={"EXTENSION_HOST_API_KEY": "shell-secret"})
    assert settings.host_api_key == "shell-secret"
    assert settings.timeout_seconds == 50
    assert "secret" not in repr(settings)
    assert load_settings(tmp_path, environ={}).host_api_key == "local-secret"


def test_host_key_fallback_and_fail_closed(tmp_path):
    assert load_settings(tmp_path, environ={"ORKET_API_KEY": "fallback"}).host_api_key == "fallback"
    with pytest.raises(ExtensionError, match="Set EXTENSION_HOST_API_KEY"):
        HostRuntimeClient(load_settings(tmp_path, environ={}))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"host_base_url": "http://user:secret@localhost:8082"},
        {"host_base_url": "file:///tmp/host"},
        {"host_base_url": "http://localhost:8082/v1"},
        {"host_base_url": "http://localhost:8082?key=secret"},
        {"host_base_url": "http://localhost:0"},
        {"host_base_url": "http://localhost:99999"},
        {"extension_id": "../other"},
        {"extension_id": ".."},
        {"extension_id": ""},
        {"timeout_seconds": 0},
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": float("inf")},
    ],
)
def test_invalid_configuration_is_rejected(kwargs):
    with pytest.raises(ExtensionError):
        Settings(**kwargs)


def test_env_values_are_literal(tmp_path):
    (tmp_path / ".env").write_text("EXTENSION_HOST_API_KEY='literal-${HOME}'\n")
    assert load_settings(tmp_path, environ={}).host_api_key == "literal-${HOME}"
