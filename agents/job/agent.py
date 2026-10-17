"""Job Agent: job offer text -> requirements card (contracts/job_requirements.py).

Two strategies (agents/job/prompts.STRATEGY):
  "whole"    (job-v1, job-v2) the whole offer in one call;
  "sections" (job-v3, job-v4) only the requirement sections, one small chunk per call,
                              then merge (agents/job/sections.py).
job-v4 adds a second call per requirement sentence that only asks for the skill
names (prompts.TERMS_PASS), because the first call leaves skill_terms empty.

The loop (act, check, correct), per call:

    job offer --> NuExtract fills the template --> parse JSON
                     ^                                 |
                     |  unreadable answer: retry once  |
                     +---------------------------------+
                                                       v
                 checks + safe repairs (validate.py) --> JobRequirements
                                                       |
                       nothing valid / too many fixes  v
                                         needs_human_review = True

Usage:
    from agents.job import run_job_agent, NuExtractClient
    card = run_job_agent(open("job.txt").read(), job_id="JD-001", backend=NuExtractClient())
    card.model_dump_json(indent=2)
"""

from __future__ import annotations

import re

from contracts.job_requirements import JobRequirements

from . import prompts
from .backend import BackendError, ExtractionBackend
from .sections import Section, chunk_sections, requirement_sections
from .validate import (MUST_CUES, _has_cue, check_requirements, detect_language, locate_evidence,
                       not_a_requirement, parse_model_output)

MAX_ATTEMPTS = 2              # first try + one retry when the answer is unreadable
REVIEW_IF_DROPPED_SHARE = 0.3  # more than 30% of proposals invented -> a person checks the card


class JobAgentError(Exception):
    """No usable requirement could be extracted from the job offer."""


def _ask(backend, text: str, template: str, examples: list[dict], warnings: list[str], where: str) -> dict | None:
    """One extraction call, retried once if the answer is unreadable. None if both fail."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw = backend.extract(text, template, examples)  # BackendError: server down, no retry
        if (getattr(backend, "last_call", {}) or {}).get("finish_reason") == "length":
            warnings.append(f"{where}answer cut off at the token limit")
        try:
            data = parse_model_output(raw)
        except (ValueError, TypeError) as exc:
            warnings.append(f"{where}attempt {attempt}: unreadable answer from NuExtract ({exc})")
            continue
        if data.pop("_salvaged", None) is not None:
            warnings.append(f"{where}answer was cut off; kept the {len(data['requirements'])} complete items")
        return data
    return None


def _extract_by_sections(post: str, backend, template: str, examples: list[dict],
                         warnings: list[str]) -> tuple[list, str, int]:
    """job-v3: only the requirement sections, one small chunk per call, then merge."""
    sections = requirement_sections(post)
    if not sections:
        warnings.append("no requirement section found, the whole offer was used")
        sections = [Section("", post, None)]
    chunks = chunk_sections(sections)

    items, failed = [], 0
    for i, (chunk, _section) in enumerate(chunks, start=1):
        data = _ask(backend, chunk, template, examples, warnings, f"chunk {i}/{len(chunks)}: ")
        if data is None:
            failed += 1
            continue
        found = data.get("requirements")
        items += found if isinstance(found, list) else []
    if failed == len(chunks):
        raise JobAgentError("NuExtract never returned valid JSON. " + " | ".join(warnings))
    if failed:
        warnings.append(f"{failed} of {len(chunks)} chunks gave no usable answer")

    title_data = _ask(backend, post[:600], prompts.title_template(), [], warnings, "title: ")
    title = str((title_data or {}).get("job_title") or "").strip()
    return items, title, failed


def _add_skill_terms(items: list, post: str, backend, warnings: list[str]) -> None:
    """job-v4: a second, focused call per requirement sentence that only asks for the skill names.

    The sentence sent is the real text of the offer (the quote after repair), so the
    verbatim terms can be found in it; each distinct sentence is asked once. The terms
    are added to any the model already gave; check_requirements then keeps only terms
    found in the quote and splits compound lines.
    """
    found: dict[str, list] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        evidence, _how = locate_evidence(str(item.get("evidence") or ""), post)
        if evidence is None or not_a_requirement(evidence):
            continue  # invented quote or not a requirement: check_requirements drops it
        if evidence not in found:
            data = _ask(backend, evidence, prompts.terms_template(), prompts.TERMS_EXAMPLES, warnings,
                        f"terms '{evidence[:40]}': ")
            terms = (data or {}).get("skill_terms")
            found[evidence] = [t for t in terms if isinstance(t, str)] if isinstance(terms, list) else []
        given = item.get("skill_terms") if isinstance(item.get("skill_terms"), list) else []
        seen = {str(t).lower() for t in given}
        item["skill_terms"] = given + [t for t in found[evidence] if t.lower() not in seen]


def _apply_section_hints(requirements: list[dict], sections: list[Section], warnings: list[str]) -> None:
    """Items from a 'Nice to have' / 'Preferred' section are nice, unless their wording says required."""
    nice_texts = [s.text for s in sections if s.kind_hint == "nice"]
    for req in requirements:
        if req["kind"] == "must" and any(req["evidence"] in t for t in nice_texts) \
                and not _has_cue(req["evidence"], MUST_CUES):
            req["kind"] = "nice"
            warnings.append(f"'{req['text'][:50]}': kind 'must' -> 'nice' (from a nice-to-have section)")


def _clean_post(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def run_job_agent(job_text: str, job_id: str, backend: ExtractionBackend,
                  prompt_version: str | None = None) -> JobRequirements:
    """Extract, check and repair the requirements of one job offer.

    prompt_version: "job-v1", "job-v2", ... (default: prompts.PROMPT_VERSION).
    """
    post = _clean_post(job_text)
    if len(post) < 30:
        raise JobAgentError("The job offer is empty or too short.")

    version = prompt_version or prompts.PROMPT_VERSION
    template, examples = prompts.get_prompt(version)
    warnings: list[str] = []

    if prompts.STRATEGY[version] == "sections":
        items, title, failed = _extract_by_sections(post, backend, template, examples, warnings)
        if version in prompts.TERMS_PASS:
            _add_skill_terms(items, post, backend, warnings)
        data = {"requirements": items, "title": title}
    else:
        data = _ask(backend, post, template, examples, warnings, "")
        failed = 0
        if data is None:
            raise JobAgentError("NuExtract never returned valid JSON. " + " | ".join(warnings))

    report = check_requirements(data.get("requirements"), post)
    warnings += report.warnings
    if not report.requirements:
        raise JobAgentError(
            "No requirement survived the checks (all missing, invented or not requirements). " + " | ".join(warnings)
        )

    if prompts.STRATEGY[version] == "sections":
        _apply_section_hints(report.requirements, requirement_sections(post), warnings)

    proposed = len(report.requirements) + report.dropped
    needs_review = (report.dropped / proposed > REVIEW_IF_DROPPED_SHARE or bool(report.uncertain)
                    or failed > 0)

    title = str(data.get("title") or "").strip()
    if not title or title not in post:
        first_line = post.splitlines()[0][:120]
        if title:
            warnings.append(f"title '{title[:60]}' not found in the job offer, used the first line")
        title = first_line

    requirements = [{"req_id": f"r{i}", **req} for i, req in enumerate(report.requirements, start=1)]
    return JobRequirements(
        job_id=job_id,
        title=title,
        language=detect_language(post),
        requirements=requirements,
        uncertain=report.uncertain,
        needs_human_review=needs_review,
        warnings=warnings,
    )
