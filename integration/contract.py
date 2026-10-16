"""HireSignal integration contract v1.1 (owner: S6). Frozen interface between the three subsystems.

    Ayoub (upstream)          ->  CV + Job (matcher/schemas.py, v1.0.0, unchanged)
    Semah (Matcher -> RAG -> Validator -> Bias Auditor -> Judge -> Report)  ->  PipelineOutput (this file)
    Dali (FastAPI / Docker)   consumes PipelineOutput as the API response body

Upstream adapters convert Ayoub's outputs without importing his code:
- CV Reader `ReaderResult.to_dict()` (agents/reader/reader.py)      -> `cv_from_reader()`
- Job Agent `JobRequirements` card, schema 0.1.0 (contracts/job_requirements.py) -> `job_from_card()`
Requirement ids (r1, r2, ...) and evidence quotes are carried unchanged through every stage.

Export the JSON Schemas:  python -m integration.contract   (writes integration/schemas/)
"""
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from matcher.schemas import CV, Job, MatchReport

CONTRACT_VERSION = "1.1.0"
Decision = Literal["MET", "MISSING", "UNCERTAIN"]


class _Open(BaseModel):
    """Stage payloads may gain fields (new Judge/Reporter versions) without breaking consumers."""
    model_config = ConfigDict(extra="allow")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValidatorOut(_Strict):
    review_priority: Literal["low", "medium", "high"]
    reasons: list[str]


class BiasOut(_Open):
    audit_status: str = Field(description="PASS | FLAGGED | NOT_TESTED")
    counterfactual_flip: bool | None = None
    affected_attribute: str | None = None
    requires_human_review: bool = False


class JudgeOut(_Open):
    judge_verdict: str = Field(description="PASS | FAIL | UNCERTAIN | NOT_APPLICABLE")
    judge_score: float | None = Field(None, description="NLI score of the deciding label; NOT a probability that the decision is correct")
    nli_probs: dict | None = Field(None, description="entailment / neutral / contradiction softmax scores")
    requires_human_review: bool
    model: str


class Citation(_Strict):
    source_id: str
    source_type: str
    title: str
    url: str | None = None
    retrieval: str


class RequirementRow(_Open):
    """One requirement after every stage. Never a hiring decision."""
    req_id: str
    requirement_text: str
    kind: Literal["must", "nice"]
    final_decision: Decision
    model_decision: Decision | None = Field(description="raw Matcher decision before deterministic validation")
    basis: str
    evidence: list[str] = Field(description="verbatim substrings of CV.text")
    evidence_spans: list[tuple[int, int]]
    explanation: str = Field(description="grounded explanation built from validated content only")
    explanation_model: str = Field("", description="the Matcher model's own text, kept for audit")
    rag_refs: list[str] = Field(description="source_ids of the knowledge SHOWN to the model (not candidate evidence)")
    citations: list[Citation] = Field(default_factory=list)
    validator: ValidatorOut
    bias_audit: BiasOut
    judge: JudgeOut | None
    requires_human_review: bool
    review_reasons: list[str]
    provenance: dict = Field(default_factory=dict, description="model that answered THIS requirement")


class Summary(_Strict):
    MET: int
    MISSING: int
    UNCERTAIN: int
    must_met: int
    must_total: int
    requires_human_review: int
    note: str


class PipelineOutput(_Open):
    """Response of `matcher.pipeline.Pipeline.run(cv, job)` (and of Dali's API)."""
    contract_version: str = CONTRACT_VERSION
    cv_id: str
    job_id: str
    parser: str
    backend: dict
    knowledge: str
    match_report: MatchReport
    judge: str | None
    requirements: list[RequirementRow]
    summary: Summary


def validate_output(out: dict) -> PipelineOutput:
    return PipelineOutput.model_validate(out)


def cv_from_reader(reader: dict, cv_id: str) -> CV:
    """Ayoub's ReaderResult.to_dict() -> Matcher CV. `text` stays the single evidence source; the reader's sections
    and quality signals go to `structured` (never used as evidence)."""
    keep = ("file_name", "file_type", "sections", "pages", "page_routes", "layout", "ocr_confidence",
            "needs_human_review", "warnings")
    return CV(cv_id=cv_id, text=reader["text"], structured={"reader": {k: reader.get(k) for k in keep}})


def job_from_card(card: dict) -> Job:
    """Ayoub's JobRequirements card (0.1.x) -> Matcher Job. Same as its to_matcher_job(); the job-post quote of each
    requirement is not a Matcher field, so it is dropped here and kept by the caller if needed."""
    if not str(card.get("schema_version", "0.1.0")).startswith("0.1"):
        raise ValueError(f"unsupported job card schema {card.get('schema_version')!r}; expected 0.1.x")
    fields = ("req_id", "text", "kind", "category", "skill_terms", "min_years")
    return Job(job_id=card["job_id"], title=card["title"],
               requirements=[{k: r[k] for k in fields if k in r} for r in card["requirements"]])


def export(folder=Path(__file__).parent / "schemas"):
    folder.mkdir(parents=True, exist_ok=True)
    for name, model in {"CV": CV, "Job": Job, "PipelineOutput": PipelineOutput}.items():
        (folder / f"{name}.schema.json").write_text(json.dumps(model.model_json_schema(), indent=2) + "\n")
    return folder


if __name__ == "__main__":
    print(export())
