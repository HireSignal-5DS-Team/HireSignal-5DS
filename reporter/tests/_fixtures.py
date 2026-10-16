"""Synthetic pipeline output for reporter tests: the real Pipeline with a scripted (MOCK) Matcher backend.
Invented CV and job (not benchmark data)."""
import json

from matcher.backends import MockBackend
from matcher.knowledge import FixtureKnowledge
from matcher.pipeline import Pipeline

CV = {"cv_id": "cv-synth-1", "text": "Profile\nBackend developer.\n- 5 years of professional Python experience.\n"
      "- Has not worked with Kubernetes so far.\n- Completed a <script>alert(1)</script> course on Docker basics."}
JOB = {"job_id": "job-synth-1", "title": "Backend <b>engineer</b>", "requirements": [
    {"req_id": "r1", "text": "At least 3 years of Python", "category": "experience", "skill_terms": ["Python"],
     "min_years": 3},
    {"req_id": "r2", "text": "Proficiency in Kubernetes", "skill_terms": ["Kubernetes"]},
    {"req_id": "r3", "text": "Terraform", "skill_terms": ["Terraform"]},
    {"req_id": "r4", "text": "Docker", "kind": "nice", "skill_terms": ["Docker"]}]}
ANSWERS = {
    "r1": ("MET", "supported", ["5 years of professional Python experience."]),
    "r2": ("MISSING", "contradicted", ["Has not worked with Kubernetes so far."]),
    "r3": ("MISSING", "not_documented", []),
    "r4": ("UNCERTAIN", "ambiguous", ["Completed a <script>alert(1)</script> course on Docker basics."]),
}
KNOWLEDGE = FixtureKnowledge([{"source_id": "esco/kubernetes", "title": "Kubernetes", "aliases": ["k8s"],
                               "text": "container orchestration"}])


def _answer(task):
    d, b, ev = ANSWERS[task.req.req_id]
    return json.dumps({"decision": d, "basis": b, "evidence": ev, "explanation": "x"})


def pipeline_output():
    return Pipeline(MockBackend(_answer), KNOWLEDGE).run(CV, JOB)
