// Mirrors matcher/schemas.py v1.0.0 at integration commit fb68665.
// These are Matcher domain contracts, NOT an agreed FastAPI transport envelope.
export type Decision = "MET" | "MISSING" | "UNCERTAIN";
export interface CV {
  cv_id: string;
  text: string;
  structured: Record<string, unknown>;
}
export interface Requirement {
  req_id: string;
  text: string;
  kind: "must" | "nice";
  category:
    | "skill"
    | "experience"
    | "education"
    | "certification"
    | "language"
    | "other";
  skill_terms: string[];
  min_years: number | null;
}
export interface Job {
  job_id: string;
  title: string;
  requirements: Requirement[];
}
// Optional per-requirement verification data, populated only in REAL mode from
// PipelineOutput.requirements[] (contract 1.1.0). MOCK leaves these undefined.
export interface JudgeInfo {
  judge_verdict: "PASS" | "FAIL" | "UNCERTAIN" | "NOT_APPLICABLE";
  judge_score: number | null;
  model: string;
  requires_human_review: boolean;
  nli_probs?: Record<string, number> | null;
}
export interface BiasInfo {
  audit_status: "PASS" | "FLAGGED" | "NOT_TESTED" | string;
  counterfactual_flip: boolean | null;
  affected_attribute: string | null;
  requires_human_review: boolean;
}
export interface ValidatorInfo {
  review_priority: "low" | "medium" | "high";
  reasons: string[];
}

export interface RequirementResult {
  req_id: string;
  requirement_text: string;
  kind: "must" | "nice";
  decision: Decision;
  basis: "supported" | "contradicted" | "not_documented" | "ambiguous";
  evidence: string[];
  evidence_spans: [number, number][];
  explanation: string;
  rag_refs: string[];
  model_decision: Decision | null;
  review_priority: "low" | "medium" | "high";
  needs_human_review: boolean;
  review_reasons: string[];
  judge?: JudgeInfo | null;
  bias_audit?: BiasInfo | null;
  validator?: ValidatorInfo | null;
  citations?: Array<{
    source_id: string;
    source_type: string;
    title: string;
    url: string | null;
    retrieval: string;
  }>;
  matcher_call?: {
    used?: string;
    model?: string;
    latency_s?: number;
    error?: string | null;
    finish_reason?: string | null;
  };
  provenance?: {
    served_alias?: string;
    answered_by?: string | null;
    prompt_id?: string;
    knowledge_provider?: string;
    finish_reason?: string | null;
  };
}
export interface MatchReport {
  schema_version: string;
  cv_id: string;
  job_id: string;
  backend: Record<string, unknown>;
  results: RequirementResult[];
  summary: {
    counts: Record<Decision, number>;
    must_total: number;
    must_met: number;
    must_coverage: number | null;
    needs_human_review: number;
    note: string;
  };
}
// Optional HTTP presentation envelope from the Report Writer.
// This is not part of the Matcher domain MatchReport contract.
export interface ReporterData {
  schema_version: string;
  executive_summary: { text: string; writer: string };
  requirements: Array<{
    req_id: string;
    plain_note: { text: string; writer: string };
  }>;
  provenance: {
    slm_status: string;
    sections_total: number;
    sections_slm: number;
    sections_fallback: number;
    model: string | null;
    any_mock: boolean;
  };
  html?: string;
  markdown?: string;
}
export type Mode = "MOCK" | "REAL";
export interface AnalysisInput {
  title: string;
  description: string;
  candidates: CV[];
}
/** One upstream/downstream stage as it really ran on the backend (POST /api/v2/analyze). */
export interface StageInfo {
  stage: string;
  status: "running" | "ok" | "failed";
  elapsed_s?: number;
  error?: string;
  [key: string]: unknown;
}
export interface LiveV2Progress {
  candidate_index: number;
  candidate_total: number;
  status: "queued" | "running" | "failed" | "completed";
  stages: StageInfo[];
  elapsed_s: number;
}
export interface UpstreamInfo {
  job_title?: string;
  review_reasons?: string[];
  privacy?: { leaks_left?: number; placeholders?: Record<string, number> };
  job_card?: { requirements?: { req_id: string; text: string; kind: string; evidence: string; min_years?: number | null }[] };
  [key: string]: unknown;
}
export interface CandidateRecord {
  id: string;
  label: string;
  cv: CV;
  report: MatchReport;
  reporter?: ReporterData | null;
  stages?: StageInfo[];
  upstream?: UpstreamInfo;
  review: "Pending review" | "Reviewed" | "Follow-up needed";
  note: string;
}
export interface Campaign {
  id: string;
  title: string;
  created: string;
  mode: Mode;
  candidates: CandidateRecord[];
}
