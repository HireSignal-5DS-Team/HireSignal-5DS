"""Report Writer: deterministic report + optional tiny-SLM natural-language sections with validation and fallback.

For each text section (executive summary, one plain-language note per requirement):
  SLM attempt 1 -> validator -> accepted, or SLM attempt 2 (one retry) -> validator -> accepted,
  or the deterministic template (writer = deterministic_fallback, with every rejection reason in provenance).
An SLM exception (timeout, crash) counts as a rejected attempt. The SLM sees only the verified facts of the section.

Environment: HS_REPORTER_SLM = off (default) | on | required ; HS_REPORTER_MODEL_PATH ; HS_REPORTER_DOWNLOAD=1 ;
HS_REPORTER_THREADS (4) ; HS_REPORTER_TIMEOUT (s per call, 30) ; HS_REPORTER_MAX_TOKENS (160).
"""
import os
import time

from . import slm_prompt
from .build import build_report, executive_summary, facts_for_requirement, facts_for_summary, requirement_note
from .schema import TextSection
from .slm import LlamaCppSLM, SLMUnavailable
from .slm_validate import validate

MAX_ATTEMPTS = 2  # one try + one retry


def slm_from_env(env=None):
    """(slm or None, status). required: raise if the SLM cannot be loaded."""
    env = os.environ if env is None else env
    mode = env.get("HS_REPORTER_SLM", "off")
    if mode not in ("off", "on", "required"):
        raise ValueError(f"HS_REPORTER_SLM must be off | on | required, not {mode!r}")
    if mode == "off":
        return None, "off"
    try:
        return LlamaCppSLM(env=env), "on"
    except SLMUnavailable as e:
        if mode == "required":
            raise
        return None, f"unavailable: {e}"


def write_section(slm, kind, facts, fallback_text):
    rejections, rejected, t0 = [], [], time.perf_counter()
    model = slm.info().get("model")
    for _ in range(MAX_ATTEMPTS):
        try:
            raw = slm.generate(kind, facts, feedback=rejections[-1][:300] if rejections else None)
        except Exception as e:  # noqa: BLE001 - SLM down / timeout: recorded, then retry or fallback
            rejections.append(f"slm_error:{type(e).__name__}: {str(e)[:80]}")
            continue
        text, errs = validate(raw, facts, kind)
        if text is not None:
            return TextSection(text=text, writer="slm_mock" if slm.is_mock else "slm", model=model,
                               attempts=len(rejections) + 1, rejections=rejections, rejected_outputs=rejected,
                               latency_s=round(time.perf_counter() - t0, 3))
        rejections.append("; ".join(errs))
        rejected.append(raw[:400])
    return TextSection(text=fallback_text, writer="deterministic_fallback", model=model, attempts=MAX_ATTEMPTS,
                       rejections=rejections, rejected_outputs=rejected, latency_s=round(time.perf_counter() - t0, 3))


def write(out, slm=None, slm_status=None, job_title=None):
    """Report (reporter.schema.Report) from a Pipeline.run() dict."""
    if slm is None:
        return build_report(out, job_title=job_title, slm_status=slm_status or "off")
    summary = write_section(slm, "summary", facts_for_summary(out), executive_summary(out))
    notes = {r["req_id"]: write_section(slm, "note", facts_for_requirement(r), requirement_note(r))
             for r in out["requirements"]}
    info = {**slm.info(), "prompt_id": slm_prompt.PROMPT_ID, "prompt_sha256": slm_prompt.prompt_sha256(),
            "max_attempts": MAX_ATTEMPTS}
    return build_report(out, job_title=job_title, notes=notes, summary=summary, slm_info=info,
                        slm_status=slm_status or ("on (MOCK test double)" if slm.is_mock else "on"))


def write_files(out, folder, slm=None, slm_status=None, job_title=None, stem="report"):
    """Write <stem>.report.json, <stem>.html and <stem>.slm.md; returns the Report."""
    import json
    from pathlib import Path

    from .render import to_html, to_markdown

    rep = write(out, slm=slm, slm_status=slm_status, job_title=job_title)
    d = Path(folder)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.report.json").write_text(json.dumps(rep.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n")
    (d / f"{stem}.html").write_text(to_html(rep))
    (d / f"{stem}.slm.md").write_text(to_markdown(rep))
    return rep
