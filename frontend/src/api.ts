import type {
  AnalysisInput,
  BiasInfo,
  Campaign,
  CandidateRecord,
  CV,
  Job,
  JudgeInfo,
  MatchReport,
  Mode,
  RequirementResult,
  ValidatorInfo,
} from "./contracts";

export const mode: Mode =
  import.meta.env.VITE_EXECUTION_MODE === "REAL" ? "REAL" : "MOCK";
export const stages = [
  "CV Reader",
  "Profile & Job Analysis",
  "RAG Retrieval",
  "Matcher",
  "Judge",
  "Bias Auditor",
  "Report Writer",
];
export const sampleJob =
  "React\nTypeScript\nAccessible interfaces\nAutomated testing\nDesign systems";
export const sampleCV =
  "Built production interfaces with React and TypeScript.\nDelivered accessible interfaces with keyboard navigation.\nCreated reusable design systems for product teams.\nCurrently learning automated testing.";
export const MAX_TEXT = 50000;
export function validateInput(input: AnalysisInput) {
  if (!input.title.trim()) throw new Error("Add a role title.");
  if (input.description.trim().length < 3)
    throw new Error("Add a job description or at least one requirement.");
  if (input.description.length > MAX_TEXT)
    throw new Error("Job description must be 50,000 characters or fewer.");
  if (!input.candidates.length || input.candidates.length > 10)
    throw new Error("Add between 1 and 10 candidates.");
  if (input.candidates.some((c) => !c.text.trim() || c.text.length > MAX_TEXT))
    throw new Error("Each CV needs text, up to 50,000 characters.");
}
export { readCVFile } from "./cv-files";
export function demoJob(input: AnalysisInput): Job {
  return {
    job_id: "job-demo",
    title: input.title,
    requirements: input.description
      .split(/\n/)
      .map((s) => s.trim())
      .filter(Boolean)
      .map((text, i) => ({
        req_id: `r${i + 1}`,
        text,
        kind: "must",
        category: "skill",
        skill_terms: [text],
        min_years: null,
      })),
  };
}
export function mockReport(cv: CV, job: Job): MatchReport {
  const results: RequirementResult[] = job.requirements.map((req) => {
    const line = cv.text
      .split("\n")
      .find((l) => l.toLowerCase().includes(req.text.toLowerCase()));
    // Deliberately conservative demo: lexical mention is not proof of competence.
    const exact = line?.trim().toLowerCase() === req.text.toLowerCase();
    const decision = line ? (exact ? "MET" : "UNCERTAIN") : "MISSING";
    const start = line
      ? Array.from(cv.text.slice(0, cv.text.indexOf(line))).length
      : 0;
    return {
      req_id: req.req_id,
      requirement_text: req.text,
      kind: req.kind,
      decision,
      basis:
        decision === "MET"
          ? "supported"
          : line
            ? "ambiguous"
            : "not_documented",
      evidence: line ? [line] : [],
      evidence_spans: line ? [[start, start + Array.from(line).length]] : [],
      explanation: line
        ? "DEMO lexical match only. A reviewer must verify context, proficiency, negation and duration."
        : "This exact requirement is not documented in the demo text search. This does not establish that the candidate lacks it.",
      rag_refs: [],
      model_decision: null,
      review_priority: "high",
      needs_human_review: true,
      review_reasons: [
        "Simulated analysis; independent human verification required.",
      ],
    };
  });
  const counts = { MET: 0, MISSING: 0, UNCERTAIN: 0 };
  results.forEach((r) => counts[r.decision]++);
  return {
    schema_version: "1.0.0",
    cv_id: cv.cv_id,
    job_id: job.job_id,
    backend: {
      mode: "MOCK",
      model: "none",
      implementation: "deterministic-lexical-demo-v1",
      judge: "not_executed",
      bias_auditor: "not_executed",
      rag: "not_executed",
    },
    results,
    summary: {
      counts,
      must_total: results.length,
      must_met: counts.MET,
      must_coverage: results.length ? counts.MET / results.length : null,
      needs_human_review: results.length,
      note: "Requirement-level screening aid. No automatic rejection or hiring decision is made.",
    },
  };
}
export function demoCampaign(
  input: AnalysisInput,
  id: string,
  created: string,
): Campaign {
  validateInput(input);
  const job = demoJob(input);
  return {
    id,
    title: input.title,
    created,
    mode: "MOCK",
    candidates: input.candidates.map((cv, i) => ({
      id: `${id}-${i + 1}`,
      label: `Candidate ${String(i + 1).padStart(2, "0")}`,
      cv,
      report: mockReport(cv, job),
      review: "Pending review",
      note: "",
    })),
  };
}
export function seedCampaign(): Campaign {
  return demoCampaign(
    {
      title: "Frontend Engineer",
      description: sampleJob,
      candidates: [
        {
          cv_id: "sample-01",
          text: "React\nTypeScript\nAccessible interfaces\nBuilt and maintained design systems.",
          structured: {},
        },
        { cv_id: "sample-02", text: sampleCV, structured: {} },
        {
          cv_id: "sample-03",
          text: "TypeScript\nAutomated testing\nBuilt server-rendered dashboards using React.",
          structured: {},
        },
      ],
    },
    "sample",
    "2026-10-16T09:00:00Z",
  );
}

export class ApiError extends Error {}
export class ApiClient {
  constructor(
    private base = import.meta.env.VITE_API_BASE_URL ?? "",
    private timeoutMs = 20000,
  ) {}
  async request(path: string, options: RequestInit = {}): Promise<unknown> {
    if (!this.base)
      throw new ApiError("Set VITE_API_BASE_URL to connect to the backend.");
    let url: URL;
    try {
      url = new URL(this.base);
    } catch {
      throw new ApiError("VITE_API_BASE_URL must be an absolute HTTP(S) URL.");
    }
    if (!["http:", "https:"].includes(url.protocol))
      throw new ApiError("Use an HTTP(S) backend URL.");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await fetch(`${this.base.replace(/\/$/, "")}${path}`, {
        ...options,
        signal: controller.signal,
        headers: { Accept: "application/json", ...options.headers },
      });
      if (!response.ok)
        throw new ApiError(
          `Backend returned HTTP ${response.status}. Check service readiness and request validation.`,
        );
      const text = await response.text();
      if (!text.trim())
        throw new ApiError("Backend returned an empty response.");
      try {
        const data: unknown = JSON.parse(text);
        if (data === null || typeof data !== "object") throw new Error();
        return data;
      } catch {
        throw new ApiError(
          "Backend returned unexpected JSON. An object or array was expected.",
        );
      }
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (controller.signal.aborted)
        throw new ApiError("The backend request timed out. Please retry.");
      throw new ApiError(
        "Cannot reach the backend. Check the URL, connection and backend CORS configuration.",
      );
    } finally {
      clearTimeout(timer);
    }
  }
  health() {
    return this.request("/health");
  }
  ready() {
    return this.request("/ready");
  }
  models() {
    return this.request("/api/v1/models/status");
  }
  // Deliberately unknown: an HTTP envelope is not defined on the integration branch.
  // Wire this transport through a verified FastAPI adapter before enabling REAL matching.
  match(payload: unknown) {
    return this.request("/api/v1/match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }
}
export interface AnalysisAdapter {
  run(input: AnalysisInput): Promise<Campaign>;
}

// POST /api/v1/match expects {cv, job} and returns a PipelineOutput (contract 1.1.0).
// Its match_report field is a MatchReport (schema 1.0.0) — exactly what the UI consumes.
// Its requirements[] field (contract 1.1.0 RequirementRow[]) carries Judge, Bias and
// validator findings that are NOT in match_report; we merge them by req_id so the UI
// renders real verification instead of static "Not executed" placeholders.
interface PipelineRequirementRow {
  req_id: string;
  judge?: JudgeInfo | null;
  bias_audit?: BiasInfo | null;
  validator?: ValidatorInfo | null;
}
interface PipelineOutput {
  contract_version?: string;
  cv_id: string;
  job_id: string;
  match_report: MatchReport;
  requirements?: PipelineRequirementRow[];
  _meta?: Record<string, unknown>;
}

function isMatchReport(x: unknown): x is MatchReport {
  if (!x || typeof x !== "object") return false;
  const o = x as Record<string, unknown>;
  return typeof o.schema_version === "string" && Array.isArray(o.results) && typeof o.summary === "object";
}

async function realMatch(
  client: ApiClient,
  cv: CV,
  job: Job,
): Promise<MatchReport> {
  const data = (await client.match({ cv, job })) as PipelineOutput;
  if (!data || typeof data !== "object" || !isMatchReport(data.match_report))
    throw new ApiError("Backend response is missing a valid match_report.");
  const extras = new Map<string, PipelineRequirementRow>();
  for (const row of data.requirements ?? []) extras.set(row.req_id, row);
  const merged: MatchReport = {
    ...data.match_report,
    results: data.match_report.results.map((r) => {
      const x = extras.get(r.req_id);
      return x
        ? { ...r, judge: x.judge ?? null, bias_audit: x.bias_audit ?? null, validator: x.validator ?? null }
        : r;
    }),
  };
  return merged;
}

export const adapter: AnalysisAdapter = {
  async run(input) {
    validateInput(input);
    if (mode !== "REAL")
      return demoCampaign(input, crypto.randomUUID(), new Date().toISOString());
    const client = new ApiClient(undefined, 600_000);
    const job = demoJob(input);
    const id = crypto.randomUUID();
    const candidates: CandidateRecord[] = [];
    // Serialize: concurrency = 1 on the backend (RTX 4050, 6 GB VRAM).
    for (let i = 0; i < input.candidates.length; i++) {
      const cv = input.candidates[i];
      const report = await realMatch(client, cv, job);
      candidates.push({
        id: `${id}-${i + 1}`,
        label: `Candidate ${String(i + 1).padStart(2, "0")}`,
        cv,
        report,
        review: "Pending review",
        note: "",
      });
    }
    return {
      id,
      title: input.title,
      created: new Date().toISOString(),
      mode: "REAL",
      candidates,
    };
  },
};
