"""Report contract (Pydantic v2) of the HireSignal Report Writer. JSON Schema exported to reporter/json_schemas/.

The report is built from the Pipeline.run() output only (matcher/pipeline.py). Every natural-language text field
carries the name of the writer that produced it (`TextSection.writer`): the deterministic renderer, the tiny SLM
(after validation), or the deterministic fallback after the SLM text was rejected. A fallback is never labelled SLM.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

REPORT_SCHEMA_VERSION = "1.0.0"
DISCLAIMER = ("Decision support only. This report checks job requirements against the text of an anonymised CV. "
              "It is not a hiring decision and makes no recommendation about the person. A human reviewer makes "
              "every decision, and must check each item flagged for review.")

Writer = Literal["deterministic", "slm", "slm_mock", "deterministic_fallback"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextSection(_Strict):
    text: str
    writer: Writer = Field(description="who wrote `text`: deterministic template, validated SLM output, a scripted "
                                       "test double (slm_mock, never a model), or the deterministic fallback used "
                                       "after the SLM output was rejected")
    model: str | None = Field(None, description="SLM id@revision when writer == 'slm' (or attempted for a fallback)")
    attempts: int = Field(0, description="SLM generations tried for this section (0 = SLM not used)")
    rejections: list[str] = Field(default_factory=list, description="validator reasons for each rejected SLM attempt")
    rejected_outputs: list[str] = Field(default_factory=list, description="raw SLM text of each rejected attempt "
                                                                          "(audit only, never shown as report text)")
    latency_s: float | None = None


class Evidence(_Strict):
    quote: str = Field(description="verbatim substring of the CV text (verified by the Matcher validator)")
    span: tuple[int, int] = Field(description="[start, end) character offsets in the CV text")


class KnowledgeShown(_Strict):
    source_id: str
    source_type: str | None = None
    title: str | None = None
    url: str | None = None
    retrieval: str | None = None
    label: Literal["knowledge shown to the model"] = "knowledge shown to the model"


class JudgeView(_Strict):
    verdict: str = Field(description="PASS | FAIL | UNCERTAIN | NOT_APPLICABLE | not run")
    score: float | None = None
    nli_probs: dict | None = None
    model: str | None = None
    disagrees: bool | None = None
    error: str | None = None


class BiasView(_Strict):
    audit_status: str
    counterfactual_flip: bool | None = None
    affected_attribute: str | None = None
    leakage_terms: list[str] = Field(default_factory=list)
    demographic_evidence: bool = False
    requires_human_review: bool = False


class ModelView(_Strict):
    answered_by: str | None = Field(description="primary | fallback | single | None (no model answered)")
    model_id: str | None = None
    served_alias: str | None = None
    adapter: str | None = Field(None, description="adapter repo@sha, or None")
    prompt_id: str | None = None
    knowledge_provider: str | None = None
    mock: bool = False
    replayed_from: str | None = Field(None, description="set when a saved LIVE model output was replayed (no new call)")


class RequirementSection(_Strict):
    req_id: str
    requirement_text: str
    kind: Literal["must", "nice"]
    decision: Literal["MET", "MISSING", "UNCERTAIN"]
    model_decision: Literal["MET", "MISSING", "UNCERTAIN"] | None
    basis: str
    evidence: list[Evidence]
    knowledge_shown: list[KnowledgeShown]
    validator_reasons: list[str]
    bias_audit: BiasView
    judge: JudgeView
    requires_human_review: bool
    review_reasons: list[str]
    model: ModelView
    explanation: TextSection = Field(description="deterministic grounded explanation from the pipeline")
    plain_note: TextSection = Field(description="one-sentence plain-language note (SLM if validated, else template)")


class Overview(_Strict):
    cv_id: str
    job_id: str
    job_title: str | None = Field(None, description="only when given by the caller; the pipeline output has none")
    counts: dict[str, int]
    must_met: int
    must_total: int
    requires_human_review: int


class ReporterProvenance(_Strict):
    report_schema_version: str = REPORT_SCHEMA_VERSION
    renderer: str
    slm: dict | None = Field(None, description="model id, revision, file, sha256, licence, runtime, decoding, "
                                               "prompt id + sha256; None when the SLM layer is off")
    slm_status: str = Field(description="off | on | unavailable: <reason>")
    sections_total: int
    sections_slm: int
    sections_fallback: int
    pipeline: dict = Field(description="pipeline backend / knowledge / judge / parser as given in the input")
    any_mock: bool


class Report(_Strict):
    schema_version: str = REPORT_SCHEMA_VERSION
    disclaimer: str = DISCLAIMER
    overview: Overview
    executive_summary: TextSection
    requirements: list[RequirementSection]
    provenance: ReporterProvenance


def export_json_schema(folder):
    import json
    from pathlib import Path

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "Report.schema.json").write_text(json.dumps(Report.model_json_schema(), indent=2) + "\n")


if __name__ == "__main__":
    from pathlib import Path

    export_json_schema(Path(__file__).parent / "json_schemas")
