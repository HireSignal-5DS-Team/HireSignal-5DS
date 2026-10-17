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


# ------------------------------------------------------------ step 4: parsed CV ---
# Same shape as the team's pipeline.schema.json ParsedCV. No name, photo, age, gender,
# nationality or contact field, by design: it is built from the anonymised text only.

YEAR_OR_MONTH = r"^\d{4}(-(0[1-9]|1[0-2]))?$"
YEAR_MONTH_OR_PRESENT = r"^(\d{4}(-(0[1-9]|1[0-2]))?|present)$"


class Skill(_Strict):
    name: str = Field(min_length=1, description="as written in the CV")
    evidence: str = Field(min_length=1, description="exact quote of the anonymised CV text")


class Education(_Strict):
    degree: str | None = None
    field: str | None = None
    institution: str | None = None
    end: str | None = Field(None, pattern=YEAR_OR_MONTH, description="YYYY or YYYY-MM")
    evidence: str = Field(min_length=1)


class Experience(_Strict):
    title: str | None = None
    company: str | None = None
    start: str | None = Field(None, pattern=YEAR_OR_MONTH)
    end: str | None = Field(None, pattern=YEAR_MONTH_OR_PRESENT, description="YYYY, YYYY-MM or 'present'")
    evidence: str = Field(min_length=1)


class ParsedCV(_Strict):
    schema_version: str = PROFILE_SCHEMA_VERSION
    candidate_id: str = Field(description="the random cv_id, never the person's name")
    skills: list[Skill] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    uncertain: list[str] = Field(default_factory=list, description="what the checks dropped or doubted, and why")
    prompt_version: str = ""
