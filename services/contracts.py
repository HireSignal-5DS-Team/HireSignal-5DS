"""JSON contracts of the station API (services/api.py). Station data models stay in their station packages:
ParsedCV / PrivacyReport (services/profile/contracts.py), JobRequirements (services/job/contracts.py).

No response model has a field for identity values (name, contacts) or raw CV text: the Reader writes the raw text to
private/<cv_id>.reader.json and the Profile station reads it from there (no raw CV text passes through n8n); the
identity is written only to private/<cv_id>.json. All files under private/ are git-ignored.

Two flag lists in every station response: `review_reasons` (send the case to human review) and `info_flags`
(shown to the reviewer, never block).
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from services.job.contracts import Category, JobRequirements, Kind
from services.profile.contracts import ParsedCV, PrivacyReport

CV_ID = r"^cv-[0-9a-f]{8}$"  # services/profile/anonymise.new_cv_id; also guards the private/<cv_id>.json path
Decision = Literal["MET", "MISSING", "UNCERTAIN"]
Basis = Literal["supported", "contradicted", "not_documented", "ambiguous"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Health(_Strict):
    status: str
    checks: dict[str, str] = Field(default_factory=dict)


class ReaderOut(_Strict):
    cv_id: str = Field(pattern=CV_ID, description="random, never derived from the file or the person")
    file_type: str
    text_chars: int = Field(description="length of the raw text kept in private/<cv_id>.reader.json")
    sections: dict[str, int] = Field(description="section name -> characters (the text stays private)")
    read_path: list[str] = Field(description="per page: 'text' (text layer / docx / txt), or for image pages the route "
                                             "of the reader mode: 'ocr' | 'vision' | 'late' | 'early' | 'ocr (vision fallback)'")
    mode: str = Field(description="reader mode used for image pages (T10): ocr | vision | late | early")
    pages: list[dict] = Field(default_factory=list, description="per page: route, vision model + latency, [unclear] "
                              "share, late-fusion counts and number of low-trust lines (their text stays private)")
    layout: str
    ocr_confidence: float | None
    needs_human_review: bool
    warnings: list[str]
    review_reasons: list[str]
    info_flags: list[str]
    elapsed_s: float


class ProfileIn(_Strict):
    cv_id: str = Field(pattern=CV_ID, description="from /reader: the raw text is loaded from private/<cv_id>.reader.json")


class ProfileOut(_Strict):
    cv_id: str
    anonymised_text: str = Field(description="the only CV text the Matcher sees")
    privacy: PrivacyReport = Field(description="counts and flags only")
    injection_removed: list[str] = Field(default_factory=list, description="T14: prompt-injection sentences removed "
                                         "from the text before the models (shown to the recruiter, never to a model)")
    bias_flags: list[dict] = Field(default_factory=list, description="T11 Bias Auditor leakage check: protected lines "
                                   "removed / words masked before the Matcher (kind, rule, line; never the text)")
    profile: ParsedCV
    review_reasons: list[str]
    info_flags: list[str]
    elapsed_s: float


class JobIn(_Strict):
    job_text: str = Field(min_length=1)
    job_id: str | None = None


class InjectionFlags(_Strict):
    injected_sentences: list[str]
    dropped_req_ids: list[str]


class JobOut(_Strict):
    card: JobRequirements
    injection: InjectionFlags
    review_reasons: list[str]
    info_flags: list[str]
    elapsed_s: float


class RequirementIn(_Strict):
    req_id: str
    text: str = Field(min_length=1)
    kind: Kind = "must"
    category: Category = "skill"
    skill_terms: list[str] = Field(default_factory=list)
    min_years: float | None = Field(None, ge=0)


class KnowledgeRef(BaseModel):
    """One ESCO knowledge entry (from /rag/search). Terminology only, never evidence."""
    source_id: str
    title: str
    text: str = Field(max_length=2000)
    url: str | None = None
    aliases: list[str] = Field(default_factory=list)
    relevance_score: float | None = None


class MatchIn(_Strict):
    cv_text: str = Field(min_length=1, description="ANONYMISED CV text (ProfileOut.anonymised_text)")
    requirement: RequirementIn
    cv_id: str | None = Field(None, pattern=CV_ID)
    knowledge_refs: list[KnowledgeRef] | None = Field(None, description="T09: refs from /rag/search; [] = no knowledge "
                                                                         "block; absent = the built-in BM25 lookup")
    knowledge: str | None = Field(None, description="name of the retriever that produced knowledge_refs")


class RagSearchIn(_Strict):
    requirement: RequirementIn
    cv_text: str | None = Field(None, description="ANONYMISED CV text; only used for the 'retrieve only when the "
                                                  "terms are not in the CV' rule, never as a query")
    k: int = Field(3, ge=1, le=10)


class RagSearchOut(_Strict):
    knowledge_refs: list[KnowledgeRef]
    retriever: str
    skipped: bool = Field(description="True when the requirement's terms are already in the CV (no knowledge needed)")
    elapsed_s: float


class Quote(_Strict):
    quote: str
    start: int = Field(description="[start, end) offsets in cv_text, verified by code")
    end: int


class KnowledgeRefOut(_Strict):
    source_id: str
    title: str


class ModelInfo(_Strict):
    name: str
    backend: str
    lora_scale: float | None
    latency_s: float
    finish_reason: str | None = Field(description="'length' = cut at max_tokens")
    max_tokens: int


class MatchOut(_Strict):
    req_id: str
    decision: Decision
    basis: Basis
    evidence: list[Quote]
    explanation: str
    model_decision: Decision | None = Field(description="the model's own decision before validation; None if invalid")
    evidence_years: float | None = Field(description="years code read in the quotes (only when min_years is set)")
    review_reasons: list[str]
    info_flags: list[str]
    needs_human_review: bool
    knowledge_refs: list[KnowledgeRefOut] = Field(description="terminology only, never evidence")
    model: ModelInfo
    confidence: dict | None = Field(None, description="label probabilities at the decision token (model decision, "
                                    "before validation); None if logprobs were not returned")
    prompt_id: str
    schema_: str = Field(alias="schema")
    knowledge: str
    elapsed_s: float

    model_config = ConfigDict(extra="forbid", populate_by_name=True, protected_namespaces=())


class JudgeIn(_Strict):
    cv_text: str = Field(min_length=1, description="ANONYMISED CV text, the same text /match saw")
    requirement: RequirementIn
    match: MatchOut


class JudgeFinding(_Strict):
    verdict: Literal["PASS", "FAIL", "UNCERTAIN", "NOT_APPLICABLE"]
    score: float | None = Field(description="NLI score that decided the verdict; not P(Matcher correct)")
    nli_probs: dict[str, float] | None
    premise_kind: str | None = Field(description="quotes | cv | none | None (not applicable) | error")
    notes: list[str]
    error: str | None
    review_reasons: list[str]
    provenance: dict


class JudgeOut(MatchOut):
    """The /match result passed through, with the Judge's review reasons added; the decision is never changed."""
    judge: JudgeFinding


class OutcomeRequirement(BaseModel):
    """One requirement result of the pair (the /match + /judge output; extra fields are ignored)."""
    req_id: str
    kind: Kind
    decision: Decision
    review_reasons: list[str] = Field(default_factory=list)
    info_flags: list[str] = Field(default_factory=list)
    category: Category | None = None
    confidence: dict[str, float] | None = Field(None, description="normalized label probabilities (/match confidence)")
    judge: dict | None = Field(None, description="the /judge finding (verdict, nli_probs)")
    min_years: float | None = None
    evidence_years: float | None = None


class OutcomeIn(_Strict):
    requirements: list[OutcomeRequirement] = Field(min_length=1)
    pair_review_reasons: list[str] = Field(default_factory=list, description="reader/profile/job review reasons")
    pair_info_flags: list[str] = Field(default_factory=list)
    cv_id: str | None = Field(None, pattern=CV_ID)
    job_id: str | None = None


class OutcomeOut(_Strict):
    outcome: Literal["invite", "review", "reject"]
    rule: str
    score: int
    reasons: list[str]
    listed_flags: list[str]
    must: dict[str, int]
    settings: dict
    message: str | None
    cv_id: str | None
    job_id: str | None


class BiasIn(_Strict):
    """Station 5 input: the pair's requirement card + the /match + /judge results (T11)."""
    cv_id: str = Field(pattern=CV_ID, description="the raw Reader text is loaded from private/<cv_id>.reader.json")
    requirements: list[RequirementIn] = Field(min_length=1, description="the requirement card used for /match")
    results: list[OutcomeRequirement] = Field(min_length=1, description="the /match + /judge results of the pair")
    pair_review_reasons: list[str] = Field(default_factory=list)


class BiasOut(_Strict):
    cv_id: str
    bias_flags: list[dict] = Field(description="leakage check: protected lines removed / words masked (no text)")
    would_be_outcome: Literal["invite", "review", "reject"] = Field(description="the gate's outcome before the audit")
    swap: dict = Field(description="live swap test: ran / skipped (why), counterfactual, identical Matcher input, "
                                   "changed must-haves, latency")
    review_reasons: list[str] = Field(description="['bias:swap_flip'] when a must-have decision changed, else []")
    info_flags: list[str]
    elapsed_s: float


class ReportRequirement(BaseModel):
    """One requirement of the decision record (station 7, T12): card fields + the /match + /judge result."""
    req_id: str
    kind: Kind
    text: str
    decision: Decision
    quotes: list[str] = Field(default_factory=list, description="the verified CV quotes (anonymised text)")
    judge: str | None = Field(None, description="Judge verdict: PASS / FAIL / UNCERTAIN / NOT_APPLICABLE")
    review_reasons: list[str] = Field(default_factory=list)
    skill_terms: list[str] = Field(default_factory=list)
    min_years: float | None = None
    evidence_years: float | None = None


class ReportIn(_Strict):
    """The anonymised decision record of one pair: no identity, no CV text except the verified quotes."""
    requirements: list[ReportRequirement] = Field(min_length=1)
    outcome: dict = Field(description="the /outcome result: outcome, score, rule, reasons")
    reader: dict = Field(default_factory=dict, description="mode + review_reasons of /reader")
    bias: dict = Field(default_factory=dict, description="review_reasons + swap of /bias")
    job_title: str | None = None
    cv_id: str | None = Field(None, pattern=CV_ID)
    decided_by: Literal["gate", "human"] = Field("gate", description="T13: 'human' = a recruiter decided after review "
                                                 "(outcome = the recruiter's decision): not an automated decision")


class ReportOut(_Strict):
    cv_id: str | None
    report: dict = Field(description="recruiter_summary, requirements, candidate_letter, flags_for_recruiter "
                                     "(services/report/schema.json), checked by services/report/checker.py")
    source: Literal["llm", "template"]
    attempts: int
    first_errors: list[str]
    retry_errors: list[str]
    info_flags: list[str]
    model: str
    elapsed_s: float
