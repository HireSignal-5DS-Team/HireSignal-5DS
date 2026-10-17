import type { Campaign, LiveV2Progress, Mode, RequirementResult } from "./contracts";

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
  apiFlow: "v1" | "v2" = "v1",
  liveProgress: LiveV2Progress | null = null,
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

  // V2 has real upstream agents; its server returns their individual stage
  // statuses after each candidate completes. Never reuse the V1 placeholders.
  if (apiFlow === "v2") return workflowStagesV2(liveProgress, campaign, running, error);

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


/** V2 is measured from the server's completed per-candidate stage records.
 *  The API is synchronous: there is NO live stage streaming during inference.
 */
function workflowStagesV2(
  liveProgress: LiveV2Progress | null,
  campaign: Campaign | null,
  running: boolean,
  error: string,
): WorkflowStage[] {
  const candidates = campaign?.mode === "REAL" ? campaign.candidates : [];
  // A running V2 analysis reports real stage events from FastAPI, per candidate.
  if (!candidates.length && liveProgress?.stages.length) {
    const candidateLabel = "Candidate " + liveProgress.candidate_index + "/" + liveProgress.candidate_total;
    const fromBackend = (name: string, key: string): WorkflowStage => {
      const event = liveProgress.stages.find((item) => item.stage === key);
      if (!event) return { name, state: "Pending", detail: candidateLabel + ": waiting for this stage" };
      const state: WorkflowState = event.status === "ok" ? "Completed"
        : event.status === "failed" ? "Failed" : "Running";
      const seconds = typeof event.elapsed_s === "number" ? " · " + event.elapsed_s.toFixed(1) + " s" : "";
      return { name, state, detail: candidateLabel + ": " + key + " " + event.status + seconds };
    };
    const afterMatcher = (name: string): WorkflowStage => ({
      name, state: "Pending",
      detail: candidateLabel + ": final RAG, Bias and Judge evidence is verified after the Matcher returns",
    });
    return [
      fromBackend("CV Reader", "reader"),
      fromBackend("Profile Agent", "profile"),
      fromBackend("Job Agent", "job_agent"),
      afterMatcher("RAG Retrieval"),
      fromBackend("Matcher", "matcher_pipeline"),
      afterMatcher("Bias Auditor"),
      afterMatcher("Judge"),
      fromBackend("Report Writer", "reporter"),
    ];
  }
  const awaitingDetail = error
    ? "Analysis failed; no verified stage results were returned. See the error above."
    : running
      ? "Awaiting the first backend progress event; no agent has been confirmed yet."
      : "No completed V2 analysis has been received yet.";

  const pending = (name: string): WorkflowStage => ({
    name,
    state: error ? "Not reported" : "Pending",
    detail: awaitingDetail,
  });

  const serverStage = (name: string, key: string): WorkflowStage => {
    if (!candidates.length) return pending(name);
    const records = candidates.map((candidate) =>
      candidate.stages?.find((stage) => stage.stage === key),
    );
    const failure = records.find((record) => record?.status === "failed");
    if (failure) {
      return {
        name,
        state: "Failed",
        detail: failure.error ?? `Backend reported that ${key} failed`,
      };
    }
    const confirmed = records.filter((record) => record?.status === "ok").length;
    if (confirmed !== candidates.length) {
      return {
        name,
        state: "Not reported",
        detail: `Verified server stage returned for ${confirmed}/${candidates.length} candidates`,
      };
    }
    const seconds = records.reduce((sum, record) => sum + (record?.elapsed_s ?? 0), 0);
    return {
      name,
      state: "Completed",
      detail: `Server confirmed ${key} for ${confirmed}/${candidates.length} candidates · ${seconds.toFixed(1)} s total`,
    };
  };

  const reader = serverStage("CV Reader", "reader");
  const profile = serverStage("Profile Agent", "profile");
  const job = serverStage("Job Agent", "job_agent");
  const matcherServer = serverStage("Matcher", "matcher_pipeline");
  const allModelBacked = candidates.length > 0 && candidates.every(
    (candidate) => candidate.report.backend.is_model === true &&
      candidate.report.results.length > 0,
  );
  const matcher: WorkflowStage = matcherServer.state === "Completed" && !allModelBacked
    ? {
        name: "Matcher",
        state: "Not reported",
        detail: "Server stage returned, but real Matcher provenance is not confirmed.",
      }
    : matcherServer;

  const evidenceStage = (
    name: string,
    verified: boolean,
    confirmedDetail: string,
    missingDetail: string,
  ): WorkflowStage => {
    if (!candidates.length) return pending(name);
    if (matcher.state !== "Completed") {
      return {
        name,
        state: "Not reported",
        detail: "Matcher pipeline has not been fully verified.",
      };
    }
    return {
      name,
      state: verified ? "Completed" : "Not reported",
      detail: verified ? confirmedDetail : missingDetail,
    };
  };

  const hasRagProvider = candidates.length > 0 && candidates.every(
    (candidate) => typeof candidate.report.backend.knowledge === "string" &&
      candidate.report.backend.knowledge.includes("rag"),
  );
  const rag = evidenceStage(
    "RAG Retrieval",
    hasRagProvider,
    "Real Matcher response confirms the RAG knowledge provider; some queries may correctly retrieve zero citations.",
    "No RAG provider was confirmed in the Matcher response.",
  );

  const results: RequirementResult[] = candidates.flatMap((candidate) => candidate.report.results);
  const biasCount = results.filter((result) => result.bias_audit != null).length;
  const judgeCount = results.filter((result) => result.judge != null).length;
  const bias = evidenceStage(
    "Bias Auditor",
    results.length > 0 && biasCount === results.length,
    `Bias audit returned for ${biasCount}/${results.length} requirements`,
    `Only ${biasCount}/${results.length} bias audit results were returned`,
  );
  const judge = evidenceStage(
    "Judge",
    results.length > 0 && judgeCount === results.length,
    `Judge verdict returned for ${judgeCount}/${results.length} requirements`,
    `Only ${judgeCount}/${results.length} Judge verdicts were returned`,
  );

  const reporterServer = serverStage("Report Writer", "reporter");
  const reportsPresent = candidates.length > 0 && candidates.every(
    (candidate) => candidate.reporter != null,
  );
  const reporter: WorkflowStage =
    reporterServer.state === "Completed" && !reportsPresent
      ? {
          name: "Report Writer",
          state: "Not reported",
          detail: "Reporter server stage succeeded but its validated report was not returned.",
        }
      : reporterServer;
  if (reporter.state === "Completed") {
    const slmSections = candidates.reduce(
      (sum, candidate) => sum + (candidate.reporter?.provenance.sections_slm ?? 0),
      0,
    );
    reporter.detail += ` · ${slmSections} SLM sections accepted; deterministic fallback where needed`;
  }

  return [reader, profile, job, rag, matcher, bias, judge, reporter];
}
