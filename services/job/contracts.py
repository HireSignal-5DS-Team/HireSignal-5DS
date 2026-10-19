# Adapted from team V2: contracts/job_requirements.py (feature/agent-integration @ a5a03ff)
"""Output contract of the Job Agent: a job post -> a requirements card.

Same style as the team's pipeline contract (pipeline.schema.json):
- Pydantic v2, strict (extra fields are refused);
- every requirement carries `evidence`, an exact quote from the job post,
  so code can check that nothing was invented;
- facts the agent could not establish go to `uncertain`, not into guesses.

The card converts losslessly to the Matcher's `Job` model
(matcher/schemas.py: job_id, title, requirements[req_id, text, kind,
category, skill_terms, min_years]) with `to_matcher_job()`.

Export the JSON Schema:  python -m services.job.contracts
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.1.0"

Kind = Literal["must", "nice"]
Category = Literal["skill", "experience", "education", "certification", "language", "other"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Requirement(_Strict):
    """One thing the employer asks for."""

    req_id: str = Field(pattern=r"^r[0-9]+$", examples=["r1"],
                        description="Stable id inside this job: r1, r2, ...")
    text: str = Field(min_length=1, examples=["3+ years of experience with Java"],
                      description="The requirement as one short, self-contained statement.")
    evidence: str = Field(min_length=1,
                          description="Exact quote copied from the job post that states this requirement.")
    kind: Kind = Field(description="'must' = required; 'nice' = preferred, a plus, nice to have.")
    category: Category = "skill"
    skill_terms: list[str] = Field(default_factory=list, examples=[["Java"]],
                                   description="Skill or tool names, used as retrieval queries by the Matcher.")
    min_years: float | None = Field(None, ge=0, le=50,
                                    description="Minimum years asked for, when the post gives a number; else null.")
    chunk_ids: list[str] = Field(default_factory=list, examples=[["JD-001-C03"]],
                                 description="RAG chunks of the job description this requirement comes from. "
                                             "Empty until the job post is indexed.")


class JobRequirements(_Strict):
    """The requirements card for one job post."""

    schema_version: str = SCHEMA_VERSION
    job_id: str = Field(min_length=1, examples=["JD-001"])
    title: str = Field(min_length=1, examples=["Backend Developer"])
    language: Literal["en", "fr", "other"] = Field("en", description="Language of the job post.")
    requirements: list[Requirement] = Field(min_length=1)
    uncertain: list[str] = Field(default_factory=list,
                                 description="Facts the agent could not establish, e.g. 'unclear if Docker is required'.")
    needs_human_review: bool = Field(False, description="True when validation still failed after the retry.")
    warnings: list[str] = Field(default_factory=list,
                                description="Problems found by validation, shown to the recruiter.")

    @model_validator(mode="after")
    def _ids_are_unique(self) -> "JobRequirements":
        ids = [r.req_id for r in self.requirements]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate req_id: {duplicates}")
        return self

    def to_matcher_job(self) -> dict:
        """Convert to the Matcher's `Job` (matcher/schemas.py)."""
        return {
            "job_id": self.job_id,
            "title": self.title,
            "requirements": [
                {
                    "req_id": r.req_id,
                    "text": r.text,
                    "kind": r.kind,
                    "category": r.category,
                    "skill_terms": r.skill_terms,
                    "min_years": r.min_years,
                }
                for r in self.requirements
            ],
        }


def export_json_schema(path) -> None:
    """Write the JSON Schema in the same layout as pipeline.schema.json."""
    import json
    from pathlib import Path

    doc = {
        "title": "HireSignal Job Agent contract",
        "version": SCHEMA_VERSION,
        "models": {"JobRequirements": JobRequirements.model_json_schema()},
    }
    Path(path).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    from pathlib import Path

    target = Path(__file__).with_name("job_requirements.schema.json")
    export_json_schema(target)
    print(f"wrote {target}")
