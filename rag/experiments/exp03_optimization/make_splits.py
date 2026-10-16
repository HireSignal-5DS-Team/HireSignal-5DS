"""Create the calibration split (template-generated, seed 0) and the sealed final test set (hand-written).
Every gold is validated against the sources; every no-answer is validated by absence. Run once; outputs are committed.

    python make_splits.py
"""
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "exp02_benchmark"))
from chunkers import sentences  # noqa: E402
from corpus import load_esco, load_jobs  # noqa: E402

E = {e["doc_id"]: e for e in load_esco()}
J = {j["doc_id"]: j for j in load_jobs()}
U = "http://data.europa.eu/esco/skill/"
USED = set()  # gold URIs / quotes already used by dev or holdout
for f in (HERE.parents[1] / "eval/queries_reviewed.jsonl", HERE.parents[1] / "eval/review/rejected_queries.jsonl",
          HERE.parent / "exp02_benchmark/holdout_queries.jsonl"):
    for q in map(json.loads, open(f, encoding="utf-8")):
        USED |= set(q.get("gold_uris", [])) | set(q.get("gold_quotes", []))


def absent_in(text, pattern):
    return not re.search(pattern, text, re.I)


def esco_absent(pattern):
    return all(absent_in(e["text"], pattern) for e in E.values())


def calibration():
    rng = random.Random(0)
    out = []
    jobs = sorted(J)
    rng.shuffle(jobs)
    pos_terms = [("Python", r"\bPython\b"), ("SQL", r"\bSQL\b"), ("a security clearance", r"clearance"),
                 ("U.S. citizenship", r"U\.S\. Citizen"), ("a degree", r"\bdegree\b"), ("statistics", r"statistic"),
                 ("machine learning", r"machine learning"), ("cloud experience", r"\bcloud\b"),
                 ("a background investigation", r"background investigation"), ("data visualization", r"visuali[sz]")]
    neg_terms = [("Salesforce administration", r"Salesforce"), ("SAP ERP", r"\bSAP\b"), ("Spanish language skills", r"Spanish"),
                 ("a commercial pilot licence", r"pilot licen"), ("CPA certification", r"\bCPA\b"),
                 ("React Native mobile development", r"React"), ("Figma design", r"Figma"), ("a nursing licence", r"nurs"),
                 ("Jira administration", r"\bJira\b"), ("Snowflake", r"Snowflake")]
    for jid in jobs[:10]:  # answerable, job-scoped: gold = every sentence that mentions the term
        body = J[jid]["text"]
        label, pat = rng.choice([t for t in pos_terms if re.search(t[1], body, re.I)])
        gold = sorted({body[s:e] for s, e in sentences(body) if re.search(pat, body[s:e], re.I)})
        out.append({"qid": f"CJ{len(out)+1:02d}", "type": "job", "job_id": jid, "query": f"Does this position require {label}?",
                    "gold_quotes": gold, "split": "calibration"})
    for jid in jobs[10:]:  # unsupported, job-scoped: the term does not occur in the posting
        body = J[jid]["text"]
        label, pat = rng.choice([t for t in neg_terms if absent_in(body, t[1])])
        assert absent_in(body, pat), (jid, label)
        out.append({"qid": f"CN{len(out)-9:02d}", "type": "none", "collection": "job", "job_id": jid,
                    "query": f"Does this position require {label}?", "absence_check": f"/{pat}/i not in {jid}",
                    "split": "calibration"})
    concepts = [u for u in sorted(E) if u not in USED and "Also known as:" in E[u]["text"]]
    for u in rng.sample(concepts, 10):  # answerable ESCO: query = one alternative label
        alts = E[u]["text"].split("Also known as: ", 1)[1].split(". ", 1)[0].split("; ")
        out.append({"qid": f"CE{sum(q['type']=='esco' for q in out)+1:02d}", "type": "esco",
                    "query": f"experience with {rng.choice(alts)}", "gold_uris": [u], "gold_labels": [E[u]["title"]],
                    "split": "calibration"})
    for i, (label, pat) in enumerate([("beekeeping", r"beekeep"), ("plumbing pipe installation", r"plumb"),
                                      ("veterinary surgery", r"veterinar"), ("ballet dance", r"ballet"),
                                      ("pottery and ceramics", r"potter|ceramic"), ("fishing vessel navigation", r"fishing"),
                                      ("bread baking", r"bread|bakery"), ("carpentry woodwork", r"carpent"),
                                      ("tattoo artistry", r"tattoo"), ("jewellery design", r"jewel")], 1):
        assert esco_absent(pat), label
        out.append({"qid": f"CX{i:02d}", "type": "none", "collection": "esco", "query": label,
                    "absence_check": f"/{pat}/i matches no ESCO subset entry", "split": "calibration"})
    return out


# Hand-written final test set. Gold quotes are verbatim; job passages and ESCO concepts are not dev/holdout gold.
TEST_JOBS = [
    ("TJ01", "882803700", "en", "perform data analysis with statistical software and share findings",
     "Respond to data requests, perform data analysis using statistical software, and communicate findings to stakeholders."),
    ("TJ02", "882803700", "en", "statistcal softwar for data requests",  # adversarial: typos
     "Respond to data requests, perform data analysis using statistical software, and communicate findings to stakeholders."),
    ("TJ03", "882960000", "en", "review and optimise code for ML models and database queries",
     "review and optimize SQL, Python, and R code related to (ML) models, queries, and database operations"),
    ("TJ04", "883048600", "fr", "traitement automatisé de données statistiques",
     "Ability to use automated data processing techniques to process statistical data"),
    ("TJ05", "883386100", "en", "role-based access control and data protection duties",
     "Implement role based access controls and data protection requirements and document practices for audits."),
    ("TJ06", "883699600", "en", "SQL Server performance tuning and schema design",
     "Strong experience working with Microsoft SQL Server (MSSQL), including schema design, performance tuning, and query optimization."),
    ("TJ07", "884225200", "en", "graph database work to uncover hidden networks",
     "Designs, implements, and maintains the core graph database ecosystem"),
    ("TJ08", "885581200", "fr", "surveiller les solutions d'IA en respectant la sécurité et l'intégrité des données",
     "Assisting in the development, implementation, and monitoring of AI solutions, ensuring adherence to security, data integrity, and quality standards."),
    ("TJ09", "885947600", "en", "apply emerging AI technologies to improve automation",
     "Evaluate and apply artificial intelligence, machine learning, and other emerging technologies to improve data management, analysis, automation, and IT solutions."),
    ("TJ10", "886606600", "en", "data ingestion, validation and preprocessing pipelines",
     "Advises on high-quality data pipelines for ingestion, transformation, validation, quality enforcement, and preprocessing of diverse datasets."),
    ("TJ11", "884501900", "fr", "combinaison de mathématiques, statistiques et informatique dans le diplôme",
     "supplemented by 30 semester hours in a combination of mathematics, statistics, and computer science"),
    ("TJ12", "882835500", "en", "what grade level must prior specialized experience equal",  # paraphrase
     "To be creditable, specialized experience must have been equivalent to at least the GS-13 grade level"),
]
TEST_JOB_NONE = [("TN01", "883699600", "Is a PhD required for this role?", r"Ph\.?D|doctora"),
                 ("TN02", "882960000", "Kubernetes experience required?", r"Kubernetes"),
                 ("TN03", "883048600", "Does the job require French language skills?", r"French"),
                 ("TN04", "885947600", "Salesforce platform administration", r"Salesforce"),
                 ("TN05", "884783000", "experience with SAP ERP systems", r"\bSAP\b"),
                 ("TN06", "883511200", "Is a commercial driver's licence needed?", r"driver")]
TEST_ESCO = [("TE01", "en", "R statistical programming", ["R"]),  # ambiguous one-letter skill name
             ("TE02", "en", "Java backend development", ["Java (computer programming)"]),  # Java vs JavaScript trap
             ("TE03", "fr", "programmation Java", ["Java (computer programming)"]),
             ("TE04", "en", "dataa warehose design", ["data warehouse"]),  # typos
             ("TE05", "en", "data protection regulations", ["data protection"]),
             ("TE06", "fr", "gestion de projet", ["project management", "perform project management"]),
             ("TE07", "en", "web analytics tools", ["web analytics"]),
             ("TE08", "en", "SPARQL queries on linked data", ["SPARQL"]),
             ("TE09", "en", "manage a relational database", ["manage database"]),
             ("TE10", "fr", "mathématiques", ["mathematics"]),
             ("TE11", "en", "LDAP directory services", ["LDAP"]),
             ("TE12", "en", "cloud monitoring and reporting", ["cloud monitoring and reporting"])]
TEST_ESCO_NONE = [("TX01", "embalming", r"embalm"), ("TX02", "horse riding instruction", r"horse"),
                  ("TX03", "glassblowing", r"glass ?blow"), ("TX04", "opera singing", r"opera singer|opera sing"),
                  ("TX05", "chimney sweeping", r"chimney"), ("TX06", "sushi preparation", r"sushi")]


def final_test():
    by_label = {}
    for u, e in E.items():
        by_label.setdefault(e["title"], u)
    out = []
    for qid, cn, lang, q, quote in TEST_JOBS:
        jid = "usajobs-" + cn
        assert quote in J[jid]["text"] and quote not in USED, qid
        out.append({"qid": qid, "type": "job", "job_id": jid, "query": q, "lang": lang, "gold_quotes": [quote], "split": "final_test"})
    for qid, cn, q, pat in TEST_JOB_NONE:
        jid = "usajobs-" + cn
        assert absent_in(J[jid]["text"], pat), qid
        out.append({"qid": qid, "type": "none", "collection": "job", "job_id": jid, "query": q, "lang": "en",
                    "absence_check": f"/{pat}/i not in {jid}", "split": "final_test"})
    for qid, lang, q, labels in TEST_ESCO:
        uris = [by_label[label] for label in labels]
        assert not set(uris) & USED, qid
        out.append({"qid": qid, "type": "esco", "query": q, "lang": lang, "gold_uris": uris, "gold_labels": labels, "split": "final_test"})
    for qid, q, pat in TEST_ESCO_NONE:
        assert esco_absent(pat), qid
        out.append({"qid": qid, "type": "none", "collection": "esco", "query": q, "lang": "en",
                    "absence_check": f"/{pat}/i matches no ESCO subset entry", "split": "final_test"})
    return out


if __name__ == "__main__":
    for name, rows in (("calibration_queries.jsonl", calibration()), ("final_test_queries.jsonl", final_test())):
        with open(HERE / name, "w", encoding="utf-8") as f:
            for q in rows:
                f.write(json.dumps({**q, "labelled_by": "Claude (exp03 authoring pass, 2026-10-14)"}, ensure_ascii=False) + "\n")
        print(name, len(rows))
