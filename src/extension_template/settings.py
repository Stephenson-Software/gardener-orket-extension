import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

from . import DEFAULT_EXTENSION_ID
from .errors import ExtensionError


@dataclass(frozen=True)
class Settings:
    host_base_url: str = "http://127.0.0.1:8082"
    extension_id: str = DEFAULT_EXTENSION_ID
    host_api_key: str = field(default="", repr=False)
    timeout_seconds: float = 300.0
    gateway_token: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        try:
            url = urlsplit(self.host_base_url)
            valid_url = (
                url.scheme in {"http", "https"}
                and url.hostname
                and not url.username
                and not url.password
                and not url.query
                and not url.fragment
                and url.path in {"", "/"}
                and url.port != 0
            )
        except ValueError:
            valid_url = False
        if not valid_url:
            raise ExtensionError(
                "E_CONFIG_URL", "Host URL must be an HTTP(S) origin without credentials.", status=503
            )
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", self.extension_id) or self.extension_id in {".", ".."}:
            raise ExtensionError("E_CONFIG_ID", "Invalid extension ID.", status=503)
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ExtensionError("E_CONFIG_TIMEOUT", "Timeout must be a positive finite number.", status=503)

    def require_host_key(self) -> None:
        if not self.host_api_key.strip():
            raise ExtensionError(
                "E_HOST_KEY_REQUIRED", "Set EXTENSION_HOST_API_KEY or ORKET_API_KEY.", status=503
            )


def load_settings(directory: Path | None = None, *, environ: Mapping[str, str] | None = None) -> Settings:
    """Read only the selected directory; never mutate the process environment."""
    root = directory if directory is not None else Path.cwd()
    values = {
        **dotenv_values(root / ".env", interpolate=False),
        **dotenv_values(root / ".env.local", interpolate=False),
        **(os.environ if environ is None else environ),
    }

    def value(name: str, default: str = "") -> str:
        return str(values.get(name) or default).strip()

    try:
        timeout = float(value("EXTENSION_TIMEOUT_SECONDS", "300"))
    except ValueError as exc:
        raise ExtensionError("E_CONFIG_TIMEOUT", "Timeout must be numeric.", status=503) from exc
    return Settings(
        host_base_url=value("EXTENSION_HOST_BASE_URL", "http://127.0.0.1:8082"),
        extension_id=value("EXTENSION_ID", DEFAULT_EXTENSION_ID),
        host_api_key=value("EXTENSION_HOST_API_KEY") or value("ORKET_API_KEY"),
        timeout_seconds=timeout,
        gateway_token=value("EXTENSION_GATEWAY_TOKEN"),
    )
