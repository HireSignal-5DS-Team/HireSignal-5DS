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
export type Mode = "MOCK" | "REAL";
export interface AnalysisInput {
  title: string;
  description: string;
  candidates: CV[];
}
export interface CandidateRecord {
  id: string;
  label: string;
  cv: CV;
  report: MatchReport;
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
