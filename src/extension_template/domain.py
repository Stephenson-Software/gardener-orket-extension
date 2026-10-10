import re

from pydantic import BaseModel, ConfigDict, Field

from .errors import ExtensionError

# Put application instructions and deterministic product rules here.
SYSTEM_PROMPT = "You are a helpful assistant. Answer the requested task clearly and concisely."

AUDIT_SYSTEM_PROMPT = (
    "You are auditing a software repository for gardener. The task section is gardener's "
    "request. Each source section is a file or listing from the repository or its conventions, "
    "headed by a reference in square brackets such as [src01]. Base every statement only on "
    "those sources, say plainly what they do not show, and cite the source you relied on after "
    "each statement using its bracketed reference exactly, for example [src02]. Answer in "
    "Markdown in at most {words} words, most significant findings first. If the task asks for "
    "a closing summary line, end with it."
)

_CITATION = re.compile(r"\[(src\d{2}|listing)\]")


class GenerateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=16000)
    provider: str = Field(default="", max_length=64)
    model: str = Field(default="", max_length=128)
    max_tokens: int = Field(default=512, ge=1, le=8192)
    temperature: float = Field(default=0.2, ge=0, le=2)


class AuditSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str = Field(pattern=r"^(src\d{2}|listing)$")
    path: str = Field(min_length=1)
    text: str


class AuditInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: str = Field(min_length=1, max_length=64000)
    sources: list[AuditSource] = Field(min_length=1)
    provider: str = Field(default="", max_length=64)
    model: str = Field(default="", max_length=128)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    report_words: int = Field(default=250, ge=20, le=5000)


def require_output(text: str) -> str:
    if not text.strip():
        raise ExtensionError("E_EMPTY_OUTPUT", "The model returned no text.")
    return text


def audit_message(request: AuditInput) -> str:
    parts = [f"## Task\n\n{request.task.strip()}"]
    parts += [f"## Source [{source.ref}] {source.path}\n\n{source.text}" for source in request.sources]
    return "\n\n".join(parts)


def cited_sources(report: str, request: AuditInput) -> list[str]:
    """The report's citations, which must exist and must all be supplied sources.

    A report that cites nothing, or cites a source it was not given, is refused
    rather than returned: provenance is the one property this extension can check.
    """
    supplied = {source.ref for source in request.sources}
    cited = list(dict.fromkeys(_CITATION.findall(report)))
    unknown = sorted(set(re.findall(r"\[(src\d+)\]", report)) - supplied)
    if unknown:
        raise ExtensionError(
            "E_REPORT_UNKNOWN_SOURCE", f"The report cites sources it was not given: {unknown}."
        )
    if not cited:
        raise ExtensionError("E_REPORT_UNSOURCED", "The report cites none of the supplied sources.")
    return cited
