import type { Campaign, Mode, RequirementResult } from "./contracts";

// The backend returns a completed pipeline result, not per-stage streaming
// telemetry. Never invent per-stage progress for REAL analyses.
export type WorkflowState =
  | "Completed"
  | "Running"
  | "Pending"
  | "Failed"
  | "Not integrated"
  | "Not reported";

export interface WorkflowStage {
  name: string;
  state: WorkflowState;
  detail: string;
}

const names = [
  "CV Reader",
  "Profile & Job Analysis",
  "RAG Retrieval",
  "Matcher",
  "Bias Auditor",
  "Judge",
  "Report Writer",
] as const;

export function workflowStages(
  executionMode: Mode,
  campaign: Campaign | null,
  running: boolean,
  step: number,
  error: string,
): WorkflowStage[] {
  if (executionMode === "MOCK") {
    return names.map((name, i) => {
      const state: WorkflowState = error
        ? i === step
          ? "Failed"
          : i < step
            ? "Completed"
            : "Pending"
        : !running && campaign
          ? "Completed"
          : i < step
            ? "Completed"
            : i === step
              ? "Running"
              : "Pending";
      return {
        name,
        state,
        detail: state === "Completed"
          ? "Simulated step; no agent or model executed"
          : state === "Running"
            ? "Simulating workflow progress"
            : "Demo stage",
      };
    });
  }

  const results: RequirementResult[] =
    campaign?.mode === "REAL"
      ? campaign.candidates.flatMap((candidate) => candidate.report.results)
      : [];
  const reports = campaign?.mode === "REAL"
    ? campaign.candidates.map((candidate) => candidate.report)
    : [];
  const responseAvailable = reports.length > 0;
  const stage = (
    name: string,
    verified: boolean,
    completeDetail: string,
    missingDetail: string,
  ): WorkflowStage => ({
    name,
    state: responseAvailable
      ? verified ? "Completed" : "Not reported"
      : "Pending",
    detail: responseAvailable
      ? verified ? completeDetail : missingDetail
      : "Waiting for the FastAPI response; live per-stage progress is not available",
  });

  const matcherVerified = reports.length > 0 && reports.every(
    (report) => report.backend.is_model === true && report.results.length > 0,
  );
  const ragVerified = reports.length > 0 && reports.every(
    (report) => typeof report.backend.knowledge === "string" &&
      report.backend.knowledge.length > 0,
  );
  const judgeCount = results.filter((result) => result.judge != null).length;
  const biasCount = results.filter((result) => result.bias_audit != null).length;

  return [
    {
      name: names[0],
      state: "Not integrated",
      detail: "Ayoub's Reader agent is not connected; CV text is prepared in the browser",
    },
    {
      name: names[1],
      state: "Not integrated",
      detail: "Profile/Job agents are not connected; job requirements are entered manually",
    },
    stage(
      names[2],
      ragVerified,
      "Backend reports RAG enabled; a requirement can have zero retrieved citations",
      "No RAG execution metadata was returned",
    ),
    stage(
      names[3],
      matcherVerified,
      "Real Matcher output received from the backend",
      "Real Matcher execution could not be confirmed from the response",
    ),
    stage(
      names[4],
      results.length > 0 && biasCount === results.length,
      `Bias audit results returned for ${biasCount}/${results.length} requirements`,
      `Bias audit output reported for ${biasCount}/${results.length} requirements`,
    ),
    stage(
      names[5],
      results.length > 0 && judgeCount === results.length,
      `Judge verdicts returned for ${judgeCount}/${results.length} requirements`,
      `Judge output reported for ${judgeCount}/${results.length} requirements`,
    ),
    {
      name: names[6],
      state: responseAvailable && campaign!.candidates.every((candidate) => candidate.reporter)
        ? "Completed"
        : "Not reported",
      detail: responseAvailable && campaign!.candidates.every((candidate) => candidate.reporter)
        ? `Grounded report returned for ${campaign!.candidates.length} candidate(s); ${campaign!.candidates.reduce((sum, candidate) => sum + (candidate.reporter?.provenance.sections_slm ?? 0), 0)} SLM-written sections accepted; deterministic fallback where needed`
        : "SLM report generation is not confirmed by the current /api/v1/match response",
    },
  ];
}
