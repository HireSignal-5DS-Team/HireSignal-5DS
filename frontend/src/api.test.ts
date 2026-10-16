import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiClient,
  demoCampaign,
  mockReport,
  readCVFile,
  validateInput,
} from "./api";
import type { AnalysisInput, Job } from "./contracts";
const input: AnalysisInput = {
  title: "Engineer",
  description: "React\nPython",
  candidates: [{ cv_id: "a", text: "React\nLearning Python.", structured: {} }],
};
const job: Job = {
  job_id: "j",
  title: "Engineer",
  requirements: [
    {
      req_id: "r1",
      text: "Python",
      kind: "must",
      category: "skill",
      skill_terms: ["Python"],
      min_years: null,
    },
  ],
};
afterEach(() => vi.unstubAllGlobals());
describe("input and honest demo results", () => {
  it("requires job and candidates and limits batch/text sizes", () => {
    expect(() => validateInput({ ...input, title: "" })).toThrow("role title");
    expect(() => validateInput({ ...input, description: "" })).toThrow(
      "job description",
    );
    expect(() => validateInput({ ...input, candidates: [] })).toThrow(
      "1 and 10",
    );
    expect(() =>
      validateInput({
        ...input,
        candidates: Array(11).fill(input.candidates[0]),
      }),
    ).toThrow("1 and 10");
    expect(() =>
      validateInput({
        ...input,
        candidates: [{ cv_id: "a", text: "a".repeat(50001), structured: {} }],
      }),
    ).toThrow("50,000");
  });
  it("is deterministic with genuine verbatim evidence and Python Unicode offsets", () => {
    const cv = { cv_id: "a", text: "🧑‍💻\nLearning Python.", structured: {} };
    const a = mockReport(cv, job);
    expect(a).toEqual(mockReport(cv, job));
    expect(a.results[0].decision).toBe("UNCERTAIN");
    const [start, end] = a.results[0].evidence_spans[0];
    expect(Array.from(cv.text).slice(start, end).join("")).toBe(
      a.results[0].evidence[0],
    );
    expect(a.backend.judge).toBe("not_executed");
  });
  it("treats absence as not documented and never says the candidate lacks a skill", () => {
    const report = mockReport(
      { cv_id: "a", text: "React", structured: {} },
      job,
    );
    expect(report.results[0]).toMatchObject({
      decision: "MISSING",
      basis: "not_documented",
      evidence: [],
      needs_human_review: true,
    });
    expect(report.summary.note).toContain("No automatic rejection");
  });
  it("does not turn a negated or aspirational mention into MET", () => {
    for (const text of [
      "No Python experience.",
      "I want to learn Python.",
      "Not proficient in Python.",
    ])
      expect(
        mockReport({ cv_id: "a", text, structured: {} }, job).results[0]
          .decision,
      ).toBe("UNCERTAIN");
  });
  it("returns all candidates, with all requirements and review flags", () => {
    const campaign = demoCampaign(
      {
        ...input,
        candidates: [
          ...input.candidates,
          { ...input.candidates[0], cv_id: "b" },
        ],
      },
      "demo",
      "2026-10-16",
    );
    expect(campaign.candidates).toHaveLength(2);
    expect(campaign.candidates[0].report.results).toHaveLength(2);
    expect(campaign.candidates[0].report.summary.needs_human_review).toBe(2);
  });
  it("validates type, size, empty text, malformed UTF-8 and binary uploads", async () => {
    await expect(readCVFile(new File(["React"], "cv.txt"))).resolves.toBe(
      "React",
    );
    await expect(readCVFile(new File(["data"], "cv.pdf"))).rejects.toThrow(
      "only UTF-8",
    );
    await expect(
      readCVFile(new File(["x".repeat(200001)], "cv.txt")),
    ).rejects.toThrow("200 KB");
    await expect(readCVFile(new File([" "], "cv.txt"))).rejects.toThrow(
      "readable text",
    );
    await expect(
      readCVFile(new File([new Uint8Array([0xff])], "cv.txt")),
    ).rejects.toThrow();
    await expect(
      readCVFile(new File(["text\0binary"], "cv.txt")),
    ).rejects.toThrow("readable text");
  });
});
describe("FastAPI transport", () => {
  it("calls all supplied endpoints and preserves the transport payload", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{"status":"ok"}'));
    // Each request needs an unconsumed response.
    fetch.mockImplementation(async () => new Response('{"status":"ok"}'));
    vi.stubGlobal("fetch", fetch);
    const api = new ApiClient("https://api.example.test/");
    await api.health();
    await api.ready();
    await api.models();
    await api.match({ cv: input.candidates[0] });
    expect(fetch.mock.calls.map((c) => c[0])).toEqual([
      "https://api.example.test/health",
      "https://api.example.test/ready",
      "https://api.example.test/api/v1/models/status",
      "https://api.example.test/api/v1/match",
    ]);
    expect(fetch.mock.calls[3][1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({ cv: input.candidates[0] }),
    });
  });
  it("rejects missing or invalid configuration", async () => {
    await expect(new ApiClient("").health()).rejects.toThrow(
      "VITE_API_BASE_URL",
    );
    await expect(new ApiClient("bad").health()).rejects.toThrow("absolute");
    await expect(new ApiClient("file:///data").health()).rejects.toThrow(
      "HTTP(S)",
    );
  });
  it.each([
    ["", "empty response"],
    ["not-json", "unexpected JSON"],
    ["null", "unexpected JSON"],
    ["42", "unexpected JSON"],
  ])("handles invalid response %s", async (body, message) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));
    await expect(
      new ApiClient("https://api.example.test").ready(),
    ).rejects.toThrow(message);
  });
  it("handles HTTP failures without exposing backend details", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(new Response("private details", { status: 422 })),
    );
    await expect(
      new ApiClient("https://api.example.test").match({}),
    ).rejects.toThrow("HTTP 422");
  });
  it("handles network errors and timeouts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );
    await expect(
      new ApiClient("https://api.example.test").health(),
    ).rejects.toThrow("CORS");
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url, init) =>
          new Promise((_resolve, reject) =>
            init.signal.addEventListener("abort", () =>
              reject(new Error("aborted")),
            ),
          ),
      ),
    );
    await expect(
      new ApiClient("https://api.example.test", 5).health(),
    ).rejects.toThrow("timed out");
  });
});
