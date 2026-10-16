"""Renderers: Report -> Markdown, Report -> self-contained HTML (inline CSS, no script, every value escaped)."""
from html import escape

WRITER_LABEL = {"deterministic": "deterministic template",
                "slm": "tiny SLM (validated)",
                "slm_mock": "scripted test double (MOCK, not a model)",
                "deterministic_fallback": "deterministic fallback (SLM text failed the fact check)"}


def _writer(t):
    lab = WRITER_LABEL[t.writer]
    if t.writer == "slm" and t.model:
        lab += f", {t.model}"
    if t.writer == "deterministic_fallback" and t.rejections:  # check names only; the details (which may contain
        codes = {c.split(":")[0] for r in t.rejections for c in r.split("; ")}  # the unsupported words) stay in JSON
        lab += f"; failed checks: {', '.join(sorted(codes))}"
    return lab


def _who(m):
    if m.answered_by is None:
        return "no model (all Matcher endpoints failed)"
    s = f"{m.answered_by} · {m.served_alias or m.model_id} · " + (f"adapter {m.adapter}" if m.adapter else "no adapter")
    if m.replayed_from:
        s += f" · replayed LIVE output from {m.replayed_from}"
    return s + (" · MOCK (not a model result)" if m.mock else "")


def _judge(j):
    s = j.verdict + (f" (score {j.score:.3f})" if j.score is not None else "")
    return s + (f" · {j.model}" if j.model else "") + (f" · error: {j.error}" if j.error else "")


def _bias(b):
    s = b.audit_status
    if b.counterfactual_flip:
        s += f" (counterfactual flip on {b.affected_attribute})"
    if b.leakage_terms:
        s += f" (leakage terms: {', '.join(b.leakage_terms)})"
    return s


def _md(s):
    """Neutralise markdown/HTML control characters in values copied from the input."""
    return (s.replace("\\", "\\\\").replace("<", "&lt;").replace(">", "&gt;").replace("`", "\\`")
            .replace("*", "\\*").replace("_", "\\_").replace("[", "\\[").replace("]", "\\]").replace("\n", " "))


def to_markdown(rep):
    o, p = rep.overview, rep.provenance
    L = [f"# Requirement check: CV `{_md(o.cv_id)}` vs job `{_md(o.job_id)}`"
         + (f" ({_md(o.job_title)})" if o.job_title else ""), "",
         f"> **{rep.disclaimer}**", "",
         f"MET {o.counts['MET']} · MISSING {o.counts['MISSING']} · UNCERTAIN {o.counts['UNCERTAIN']} · must-have met "
         f"{o.must_met}/{o.must_total} · **{o.requires_human_review} requirement(s) need human review**", ""]
    if o.requires_human_review:
        L += [f"**⚠ HUMAN REVIEW REQUIRED for {o.requires_human_review} requirement(s)** (see flags below).", ""]
    if p.any_mock:
        L += ["**MOCK backend in the pipeline: decisions are not model results.**", ""]
    L += ["## Summary", "", _md(rep.executive_summary.text), "", f"_Written by: {_md(_writer(rep.executive_summary))}_", ""]
    for r in rep.requirements:
        L += [f"## {_md(r.req_id)} ({r.kind}-have): {_md(r.requirement_text)}", "",
              f"- Decision: **{r.decision}** (basis: {r.basis}); Matcher model said {r.model_decision}",
              f"- Note: {_md(r.plain_note.text)} _(written by: {_md(_writer(r.plain_note))})_",
              f"- Explanation: {_md(r.explanation.text)} _(deterministic, from validated fields)_"]
        L += [f"- Evidence (verbatim CV quote, chars {e.span[0]}-{e.span[1]}): \"{_md(e.quote)}\"" for e in r.evidence] \
            or ["- Evidence: none quoted"]
        if r.knowledge_shown:
            L += ["- Knowledge shown to the model (terminology, NOT candidate evidence): "
                  + "; ".join(f"{_md(k.title or '')} [{_md(k.source_id)}]" for k in r.knowledge_shown)]
        L += [f"- Validator: {_md(', '.join(r.validator_reasons) or 'no issue')}",
              f"- Bias audit: {_md(_bias(r.bias_audit))}",
              f"- NLI Judge: {_md(_judge(r.judge))}",
              f"- Matcher model: {_md(_who(r.model))}",
              "- Human review: " + (f"**REQUIRED**: {_md(', '.join(r.review_reasons))}" if r.requires_human_review
                                    else "not required"), ""]
    L += ["## Provenance", "", f"- Report schema {p.report_schema_version}, renderer `{p.renderer}`",
          f"- SLM layer: {_md(p.slm_status)}"
          + (f"; {_md(p.slm['model'])}, prompt `{p.slm['prompt_id']}` (sha256 {p.slm['prompt_sha256'][:12]})"
             if p.slm else ""),
          f"- Text sections: {p.sections_total} total, {p.sections_slm} written by the SLM, "
          f"{p.sections_fallback} deterministic fallback after a failed fact check",
          f"- Matcher prompt `{_md(str(p.pipeline['backend'].get('prompt_id')))}` · knowledge "
          f"`{_md(str(p.pipeline.get('knowledge')))}` · judge `{_md(str(p.pipeline.get('judge')))}`", "",
          f"_{rep.disclaimer}_", ""]
    return "\n".join(L)


CSS = """body{font-family:system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem;color:#1a1a1a;background:#fff}
.disc{border:2px solid #b45309;background:#fffbeb;padding:.75rem 1rem;font-weight:600}
.req{border:1px solid #d4d4d8;border-radius:6px;padding:.5rem 1rem;margin:1rem 0}
.MET{color:#166534}.MISSING{color:#991b1b}.UNCERTAIN{color:#92400e}
.who{color:#52525b;font-size:.85em}.review{color:#991b1b;font-weight:600}.mock{background:#fee2e2;padding:.5rem}
blockquote{margin:.25rem 0;padding-left:.75rem;border-left:3px solid #a1a1aa}
.kn{color:#52525b}table{border-collapse:collapse}td,th{border:1px solid #d4d4d8;padding:.2rem .5rem;text-align:left}"""


def to_html(rep):
    e = lambda s: escape(str(s), quote=True)  # noqa: E731
    o, p = rep.overview, rep.provenance
    H = ["<!doctype html><html lang=en><head><meta charset=utf-8>",
         "<meta name=viewport content='width=device-width,initial-scale=1'>",
         f"<title>Requirement check {e(o.cv_id)} / {e(o.job_id)}</title><style>{CSS}</style></head><body>",
         f"<h1>Requirement check: CV {e(o.cv_id)} vs job {e(o.job_id)}"
         + (f" ({e(o.job_title)})" if o.job_title else "") + "</h1>",
         f"<p class=disc>{e(rep.disclaimer)}</p>"]
    if o.requires_human_review:
        H.append(f"<p class=review>HUMAN REVIEW REQUIRED for {o.requires_human_review} requirement(s) (see flags below).</p>")
    if p.any_mock:
        H.append("<p class=mock>MOCK backend in the pipeline: decisions are not model results.</p>")
    H += ["<table><tr><th>MET</th><th>MISSING</th><th>UNCERTAIN</th><th>must-have met</th><th>need review</th></tr>",
          f"<tr><td>{o.counts['MET']}</td><td>{o.counts['MISSING']}</td><td>{o.counts['UNCERTAIN']}</td>"
          f"<td>{o.must_met}/{o.must_total}</td><td>{o.requires_human_review}</td></tr></table>",
          f"<h2>Summary</h2><p>{e(rep.executive_summary.text)}</p>"
          f"<p class=who>Written by: {e(_writer(rep.executive_summary))}</p>"]
    for r in rep.requirements:
        H += [f"<section class=req><h2>{e(r.req_id)} ({e(r.kind)}-have): {e(r.requirement_text)}</h2>",
              f"<p>Decision: <strong class={e(r.decision)}>{e(r.decision)}</strong> (basis: {e(r.basis)}); "
              f"Matcher model said {e(r.model_decision)}</p>",
              f"<p>{e(r.plain_note.text)} <span class=who>(written by: {e(_writer(r.plain_note))})</span></p>",
              f"<p>{e(r.explanation.text)} <span class=who>(deterministic, from validated fields)</span></p>"]
        H += [f"<blockquote>{e(x.quote)} <span class=who>verbatim CV quote, chars {x.span[0]}-{x.span[1]}</span>"
              "</blockquote>" for x in r.evidence] or ["<p>Evidence: none quoted</p>"]
        if r.knowledge_shown:
            H.append("<p class=kn>Knowledge shown to the model (terminology, NOT candidate evidence): "
                     + "; ".join(f"{e(k.title or '')} [{e(k.source_id)}]" for k in r.knowledge_shown) + "</p>")
        H += ["<ul>", f"<li>Validator: {e(', '.join(r.validator_reasons) or 'no issue')}</li>",
              f"<li>Bias audit: {e(_bias(r.bias_audit))}</li>", f"<li>NLI Judge: {e(_judge(r.judge))}</li>",
              f"<li>Matcher model: {e(_who(r.model))}</li>",
              "<li>Human review: " + (f"<span class=review>REQUIRED: {e(', '.join(r.review_reasons))}</span>"
                                      if r.requires_human_review else "not required") + "</li></ul></section>"]
    slm = (f"; {e(p.slm['model'])}, prompt {e(p.slm['prompt_id'])} (sha256 {e(p.slm['prompt_sha256'][:12])})"
           if p.slm else "")
    H += ["<h2>Provenance</h2><ul>", f"<li>Report schema {e(p.report_schema_version)}, renderer {e(p.renderer)}</li>",
          f"<li>SLM layer: {e(p.slm_status)}{slm}</li>",
          f"<li>Text sections: {p.sections_total} total, {p.sections_slm} written by the SLM, "
          f"{p.sections_fallback} deterministic fallback after a failed fact check</li>",
          f"<li>Matcher prompt {e(p.pipeline['backend'].get('prompt_id'))} · knowledge {e(p.pipeline.get('knowledge'))}"
          f" · judge {e(p.pipeline.get('judge'))}</li></ul>",
          f"<p class=disc>{e(rep.disclaimer)}</p></body></html>"]
    return "\n".join(H) + "\n"
