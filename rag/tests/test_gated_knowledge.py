"""rag.gated.v1 (matcher/knowledge.py GatedKnowledge): gating, relevance cut-off, de-duplication, compact text and
citations. Real ESCO subset + BM25 (no model download); MockBackend only (no LLM). Run: pytest rag/tests"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from matcher.agent import Matcher  # noqa: E402
from matcher.backends import MockBackend  # noqa: E402
from matcher.knowledge import (MAX_TEXT_CHARS, NO_KNOWLEDGE_CATEGORIES, GatedKnowledge, NoKnowledge,  # noqa: E402
                               RagKnowledge, compact_text, distinct_aliases, esco_aliases, esco_description)
from matcher.prompt import user_message  # noqa: E402
from matcher.schemas import CV, Requirement  # noqa: E402

CV_TEXT = "Profile\nSet up Maven builds for twelve Java services.\nRan Zed Attack Proxy scans on every release.\nCVSECRET-7781"
CVX = CV(cv_id="cv-1", text=CV_TEXT)
MAVEN = "http://data.europa.eu/esco/skill/"  # prefix only; ids are checked through titles


@pytest.fixture(scope="module")
def gated():
    return GatedKnowledge()


def R(text, terms=None, category="skill", rid="r1"):
    return Requirement(req_id=rid, text=text, category=category, skill_terms=[] if terms is None else terms)


def titles(refs):
    return [r.title for r in refs]


# -- gating -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("category,text,terms", [
    ("certification", "Microsoft Azure Administrator Associate certification", ["Microsoft Azure Administrator Associate"]),
    ("language", "Portuguese at C1 level or above", ["Portuguese"]),
    ("education", "Master's degree in computer science", ["master", "MSc", "Master of Science"]),
])
def test_gated_categories_abstain_and_prompt_equals_no_rag(gated, category, text, terms):
    req = R(text, terms, category)
    assert category in NO_KNOWLEDGE_CATEGORIES
    assert gated.lookup(req) == [] and gated.last_trace["gated"]
    assert user_message(CVX, req, gated.lookup(req)) == user_message(CVX, req, NoKnowledge().lookup(req))
    assert RagKnowledge().lookup(req) or category == "certification"  # the legacy arm did inject something here


# -- exact match, one concept per term, compact text -----------------------------------------------------------------
def test_alias_requirement_gets_exactly_its_concept_with_the_alias_shown(gated):
    refs = gated.lookup(R("Working knowledge of OWASP ZAP", ["OWASP ZAP"]))
    assert titles(refs) == ["OWASP ZAP"] and refs[0].retrieval.endswith(":exact")
    assert "Zed Attack Proxy" in refs[0].text and len(refs[0].text) <= MAX_TEXT_CHARS
    assert all(a in refs[0].text for a in refs[0].aliases)  # aliases used by the validator are the ones shown


def test_absent_skill_trap_gets_no_neighbouring_concepts(gated):
    refs = gated.lookup(R("Ability to maintain information network hardware", ["maintain information network hardware"]))
    assert titles(refs) == ["maintain information network hardware"]  # legacy BM25/dense added 2 neighbours
    legacy = RagKnowledge().lookup(R("x", ["maintain information network hardware"]))
    assert len(legacy) == 3


def test_sentence_query_needs_a_label_covering_the_sentence(gated):
    assert titles(gated.lookup(R("Ability to use concurrent programming"))) == ["use concurrent programming"]
    assert gated.lookup(R("Working knowledge of database design")) == []  # not "database" + "design" separately
    assert gated.lookup(R("experience programming in Python")) == []  # "Python" covers 1 of 2 content words
    loose = GatedKnowledge(retriever=gated.retriever, sentence_min_cover=0.5)
    assert titles(loose.lookup(R("experience programming in Python"))) == ["Python (computer programming)"]


# -- relevance cut-off ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("term", ["React", "Pandas", "database design", "FastAPI", "scikit-learn"])
def test_cutoff_rejects_partial_lexical_overlap(gated, term):
    """BM25 returns e.g. 'react to physical changes or hazards' for React; none of these is the required concept."""
    assert gated.lookup(R(f"Working knowledge of {term}", [term])) == []
    assert gated.last_trace["terms"][0]["how"] == "abstain"


def test_cutoff_accepts_same_words_in_another_order(gated):
    refs = gated.lookup(R("cloud architecture design", ["cloud architecture design"]))
    assert titles(refs) == ["design cloud architecture"] and refs[0].retrieval.endswith(":cutoff")


def test_max_extra_relaxes_the_cutoff():
    loose = GatedKnowledge(max_extra=1)
    assert titles(loose.lookup(R("database design", ["database design"]))) == ["design database in the cloud"]


# -- de-duplication and k budget ----------------------------------------------------------------------------------
def test_duplicate_terms_give_one_ref_and_k_is_respected(gated):
    refs = gated.lookup(R("Apache Maven, Maven", ["Apache Maven", "Maven", "Sass", "MDX"]), k=2)
    assert titles(refs) == ["Apache Maven", "Sass"]
    assert len({r.source_id.rsplit("/", 1)[-1][:12] for r in refs}) == len(refs)  # prompt tags stay unambiguous
    assert gated.lookup(R("Sass", ["Sass"]), k=0) == []


def test_distinct_aliases_drops_inflections():
    assert distinct_aliases("lead a team", ["leading a team", "lead teams", "direct a team"]) == ["direct a team"]


def test_every_esco_entry_fits_the_prompt_window(gated):
    for e in gated.esco.values():
        text, shown = compact_text(e["title"], esco_aliases(e["text"]), esco_description(e["text"], e["title"]))
        assert len(text) <= MAX_TEXT_CHARS and text.startswith(e["title"])
        assert all(a in text for a in shown)


# -- citations: rag_refs cite only what the model was shown -----------------------------------------------------------
def _matcher(gated, seen):
    def fn(task):
        seen.append(task.messages[1]["content"])
        return json.dumps({"decision": "MET", "basis": "supported", "evidence": ["Set up Maven builds for twelve Java services."],
                           "explanation": "Maven alias."})
    return Matcher(MockBackend(fn, "MOCK"), gated)


def test_rag_refs_are_exactly_the_refs_shown_in_the_prompt(gated):
    seen = []
    res, info = _matcher(gated, seen).match_requirement(CVX, R("Experience with Apache Maven", ["Apache Maven"]))
    shown = seen[0]
    assert res.rag_refs == [r.source_id for r in info["refs"]] and len(res.rag_refs) == 1
    for r in info["refs"]:
        assert f"[{r.source_id.rsplit('/', 1)[-1][:12]}] {r.text}\n" in shown + "\n"  # whole text, untruncated
    assert res.decision == "MET" and "semantic_inference_no_term_in_quote" not in res.review_reasons  # alias shown


def test_abstention_cites_nothing(gated):
    seen = []
    res, _ = _matcher(gated, seen).match_requirement(CVX, R("CISSP certification", ["CISSP"], "certification"))
    assert res.rag_refs == [] and "(none retrieved)" in seen[0]


class SpyRetriever:
    """Wraps the real retriever and records every query text."""

    def __init__(self, inner):
        self.inner, self.chunks, self.queries, self.model = inner, inner.chunks, [], None

    def search(self, query, **kw):
        self.queries.append(query)
        return self.inner.search(query, **kw)


def test_cv_text_never_reaches_retrieval(gated):
    spy = SpyRetriever(gated.retriever)
    g = GatedKnowledge(retriever=spy)
    job = sorted(g.job_ids)[0]
    m = Matcher(MockBackend(lambda t: '{"decision": "UNCERTAIN", "basis": "ambiguous", "evidence": [], "explanation": "m"}'), g)
    for req in (R("Working knowledge of React", ["React"]), R("Strong ability to troubleshoot"),
                R("Bachelor's degree in statistics", ["statistics"])):
        m.match_requirement(CVX, req, job_id=job)
    assert spy.queries and not any("CVSECRET" in q or "Zed Attack" in q or "Maven builds" in q for q in spy.queries)


# -- job postings ----------------------------------------------------------------------------------------------------
def test_job_passage_is_trimmed_relevant_and_within_k(gated):
    job = "usajobs-883048600"
    assert job in gated.job_ids
    refs = gated.lookup(R("Knowledge of statistics", ["statistics"]), k=3, job_id=job)
    jobs = [r for r in refs if r.source_type == "job"]
    assert len(refs) <= 3 and len(jobs) == 1 and len(jobs[0].text) <= MAX_TEXT_CHARS
    assert "statistic" in jobs[0].text.casefold() and jobs[0].source_id.startswith(job)
    assert [r for r in gated.lookup(R("Knowledge of statistics", ["statistics"]), job_id="job-val-000")
            if r.source_type == "job"] == []  # unknown posting: never another posting


# -- dense candidates (fake dense retriever: no model download) -------------------------------------------------------
class FakeDense:
    model = "fake"
    collection = "fake-e5"

    def __init__(self, chunks, hit, score):
        self.chunks, self.hit, self.score = chunks, hit, score

    def search(self, query, k=5, mode="dense", filters=None):
        assert mode == "dense"
        return {"status": "found", "results": [(self.hit, self.score)]}


def test_dense_candidate_needs_tau(gated):
    ml = next(e for e in gated.esco.values() if e["title"] == "machine learning")
    req = R("apprentissage automatique")
    assert GatedKnowledge(retriever=FakeDense(gated.retriever.chunks, ml, 0.90), mode="dense", dense_tau=0.85).lookup(req)
    assert GatedKnowledge(retriever=FakeDense(gated.retriever.chunks, ml, 0.80), mode="dense", dense_tau=0.85).lookup(req) == []
    with pytest.raises(ValueError):
        GatedKnowledge(retriever=gated.retriever, mode="dense")


def test_every_provider_has_a_version_for_provenance(gated):
    from matcher.knowledge import FixtureKnowledge

    for p in (gated, RagKnowledge(), NoKnowledge(), FixtureKnowledge([])):
        assert isinstance(p.version, str) and p.version
    assert gated.version.startswith("rag.gated.v1;retriever=bm25s-") and "esco=8c6a4b3d0f26" in gated.version
    assert "esco=8c6a4b3d0f26" in RagKnowledge().version


class FakeBM25:
    """BM25-like retriever returning fixed candidates (QA-023 case)."""
    model = None

    def __init__(self, chunks, results):
        self.chunks, self.results = chunks, results

    def search(self, query, k=5, mode="bm25", filters=None):
        return {"status": "found", "results": self.results}


def test_qa023_shared_generic_token_is_not_relevance():
    """QA-023: BM25 matches "Apache Kafka" to "Apache Maven" through the token "Apache". The production provider
    (rag.gated.v1) keeps only a candidate whose label holds the same content words."""
    kafka = {"doc_id": "esco/kafka", "source_type": "esco", "title": "Apache Kafka", "url": "k",
             "text": "Apache Kafka. Also known as: Kafka. Stream processing platform."}
    maven = {"doc_id": "esco/maven", "source_type": "esco", "title": "Apache Maven", "url": "m",
             "text": "Apache Maven. Also known as: Maven. Build tool."}
    only_maven = GatedKnowledge(retriever=FakeBM25([maven], [(maven, 0.9)]), esco=[maven])
    assert only_maven.lookup(R("Experience with Apache Kafka", ["Apache Kafka"])) == []
    both = GatedKnowledge(retriever=FakeBM25([kafka, maven], [(maven, 7.1), (kafka, 0.9)]), esco=[kafka, maven])
    assert titles(both.lookup(R("Experience with Apache Kafka", ["Apache Kafka"]))) == ["Apache Kafka"]
