"""Job Agent: job offer text -> requirements card (contracts/job_requirements.py).

The loop (act, check, correct):

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
from .validate import check_requirements, detect_language, parse_model_output

MAX_ATTEMPTS = 2              # first try + one retry when the answer is unreadable
REVIEW_IF_DROPPED_SHARE = 0.3  # more than 30% of proposals invented -> a person checks the card


class JobAgentError(Exception):
    """No usable requirement could be extracted from the job offer."""


def _clean_post(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def run_job_agent(job_text: str, job_id: str, backend: ExtractionBackend,
                  template: str | None = None, examples: list[dict] | None = None) -> JobRequirements:
    """Extract, check and repair the requirements of one job offer."""
    post = _clean_post(job_text)
    if len(post) < 30:
        raise JobAgentError("The job offer is empty or too short.")

    template = template or prompts.template_json()
    examples = prompts.EXAMPLES if examples is None else examples
    warnings: list[str] = []
    data = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = backend.extract(post, template, examples)
        except BackendError:
            raise  # the server is down: a retry with the same input won't help
        try:
            data = parse_model_output(raw)
            break
        except (ValueError, TypeError) as exc:
            warnings.append(f"attempt {attempt}: unreadable answer from NuExtract ({exc})")
    if data is None:
        raise JobAgentError("NuExtract never returned valid JSON. " + " | ".join(warnings))

    report = check_requirements(data.get("requirements"), post)
    warnings += report.warnings
    if not report.requirements:
        raise JobAgentError(
            "No requirement survived the checks (all missing or invented). " + " | ".join(warnings)
        )

    proposed = len(report.requirements) + report.dropped
    needs_review = report.dropped / proposed > REVIEW_IF_DROPPED_SHARE or bool(report.uncertain)

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
