from typing import Any


class ExtensionError(Exception):
    """Safe, stable error for CLI and HTTP consumers. Never include upstream bodies;
    the one exception is Orket's own typed error code, with its message only when
    that is plain names, numbers and punctuation (see host_runtime._http_failure)."""

    def __init__(self, code: str, message: str, *, status: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status

    def as_dict(self) -> dict[str, Any]:
        return {"ok": False, "error": {"code": self.code, "message": self.message}}
