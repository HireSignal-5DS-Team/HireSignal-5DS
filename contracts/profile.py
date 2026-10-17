"""Profile Agent output contracts (schema 0.1.0).

Two files per CV, on purpose kept apart:

- `Identity`        -> <cv_id>.identity.json : who the candidate is. Stays on the
                       recruiter's machine. NEVER sent to n8n, the Matcher or an API.
- `PrivacyReport`   -> inside the Matcher CV (`structured.privacy`): what was hidden,
                       as counts only. It contains no personal value.

The Matcher CV itself is the team's `{"cv_id", "text", "structured"}` (matcher/schemas.py);
`text` is the anonymised CV, the only evidence source for the Matcher.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROFILE_SCHEMA_VERSION = "0.1.0"

ProxyKind = Literal["DOB", "AGE", "GENDER", "HONORIFIC", "NATIONALITY", "MARITAL", "BIRTHPLACE", "RELIGION"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PersonalItem(_Strict):
    kind: ProxyKind
    value: str


class Identity(_Strict):
    """The candidate's identity, found in the CV. Local only."""
    schema_version: str = PROFILE_SCHEMA_VERSION
    cv_id: str
    name: str | None = Field(None, description="as written in the CV; None if not found")
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list, description="LinkedIn, GitHub, portfolio, social handles")
    addresses: list[str] = Field(default_factory=list)
    personal: list[PersonalItem] = Field(default_factory=list, description="bias proxies, hidden as [PERSONAL]")


class PrivacyReport(_Strict):
    """What the anonymisation did. Counts and flags only: safe to send to the Matcher."""
    schema_version: str = PROFILE_SCHEMA_VERSION
    placeholders: dict[str, int] = Field(description="e.g. {'[NAME]': 3, '[EMAIL]': 1}")
    detectors: list[str] = Field(description="'rules' plus any NER model that really ran")
    name_found: bool
    leaks_fixed: int = Field(description="identity pieces the leak check found after masking, then hid")
    leaks_left: int = Field(description="must be 0; otherwise needs_human_review")
    needs_human_review: bool
    warnings: list[str] = Field(default_factory=list, description="never contain a personal value")
