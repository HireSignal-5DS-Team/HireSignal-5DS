import { describe, expect, it } from "vitest";
import { demoCampaign } from "./api";
import { workflowStages } from "./workflow";
import type { Campaign } from "./contracts";

const fixture = demoCampaign(
  {
    title: "AI Engineer",
    description: "Python",
    candidates: [{ cv_id: "c1", text: "Built Python APIs.", structured: {} }],
  },
  "sample",
  "2026-10-16T19:00:00Z",
);

function realCampaign(): Campaign {
  const campaign = structuredClone(fixture);
  campaign.mode = "REAL";
  const report = campaign.candidates[0].report;
  report.backend = { is_model: true, knowledge: "rag.gated.v1+bm25" };
  report.results[0].judge = {
    judge_verdict: "UNCERTAIN",
    judge_score: 0.4,
    model: "cross-encoder/nli-deberta-v3-xsmall",
    requires_human_review: true,
  };
  report.results[0].bias_audit = {
    audit_status: "PASS",
    counterfactual_flip: false,
    affected_attribute: null,
    requires_human_review: false,
  };
  return campaign;
}

describe("honest workflow telemetry", () => {
  it("keeps mock completions visibly simulated", () => {
    const stages = workflowStages("MOCK", fixture, false, 6, "");
    expect(stages).toHaveLength(7);
    expect(stages.every((s) => s.state === "Completed")).toBe(true);
    expect(stages.every((s) => s.detail.includes("Simulated"))).toBe(true);
  });

  it("does not invent running model stages while awaiting REAL response", () => {
    const stages = workflowStages("REAL", null, true, 0, "");
    expect(stages[0].state).toBe("Not integrated");
    expect(stages[1].state).toBe("Not integrated");
    expect(stages.slice(2, 6).every((s) => s.state === "Pending")).toBe(true);
    expect(stages[6].state).toBe("Not reported");
    expect(stages.every((s) => s.state !== "Completed")).toBe(true);
  });

  it("uses real response provenance to mark only confirmed stages completed", () => {
    const stages = workflowStages("REAL", realCampaign(), false, 0, "");
    expect(stages.map((s) => s.state)).toEqual([
      "Not integrated",
      "Not integrated",
      "Completed",
      "Completed",
      "Completed",
      "Completed",
      "Not reported",
    ]);
    expect(stages[6].detail).toContain("/api/v1/match");
  });

  it("confirms the Report Writer only when the API returns its grounded report", () => {
    const campaign = realCampaign();
    campaign.candidates[0].reporter = {
      schema_version: "1.0.0",
      executive_summary: { text: "Verified summary", writer: "deterministic_fallback" },
      requirements: [],
      provenance: {
        slm_status: "on",
        sections_total: 2,
        sections_slm: 1,
        sections_fallback: 1,
        model: "Qwen3-0.6B",
        any_mock: false,
      },
    };
    const stages = workflowStages("REAL", campaign, false, 0, "");
    expect(stages[6].state).toBe("Completed");
    expect(stages[6].detail).toContain("1 SLM-written sections");
  });

  it("never calls an unreported Judge or Bias audit completed", () => {
    const campaign = realCampaign();
    delete campaign.candidates[0].report.results[0].judge;
    delete campaign.candidates[0].report.results[0].bias_audit;
    const stages = workflowStages("REAL", campaign, false, 0, "");
    expect(stages[4].state).toBe("Not reported");
    expect(stages[5].state).toBe("Not reported");
  });
});


function completedV2Campaign(): Campaign {
  const campaign = realCampaign();
  campaign.candidates[0].stages = [
    { stage: "reader", status: "ok", elapsed_s: 0.4 },
    { stage: "profile", status: "ok", elapsed_s: 12.5 },
    { stage: "job_agent", status: "ok", elapsed_s: 18.3 },
    { stage: "matcher_pipeline", status: "ok", elapsed_s: 31.7 },
    { stage: "reporter", status: "ok", elapsed_s: 9.2 },
  ];
  campaign.candidates[0].reporter = {
    schema_version: "1.0.0",
    executive_summary: { text: "Verified report", writer: "slm" },
    requirements: [],
    provenance: {
      slm_status: "on",
      sections_total: 2,
      sections_slm: 2,
      sections_fallback: 0,
      model: "Qwen3-0.6B",
      any_mock: false,
    },
  };
  return campaign;
}

describe("V2 upstream workflow telemetry", () => {
  it("shows all eight real V2 stages as pending while API inference is in flight", () => {
    const rows = workflowStages("REAL", null, true, 0, "", "v2");
    expect(rows.map((s) => s.name)).toEqual([
      "CV Reader", "Profile Agent", "Job Agent", "RAG Retrieval",
      "Matcher", "Bias Auditor", "Judge", "Report Writer",
    ]);
    expect(rows.every((s) => s.state === "Pending")).toBe(true);
    expect(rows.every((s) => s.detail.includes("does not stream"))).toBe(true);
    expect(rows.some((s) => s.state === "Not integrated")).toBe(false);
  });

  it("marks upstream stages completed only from genuine server stage records", () => {
    const rows = workflowStages("REAL", completedV2Campaign(), false, 0, "", "v2");
    expect(rows.map((s) => s.state)).toEqual(Array(8).fill("Completed"));
    expect(rows[0].detail).toContain("reader");
    expect(rows[1].detail).toContain("profile");
    expect(rows[2].detail).toContain("job_agent");
    expect(rows[7].detail).toContain("2 SLM sections accepted");
  });

  it("does not claim completion if an upstream stage or report is absent", () => {
    const campaign = completedV2Campaign();
    campaign.candidates[0].stages = campaign.candidates[0].stages!.filter(
      (stage) => stage.stage !== "profile",
    );
    delete campaign.candidates[0].reporter;
    const rows = workflowStages("REAL", campaign, false, 0, "", "v2");
    expect(rows[0].state).toBe("Completed");
    expect(rows[1].state).toBe("Not reported");
    expect(rows[7].state).toBe("Not reported");
  });

  it("requires stage confirmation for all candidates in a multi-CV run", () => {
    const campaign = completedV2Campaign();
    const second = structuredClone(campaign.candidates[0]);
    second.id = "c2";
    second.stages = second.stages?.filter((stage) => stage.stage !== "job_agent");
    campaign.candidates.push(second);
    const rows = workflowStages("REAL", campaign, false, 0, "", "v2");
    expect(rows[2].state).toBe("Not reported");
    expect(rows[0].detail).toContain("2/2 candidates");
  });

  it("preserves V1-only not-integrated indicators when explicitly using V1", () => {
    const rows = workflowStages("REAL", null, true, 0, "", "v1");
    expect(rows[0].state).toBe("Not integrated");
    expect(rows[1].state).toBe("Not integrated");
  });

  it("does not fabricate successful stages after an API failure", () => {
    const rows = workflowStages("REAL", null, false, 0, "503", "v2");
    expect(rows.every((s) => s.state === "Not reported")).toBe(true);
    expect(rows[0].detail).toContain("Analysis failed");
  });
});
