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

  it("never calls an unreported Judge or Bias audit completed", () => {
    const campaign = realCampaign();
    delete campaign.candidates[0].report.results[0].judge;
    delete campaign.candidates[0].report.results[0].bias_audit;
    const stages = workflowStages("REAL", campaign, false, 0, "");
    expect(stages[4].state).toBe("Not reported");
    expect(stages[5].state).toBe("Not reported");
  });
});
