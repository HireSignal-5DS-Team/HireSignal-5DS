"""Data contracts of the Matcher agent (Pydantic v2). JSON Schemas are exported to matcher/json_schemas/.

Decision semantics (requirement level, never a hiring decision):
- MET       the CV contains verbatim evidence that satisfies the requirement (basis = supported).
- MISSING   either the CV contradicts / falls short of the requirement (basis = contradicted, quote required)
            or the CV documents nothing about it (basis = not_documented). not_documented is absence of
            evidence, NOT proof that the candidate lacks the skill, so must-have cases go to human review.
- UNCERTAIN ambiguous, incomplete or unsupported inference (basis = ambiguous).
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0.0"
Decision = Literal["MET", "MISSING", "UNCERTAIN"]
Basis = Literal["supported", "contradicted", "not_documented", "ambiguous"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CV(_Strict):
    """Anonymized CV. `text` is the single source of truth for evidence quotes."""
    cv_id: str
    text: str = Field(min_length=1)
    structured: dict = Field(default_factory=dict, description="optional parsed fields from the CV reader; never used as evidence")


class Requirement(_Strict):
    req_id: str
    text: str = Field(min_length=1)
    kind: Literal["must", "nice"] = "must"
    category: Literal["skill", "experience", "education", "certification", "language", "other"] = "skill"
    skill_terms: list[str] = Field(default_factory=list, description="skill names used as retrieval queries")
    min_years: float | None = Field(None, ge=0)


class Job(_Strict):
    job_id: str
    title: str
    requirements: list[Requirement] = Field(min_length=1)


class KnowledgeRef(_Strict):
    """A retrieved knowledge item (ESCO / O*NET / job posting). Terminology only, never candidate evidence."""
    source_type: Literal["esco", "onet", "job", "fixture"]
    source_id: str
    title: str
    text: str
    url: str | None = None
    aliases: list[str] = Field(default_factory=list)
    relevance_score: float | None = Field(None, description="retriever rank score; not a probability")
    retrieval: str = Field(description="retriever that produced it, e.g. rag.bm25")


class ModelAnswer(_Strict):
    """What the SLM must emit for one requirement (strict JSON)."""
    decision: Decision
    basis: Basis
    evidence: list[str] = Field(default_factory=list, max_length=3)
    explanation: str = Field(max_length=600)


class RequirementResult(_Strict):
    req_id: str
    requirement_text: str
    kind: Literal["must", "nice"]
    decision: Decision
    basis: Basis
    evidence: list[str] = Field(description="verified verbatim substrings of CV.text")
    evidence_spans: list[tuple[int, int]] = Field(description="[start, end) offsets of each evidence quote in CV.text")
    explanation: str
    rag_refs: list[str] = Field(description="source_ids of knowledge used to interpret the requirement")
    model_decision: Decision | None = Field(description="raw model decision before deterministic validation; None if output unparseable")
    review_priority: Literal["low", "medium", "high"] = Field(
        description="heuristic review signal from validation rules; NOT a calibrated probability")
    needs_human_review: bool
    review_reasons: list[str]


class MatchSummary(_Strict):
    counts: dict[Decision, int]
    must_total: int
    must_met: int
    must_coverage: float | None = Field(description="must_met / must_total; transparent ratio, not a fit probability")
    needs_human_review: int
    note: str = "Requirement-level screening aid. No automatic rejection or hiring decision is made."


class MatchReport(_Strict):
    schema_version: str = SCHEMA_VERSION
    cv_id: str
    job_id: str
    backend: dict
    results: list[RequirementResult]
    summary: MatchSummary


def export_json_schemas(folder):
    import json
    from pathlib import Path

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for model in (CV, Job, KnowledgeRef, ModelAnswer, MatchReport):
        (folder / f"{model.__name__}.schema.json").write_text(json.dumps(model.model_json_schema(), indent=2) + "\n")


if __name__ == "__main__":
    from pathlib import Path

    export_json_schemas(Path(__file__).parent / "json_schemas")
