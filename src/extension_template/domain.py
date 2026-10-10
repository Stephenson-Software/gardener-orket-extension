from pydantic import BaseModel, ConfigDict, Field

from .errors import ExtensionError

# Put application instructions and deterministic product rules here.
SYSTEM_PROMPT = "You are a helpful assistant. Answer the requested task clearly and concisely."


class GenerateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=16000)
    provider: str = Field(default="", max_length=64)
    model: str = Field(default="", max_length=128)
    max_tokens: int = Field(default=512, ge=1, le=8192)
    temperature: float = Field(default=0.2, ge=0, le=2)


def require_output(text: str) -> str:
    if not text.strip():
        raise ExtensionError("E_EMPTY_OUTPUT", "The model returned no text.")
    return text
