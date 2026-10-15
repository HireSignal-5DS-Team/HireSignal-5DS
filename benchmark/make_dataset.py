"""Deterministic generator of the HireSignal Matcher benchmark: fully synthetic, anonymized CVs + structured jobs.

No real person, name, e-mail or employer appears. Every gold evidence quote is an exact substring of the CV.
Leakage control: every pool (skills, ESCO alias pairs, project sentences, requirement and CV phrasings, section
titles) is partitioned by index into train / val / test (idx % 5: 0-2 train, 3 val, 4 test), so no phrasing,
skill name or CV text is shared between splits. The test split is LOCKED (see MANIFEST.json).

  python -m benchmark.make_dataset          # writes benchmark/data/{train,val,test}.jsonl + MANIFEST.json
"""
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

VERSION = "bench-v1"
SEED = 20261015
OUT = Path(__file__).parent / "data"
SIZES = {"train": 150, "val": 45, "test": 45}
LOCK_NOTE = "test split is LOCKED: never used for training, prompt tuning or model selection"


def part(pool, split):
    keep = {"train": (0, 1, 2), "val": (3,), "test": (4,)}[split]
    return [x for i, x in enumerate(pool) if i % 5 in keep]


SKILLS = ["Python", "PostgreSQL", "Docker", "React", "Kafka", "TypeScript", "MongoDB", "Kubernetes", "Angular",
          "Spark", "Scala", "Redis", "Terraform", "Vue.js", "Airflow", "Kotlin", "Elasticsearch", "Ansible",
          "Django", "Snowflake", "Swift", "RabbitMQ", "Jenkins", "Flask", "dbt", "PHP", "GraphQL", "GitLab CI",
          "FastAPI", "Tableau", "Rust", "Hadoop", "Spring Boot", "Node.js", "Power BI", "Linux", "Cassandra",
          "Azure", "Pandas", "PyTorch", "Bash", "Neo4j", "AWS", "scikit-learn", "TensorFlow"]
# ESCO preferred label (skill_terms) + requirement text using it + CV sentence using only an ESCO alternative label
ALIASES = [("Apache Maven", "Experience with Apache Maven", "Set up Maven builds for twelve Java services."),
           ("use concurrent programming", "Ability to use concurrent programming", "Sped up the simulation engine with parallel computing on 32 cores."),
           ("Informatica PowerCenter", "Hands-on experience with Informatica PowerCenter", "Maintained PowerCenter Informatica workflows for the data warehouse."),
           ("OWASP ZAP", "Working knowledge of OWASP ZAP", "Ran Zed Attack Proxy scans on every release candidate."),
           ("identify statistical patterns", "Ability to identify statistical patterns in data", "Used survey data to examine statistical patterns in customer churn."),
           ("Sass", "Proficiency in Sass", "Wrote the design system stylesheets in Syntactically Awesome Stylesheets."),
           ("normalise data", "Ability to normalise data before modelling", "Owned data pre-processing for the credit scoring models."),
           ("visual presentation techniques", "Knowledge of visual presentation techniques", "Created information visualization pieces for the annual report."),
           ("model based system engineering", "Background in model based system engineering", "Applied MBSE to the train signalling project."),
           ("MDX", "Experience writing MDX queries", "Wrote MultiDimensional eXpressions queries against the sales cube."),
           ("lead a team", "Proven ability to lead a team", "Asked to supervise a group of people: eight developers and two testers."),
           ("manage schedule of tasks", "Ability to manage schedule of tasks", "Handled task scheduling for the support rota of 15 staff."),
           ("use markup languages", "Ability to use markup languages", "Edited documentation pages in mark-up languages every week."),
           ("Oracle Warehouse Builder", "Hands-on Oracle Warehouse Builder experience", "Built OWB mappings for the finance data mart."),
           ("plan migration to cloud", "Ability to plan migration to cloud", "Led cloud migration planning for 60 on-premise applications."),
           ("troubleshoot", "Strong ability to troubleshoot", "Known in the team as the person who could problem solve outages quickly."),
           ("systems thinking", "Systems thinking", "Recognised for integrated thinking across product, data and operations."),
           ("use software design patterns", "Ability to use software design patterns", "Refactored the payment module around programming design patterns such as strategy and observer."),
           ("design cloud architecture", "Ability to design cloud architecture", "Hired to engineer cloud architecture for a multi-region SaaS product."),
           ("manage system security", "Ability to manage system security", "Asked to manage information security for the clinic's servers.")]
PROJECTS = [("machine learning", "Trained a gradient-boosted classifier that predicts customer churn from usage logs."),
            ("data visualisation", "Designed interactive dashboards showing weekly sales by region for management."),
            ("REST API development", "Implemented HTTP endpoints returning JSON for the order service of a mobile app."),
            ("natural language processing", "Built a model that sorts support tickets by topic from their text."),
            ("version control", "Managed feature branches, pull requests and merges in the team's Git repositories."),
            ("cloud computing", "Ran the platform on EC2 instances with files stored in S3 buckets."),
            ("unit testing", "Wrote pytest suites that check every function of the billing module."),
            ("containerisation", "Packaged each microservice as an image and orchestrated them with docker-compose."),
            ("database design", "Modelled 40 relational tables with primary keys, foreign keys and indexes for the HR system."),
            ("computer vision", "Developed a model that spots scratches in product photos on the assembly line."),
            ("CI/CD", "Set up pipelines that build, test and deploy every commit to staging automatically."),
            ("statistics", "Ran A/B tests and computed confidence intervals for conversion rates."),
            ("web scraping", "Wrote crawlers that extracted product prices from 30 retailer websites."),
            ("agile methodology", "Ran two-week sprints with daily stand-ups and retrospectives for a team of six."),
            ("time series forecasting", "Predicted next-month electricity demand from five years of hourly meter readings.")]
# ESCO skill required; the CV only shows a neighbouring activity sharing words with it (gold: not documented)
NEAR = [("cloud security and compliance", "Experience with cloud security and compliance", "Deployed web applications to a public cloud."),
        ("statistical process control", "Knowledge of statistical process control", "Produced monthly statistical reports for the finance team."),
        ("define database physical structure", "Ability to define database physical structure", "Wrote SQL queries against the reporting database."),
        ("perform risk analysis", "Ability to perform risk analysis", "Performed analysis of website traffic for the marketing team."),
        ("design interaction model", "Ability to design interaction model for voice assistants", "Designed the visual style of the company website."),
        ("embedded systems", "Experience with embedded systems", "Built desktop systems for warehouse inventory tracking."),
        ("perform business analysis", "Ability to perform business analysis", "Performed code reviews for the business intelligence team."),
        ("establish data processes", "Ability to establish data processes", "Documented data definitions in the data catalogue."),
        ("maintain information network hardware", "Ability to maintain information network hardware", "Maintained the team's information wiki."),
        ("apply statistical analysis techniques", "Ability to apply statistical analysis techniques", "Applied for a statistical analysis grant on behalf of the lab.")]
CERTS = ["AWS Certified Solutions Architect", "Certified Kubernetes Administrator", "PMP",
         "Microsoft Azure Administrator Associate", "Google Professional Data Engineer", "CompTIA Security+",
         "Oracle Certified Professional Java SE", "Professional Scrum Master I", "CISSP", "Databricks Certified Data Engineer"]
LANGS = ["French", "German", "Dutch", "Spanish", "Arabic", "Italian", "Polish", "Swedish", "Portuguese", "Turkish"]

REQ_SKILL = ["Proficiency in {s}", "Strong {s} skills", "Hands-on experience with {s}", "Working knowledge of {s}",
             "Solid background in {s}"]
REQ_YEARS = ["At least {n} years of experience with {s}", "{n}+ years of professional {s} experience",
             "Minimum {n} years working with {s}", "{s}: {n} years of experience or more",
             "Experience with {s} for at least {n} years"]
CV_DIRECT = ["Built and maintained internal tools in {s}.", "Delivered three production projects using {s}.",
             "Refactored legacy modules with {s} to cut run time by 40%.", "Led the migration of reporting jobs to {s}.",
             "Developed the customer analytics backend with {s}."]
CV_NEGATED = ["Has not worked with {s} so far.", "No exposure to {s} yet.", "{s}: never used in a project.",
              "Did not use {s}; the team chose other tools.", "Not yet familiar with {s}."]
CV_PARTIAL = ["Some familiarity with {s}.", "Attended a one-day introduction to {s}.", "Basic {s} notions from an online course.",
              "Watched tutorials about {s} in spare time.", "Exposure to {s} through a colleague's project."]
CV_YEARS = ["{m} years of hands-on {s} development.", "Worked with {s} for {m} years in a fintech team.",
            "{m} years of professional {s} experience.", "{s} in daily use for {m} years.",
            "Over the last {m} years, {s} was the main tool at work."]
CV_RANGE = ["{s} engineer at a logistics company ({y1} - {y2}).", "{s} developer, retail sector, {y1} to {y2}.",
            "Backend role focused on {s} ({y1} - {y2}).", "{s} consultant for public clients ({y1} - {y2}).",
            "Member of the {s} platform team, {y1} - {y2}."]
CV_VAGUE = ["Used {s} on several freelance projects.", "{s} came up in a number of university assignments.",
            "Touched {s} occasionally in previous roles.", "Applied {s} in various side projects over time.",
            "Familiar with {s} from different short missions."]
CV_CERT_OK = ["Certified: {c} ({y}).", "Certification - {c}, obtained {y}.", "{c} (certified {y}).",
              "Holder of the {c} certificate since {y}.", "Earned the {c} credential in {y}."]
CV_CERT_NO = ["Currently preparing for the {c} exam.", "Plans to sit the {c} exam next year.",
              "Studying for {c}; not certified yet.", "Enrolled in a {c} preparation course.",
              "{c} exam scheduled, not yet passed."]
EDU_REQ = ["Master's degree in computer science or a related field", "MSc in a computing discipline",
           "Master-level degree in computer science or related", "Postgraduate (master) degree in a computing field",
           "Master's in computer science, software engineering or similar"]
EDU_OK = ["MSc in Computer Science, technical university ({y}).", "Master of Science in Software Engineering ({y}).",
          "MSc Computer Science and Data ({y}).", "Master's degree in Computer Engineering, {y}.",
          "MSc in Informatics, graduated {y}."]
EDU_NO = ["BSc in Business Administration ({y}).", "Bachelor of Arts in History ({y}).", "BSc in Biology, {y}.",
          "Bachelor's degree in Marketing ({y}).", "BA in Economics, graduated {y}."]
EDU_TERMS = ["master", "MSc", "Master of Science"]
LANG_REQ = ["Fluent {l}", "Professional working proficiency in {l}", "Excellent written and spoken {l}",
            "{l} at C1 level or above", "Full professional {l}"]
LANG_OK = ["{l} (C2), English (C1)", "{l}: native speaker", "{l} - fluent (C1)", "Spoken languages: {l} (C2)", "{l} (bilingual)"]
LANG_NO = ["{l} (A1, beginner)", "{l}: basic tourist level", "{l} - elementary (A2)", "Spoken languages: {l} (A1)",
           "{l} (just started learning)"]
HEADERS = ["Candidate profile", "Anonymized CV", "Applicant summary", "Profile (anonymized)", "Candidate record"]
SECTIONS = [("Summary", "Experience", "Education", "Languages", "Certifications", "Other"),
            ("Profile", "Work history", "Studies", "Languages", "Credentials", "Interests"),
            ("About", "Professional experience", "Education", "Language skills", "Certificates", "Miscellaneous"),
            ("Overview", "Career", "Academic background", "Languages", "Qualifications", "Additional information"),
            ("Introduction", "Employment", "Degrees", "Languages spoken", "Licences and certificates", "Extra")]
SUMMARIES = ["Software professional with experience across several industries.", "Engineer who enjoys turning data into products.",
             "Technology generalist looking for a long-term team.", "Developer with a background in consulting projects.",
             "IT specialist motivated by reliable, maintainable systems."]
DISTRACT = ["Interests: hiking, photography, cooking.", "Volunteer: teaches chess at a community centre.",
            "Won a regional hackathon with a {t} prototype.", "Runs a small blog about urban gardening.",
            "Mentored two interns on {t} basics during a summer.", "Hobby: restores vintage bicycles.",
            "Gave a meetup talk about {t} tooling.", "Plays in an amateur football league.",
            "Organised the office charity run.", "Translated open-source docs for a {t} library."]
BULLETS = ["- ", "• ", "* ", "", "– "]

ITEM_TYPES = ["direct", "alias", "project", "missing", "negated", "partial", "years_ok", "range_ok", "years_low",
              "vague", "near", "edu", "cert", "lang"]


def item(kind, split, rng, used):
    """One requirement + the CV lines it injects (section, text) + gold. `used` holds skills taken in this case."""
    P = lambda pool: rng.choice(part(pool, split))  # noqa: E731
    def skill():
        s = rng.choice([x for x in part(SKILLS, split) if x not in used])
        used.add(s)
        return s
    y = rng.randint(2012, 2024)
    if kind in ("direct", "missing", "negated", "partial"):
        s = skill()
        req = {"text": P(REQ_SKILL).format(s=s), "category": "skill", "skill_terms": [s]}
        line, gold, tags = {
            "direct": (P(CV_DIRECT), ("MET", "supported"), ["direct_match"]),
            "missing": (None, ("MISSING", "not_documented"), ["missing_evidence"]),
            "negated": (P(CV_NEGATED), ("MISSING", "contradicted"), ["contradictory_evidence", "negation_trap"]),
            "partial": (P(CV_PARTIAL), ("UNCERTAIN", "ambiguous"), ["partial_evidence"]),
        }[kind]
        lines = [("exp", line.format(s=s))] if line else []
    elif kind in ("years_ok", "range_ok", "years_low", "vague"):
        s, n = skill(), rng.randint(2, 6)
        req = {"text": P(REQ_YEARS).format(s=s, n=n), "category": "experience", "skill_terms": [s], "min_years": n}
        if kind == "years_ok":
            text, gold, tags = P(CV_YEARS).format(s=s, m=n + rng.randint(0, 4)), ("MET", "supported"), ["sufficient_experience"]
        elif kind == "range_ok":
            y1 = rng.randint(2010, 2026 - n)
            y2 = rng.choice([str(min(2026, y1 + n + rng.randint(0, 3))), "present"])
            text, gold, tags = P(CV_RANGE).format(s=s, y1=y1, y2=y2), ("MET", "supported"), ["sufficient_experience", "date_range"]
        elif kind == "years_low":
            text, gold, tags = P(CV_YEARS).format(s=s, m=rng.randint(1, n - 1)), ("MISSING", "contradicted"), ["insufficient_experience"]
        else:
            text, gold, tags = P(CV_VAGUE).format(s=s), ("UNCERTAIN", "ambiguous"), ["ambiguous_duration"]
        lines = [("exp", text)]
    elif kind == "alias":
        label, rtext, sentence = P(ALIASES)
        used.add(label)
        req = {"text": rtext, "category": "skill", "skill_terms": [label]}
        lines, gold, tags = [("exp", sentence)], ("MET", "supported"), ["equivalent_skill_alias"]
    elif kind == "project":
        sk, sentence = P(PROJECTS)
        used.add(sk)
        req = {"text": P(REQ_SKILL).format(s=sk), "category": "skill", "skill_terms": [sk]}
        lines, gold, tags = [("exp", sentence)], ("MET", "supported"), ["implicit_project_evidence"]
    elif kind == "near":
        label, rtext, sentence = P(NEAR)
        used.add(label)
        req = {"text": rtext, "category": "skill", "skill_terms": [label]}
        lines, gold, tags = [("exp", sentence)], ("MISSING", "not_documented"), ["rag_suggests_absent_skill"]
    elif kind == "edu":
        req = {"text": P(EDU_REQ), "category": "education", "skill_terms": EDU_TERMS}
        v = rng.choice(["ok", "no", "none"])
        lines = {"ok": [("edu", P(EDU_OK).format(y=y))], "no": [("edu", P(EDU_NO).format(y=y))], "none": []}[v]
        gold, tags = {"ok": (("MET", "supported"), ["education"]), "no": (("MISSING", "contradicted"), ["education", "contradictory_evidence"]),
                      "none": (("MISSING", "not_documented"), ["education", "missing_evidence"])}[v]
    elif kind == "cert":
        c = P(CERTS)
        req = {"text": f"{c} certification", "category": "certification", "skill_terms": [c]}
        v = rng.choice(["ok", "no"])
        lines = [("cert", P(CV_CERT_OK if v == "ok" else CV_CERT_NO).format(c=c, y=y))]
        gold, tags = ((("MET", "supported"), ["certification"]) if v == "ok"
                      else (("MISSING", "contradicted"), ["certification", "contradictory_evidence", "negation_trap"]))
    else:  # lang
        lang = P(LANGS)
        req = {"text": P(LANG_REQ).format(l=lang), "category": "language", "skill_terms": [lang]}
        v = rng.choice(["ok", "no"])
        lines = [("lang", P(LANG_OK if v == "ok" else LANG_NO).format(l=lang))]
        gold, tags = ((("MET", "supported"), ["language"]) if v == "ok"
                      else (("MISSING", "contradicted"), ["language", "contradictory_evidence"]))
    req["kind"] = "nice" if rng.random() < 0.25 else "must"
    evidence = [t for _, t in lines] if gold[1] in ("supported", "contradicted") else []
    return req, lines, {"decision": gold[0], "basis": gold[1], "evidence": evidence, "tags": tags}


def one_year(t):
    return re.sub(r"\b1 years\b", "1 year", t)


class Collision(Exception):
    pass


def make_case(split, i, rng, kinds):
    used = set()
    reqs, golds, lines = [], {}, []
    for j, kind in enumerate(kinds, 1):
        req, ls, gold = item(kind, split, rng, used)
        rid = f"r{j}"
        reqs.append({"req_id": rid, **req})
        golds[rid] = gold
        lines += [(sec, one_year(t)) for sec, t in ls]
        gold["evidence"] = [one_year(t) for t in gold["evidence"]]
    distract = rng.random() < 0.5
    titles = rng.choice(part(SECTIONS, split))
    bullet = rng.choice(BULLETS)
    others = [d.format(t=rng.choice([s for s in part(SKILLS, split) if s not in used]))
              for d in rng.sample(part(DISTRACT, split), k=min(2, len(part(DISTRACT, split))))] if distract else []
    body = {"exp": [t for s, t in lines if s == "exp"], "edu": [t for s, t in lines if s == "edu"],
            "lang": [t for s, t in lines if s == "lang"], "cert": [t for s, t in lines if s == "cert"]}
    rng.shuffle(body["exp"])
    if distract:  # irrelevant details mixed into experience too
        body["exp"].insert(rng.randint(0, len(body["exp"])), rng.choice(part(SUMMARIES, split)))
    blocks = [rng.choice(part(HEADERS, split)), "", titles[0], rng.choice(part(SUMMARIES, split))]
    for key, title in (("exp", titles[1]), ("edu", titles[2]), ("lang", titles[3]), ("cert", titles[4])):
        if body[key]:
            blocks += ["", title, *(bullet + t for t in body[key])]
    if others:
        blocks += ["", titles[5], *(bullet + t for t in others)]
    text = "\n".join(blocks)
    for rid, g in golds.items():
        assert all(q in text for q in g["evidence"]), (split, i, rid)
        if distract:
            g["tags"].append("distractor_details")
        if len(kinds) >= 5:
            g["tags"].append("multi_requirement")
    for r in reqs:  # an undocumented requirement must really be absent
        if golds[r["req_id"]]["basis"] == "not_documented" and r["category"] != "education":
            if any(t.casefold() in text.casefold() for t in r["skill_terms"]):
                raise Collision(r["req_id"])  # e.g. a missing "Kubernetes" inside a certification name: resample
    cid = f"{split}-{i:03d}"
    return {"case_id": cid, "family": f"{split}-t{SECTIONS.index(titles)}-b{BULLETS.index(bullet)}", "split": split,
            "cv": {"cv_id": f"cv-{cid}", "text": text},
            "job": {"job_id": f"job-{cid}", "title": "Synthetic technical role", "requirements": reqs}, "gold": golds}


def generate(seed=SEED):
    out = {}
    for split, n in SIZES.items():
        rng = random.Random(f"{seed}-{split}")
        cycle = ITEM_TYPES * 100
        rng.shuffle(cycle)
        pos, cases = 0, []
        for i in range(n):
            k = rng.randint(3, 6)
            kinds = []
            while len(kinds) < k:  # one education / certification / language requirement per job at most
                kd = cycle[pos]
                pos += 1
                if kd in ("edu", "cert", "lang") and kd in kinds:
                    continue
                kinds.append(kd)
            for _ in range(50):
                try:
                    cases.append(make_case(split, i, rng, kinds))
                    break
                except Collision:
                    continue
            else:
                raise RuntimeError(f"could not build {split} case {i}")
        out[split] = cases
    return out


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(out_dir=OUT, seed=SEED):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data = generate(seed)
    manifest = {"version": VERSION, "seed": seed, "note": LOCK_NOTE, "generator": "benchmark/make_dataset.py", "splits": {}}
    for split, cases in data.items():
        p = out_dir / f"{split}.jsonl"
        p.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8")
        golds = [g for c in cases for g in c["gold"].values()]
        manifest["splits"][split] = {
            "file": p.name, "sha256": sha256(p), "cases": len(cases), "requirements": len(golds),
            "decisions": dict(Counter(g["decision"] for g in golds)),
            "basis": dict(Counter(g["basis"] for g in golds)),
            "tags": dict(sorted(Counter(t for g in golds for t in g["tags"]).items()))}
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    print(json.dumps(write(), indent=2))
