"""Seeded programmatic generator for benchmark/data/train.jsonl (LoRA training data only).

Templates, skill phrasings and CV layouts are deliberately different from the hand-authored val/test sets.
Every gold label follows benchmark/LABELING.md; every gold evidence string is a whole generated CV line.
Run: python benchmark/generate_train.py [--n 300] [--seed 13]
"""
import argparse
import json
import random
import re
from pathlib import Path

REF_YEAR = 2026

# canonical name, true equivalents (same skill), related-but-not-equivalent confusers, terms that imply the skill
SKILLS = [
    ("Python", ["Python 3", "CPython"], ["Ruby", "Perl"],
     ["Django", "Flask", "FastAPI", "pandas", "scikit-learn", "sklearn", "PyTorch", "PySpark", "TensorFlow", "MLflow"]),
    ("Java", ["Java SE", "Java 17"], ["JavaScript", "Kotlin"], ["Spring Boot", "Java EE"]),
    ("JavaScript", ["ECMAScript"], ["Java", "Dart"],
     ["TypeScript", "React", "ReactJS", "Angular", "Vue", "Node.js", "NodeJS", "Cypress"]),
    ("TypeScript", [], ["CoffeeScript", "Flow"], ["Angular"]),
    ("C#", [".NET C#"], ["C++", "F#"], [".NET", "ASP.NET", "Unity"]),
    ("C++", ["C++17", "modern C++"], ["C#", "Objective-C"], []),
    ("Go", ["Golang"], ["Rust", "Elixir"], []),
    ("Rust", [], ["Go", "Zig"], []),
    ("Kotlin", [], ["Java", "Scala"], []),
    ("Swift", [], ["Objective-C", "Kotlin"], ["SwiftUI"]),
    ("PHP", ["PHP 8"], ["Python", "Perl"], ["Laravel", "Symfony"]),
    ("Ruby", ["Ruby on Rails"], ["Python", "Crystal"], []),
    ("Scala", [], ["Java", "Kotlin"], []),
    ("R", ["R language"], ["SAS", "Stata"], []),
    ("SQL", ["T-SQL", "PL/SQL"], ["NoSQL", "GraphQL"],
     ["PostgreSQL", "Postgres", "MySQL", "Oracle", "SQL Server", "MSSQL", "BigQuery", "Snowflake", "MariaDB", "dbt"]),
    ("PostgreSQL", ["Postgres"], ["MySQL", "Oracle Database"], []),
    ("MySQL", [], ["PostgreSQL", "SQLite"], []),
    ("Oracle Database", ["Oracle 19c"], ["MySQL", "PostgreSQL"], []),
    ("Microsoft SQL Server", ["MS SQL Server", "MSSQL"], ["MySQL", "Azure Cosmos DB"], []),
    ("MongoDB", ["Mongo"], ["Cassandra", "CouchDB"], []),
    ("Redis", [], ["Memcached", "Hazelcast"], []),
    ("Elasticsearch", [], ["Apache Solr", "Splunk"], []),
    ("Apache Kafka", ["Kafka"], ["RabbitMQ", "Amazon SQS"], []),
    ("RabbitMQ", [], ["Apache Kafka", "ActiveMQ"], []),
    ("Apache Spark", ["Spark", "PySpark"], ["Hadoop MapReduce", "Dask"], ["Databricks"]),
    ("Apache Airflow", ["Airflow"], ["Luigi", "Prefect"], []),
    ("dbt", ["data build tool"], ["Dataform", "Matillion"], []),
    ("Snowflake", [], ["BigQuery", "Amazon Redshift"], []),
    ("BigQuery", ["Google BigQuery"], ["Snowflake", "Amazon Redshift"], []),
    ("Power BI", ["Microsoft Power BI"], ["Tableau", "Looker"], []),
    ("Tableau", [], ["Power BI", "Qlik Sense"], []),
    ("Excel", ["Microsoft Excel"], ["Google Sheets", "LibreOffice Calc"], []),
    ("Docker", ["Docker containers"], ["Vagrant", "Podman"], []),
    ("Kubernetes", ["K8s"], ["Docker Swarm", "HashiCorp Nomad"], ["EKS", "AKS", "GKE", "OpenShift"]),
    ("Terraform", ["HashiCorp Terraform"], ["AWS CloudFormation", "Pulumi"], []),
    ("Ansible", [], ["Puppet", "Chef"], []),
    ("Jenkins", ["Jenkins CI"], ["GitLab CI", "GitHub Actions"], []),
    ("GitLab CI", ["GitLab CI/CD"], ["Jenkins", "Bamboo"], []),
    ("GitHub Actions", [], ["CircleCI", "Travis CI"], []),
    ("Git", [], ["Subversion", "Mercurial"], ["GitHub", "GitLab", "Bitbucket"]),
    ("Linux", ["Ubuntu Linux", "RHEL"], ["Windows Server", "FreeBSD"], ["Ubuntu", "Debian", "CentOS", "Bash"]),
    ("Windows Server", [], ["Linux", "macOS Server"], []),
    ("Bash", ["Bash scripting"], ["PowerShell", "Windows batch files"], []),
    ("PowerShell", [], ["Bash", "VBScript"], []),
    ("AWS", ["Amazon Web Services"], ["Microsoft Azure", "Google Cloud"], ["EKS", "Lambda", "Amazon"]),
    ("Microsoft Azure", ["Azure"], ["AWS", "Google Cloud"], ["AKS"]),
    ("Google Cloud", ["GCP"], ["AWS", "Microsoft Azure"], ["BigQuery", "GKE"]),
    ("Prometheus", [], ["Zabbix", "Nagios"], []),
    ("Grafana", [], ["Kibana", "Datadog"], []),
    ("Datadog", [], ["New Relic", "Grafana"], []),
    ("React", ["React.js", "ReactJS"], ["Angular", "Vue.js"], ["Next.js"]),
    ("Angular", [], ["React", "AngularJS"], []),
    ("Vue.js", ["Vue 3"], ["React", "Svelte"], ["Nuxt"]),
    ("Node.js", ["NodeJS"], ["Deno", "PHP"], ["Express", "NestJS"]),
    ("Django", [], ["Flask", "FastAPI"], []),
    ("Flask", [], ["Django", "Bottle"], []),
    ("Spring Boot", [], ["Quarkus", "Micronaut"], []),
    (".NET", ["ASP.NET Core"], ["Java EE", "Mono"], []),
    ("GraphQL", [], ["gRPC", "SOAP"], []),
    ("REST APIs", ["RESTful APIs"], ["SOAP web services", "gRPC"], []),
    ("scikit-learn", ["sklearn"], ["Weka", "RapidMiner"], []),
    ("PyTorch", [], ["TensorFlow", "JAX"], []),
    ("TensorFlow", ["TensorFlow 2"], ["PyTorch", "MXNet"], []),
    ("pandas", [], ["Polars", "Apache Arrow"], []),
    ("machine learning", ["ML"], ["descriptive statistics", "business intelligence"],
     ["scikit-learn", "sklearn", "PyTorch", "TensorFlow", "MLflow", "XGBoost", "deep learning"]),
    ("natural language processing", ["NLP"], ["computer vision", "speech synthesis"], ["spaCy", "BERT"]),
    ("computer vision", [], ["natural language processing", "image editing"], ["OpenCV", "YOLO"]),
    ("MLflow", [], ["Weights & Biases", "Neptune"], []),
    ("Selenium", ["Selenium WebDriver"], ["Cypress", "Playwright"], []),
    ("Cypress", [], ["Selenium", "Puppeteer"], []),
    ("JMeter", ["Apache JMeter"], ["Gatling", "Locust"], []),
    ("Jira", ["Atlassian Jira"], ["Trello", "Asana"], []),
    ("Scrum", [], ["Kanban", "waterfall delivery"], []),
    ("ITIL", [], ["COBIT", "Six Sigma"], []),
    ("ServiceNow", [], ["Jira Service Management", "Zendesk"], []),
    ("Active Directory", ["Microsoft Active Directory"], ["Okta", "OpenLDAP"], []),
    ("LDAP", ["Lightweight Directory Access Protocol"], ["Kerberos", "RADIUS"], ["OpenLDAP", "Active Directory"]),
    ("VMware vSphere", ["vSphere", "ESXi"], ["Hyper-V", "KVM"], []),
    ("Cisco IOS", [], ["Juniper Junos", "MikroTik RouterOS"], []),
    ("Splunk", [], ["Elastic SIEM", "IBM QRadar"], []),
    ("penetration testing", ["pentesting", "pen testing"], ["vulnerability scanning", "security awareness training"], []),
    ("OAuth 2.0", ["OAuth2"], ["SAML", "LDAP"], []),
    ("microservices", ["microservice architecture"], ["service-oriented architecture", "serverless functions"], []),
    ("Figma", [], ["Sketch", "Adobe XD"], []),
    ("UML", ["Unified Modeling Language"], ["BPMN", "ArchiMate"], []),
    ("SAP ABAP", ["ABAP"], ["SAP Basis", "SAP FICO"], []),
    ("Salesforce", ["Salesforce CRM"], ["Microsoft Dynamics 365", "HubSpot"], []),
    ("Unity", ["Unity3D"], ["Unreal Engine", "Godot"], []),
    ("Android", ["Android SDK"], ["iOS", "HarmonyOS"], []),
    ("iOS", ["iOS SDK"], ["Android", "macOS"], ["SwiftUI"]),
    ("Flutter", [], ["React Native", "Xamarin"], []),
    ("Embedded C", ["embedded C programming"], ["C#", "Arduino sketches"], []),
    ("FreeRTOS", [], ["Zephyr RTOS", "embedded Linux"], []),
]
SKILL_BY_NAME = {s[0]: s for s in SKILLS}

CERTS = [  # (certificate, related-but-different certificate)
    ("AWS Certified Solutions Architect - Associate", "AWS Certified Cloud Practitioner"),
    ("Certified Kubernetes Administrator (CKA)", "Certified Kubernetes Application Developer (CKAD)"),
    ("ISTQB Advanced Test Analyst", "ISTQB Foundation Level"),
    ("CISSP", "SSCP"),
    ("PMP", "CAPM"),
    ("Professional Scrum Master I (PSM I)", "Professional Scrum Product Owner I (PSPO I)"),
    ("Microsoft Azure Administrator (AZ-104)", "Microsoft Azure Fundamentals (AZ-900)"),
    ("Cisco CCNP Enterprise", "Cisco CCNA"),
    ("ITIL 4 Foundation", "COBIT 2019 Foundation"),
    ("Google Professional Data Engineer", "Google Associate Cloud Engineer"),
    ("Oracle Certified Professional Java SE Developer", "Oracle Certified Associate Java SE"),
    ("CompTIA Security+", "CompTIA A+"),
    ("Red Hat Certified Engineer (RHCE)", "Red Hat Certified System Administrator (RHCSA)"),
    ("TOGAF 9 Certified", "ArchiMate 3 Foundation"),
    ("Certified Ethical Hacker (CEH)", "CompTIA PenTest+"),
]
FIELDS = ["Computer Science", "Software Engineering", "Information Systems", "Data Science", "Electrical Engineering",
          "Applied Mathematics", "Cybersecurity", "Information Technology"]
LANGS = ["German", "French", "Spanish", "Italian", "Dutch", "Polish", "Swedish", "Portuguese", "Czech", "Finnish",
         "Danish", "Greek", "Romanian", "Hungarian"]
CEFR = ["A1", "A2", "B1", "B2", "C1", "C2"]
TITLES = ["Software Developer", "Cloud Engineer", "Data Analyst", "Analytics Engineer", "Test Engineer",
          "Infrastructure Specialist", "Application Developer", "Security Engineer", "Solutions Engineer",
          "Integration Developer", "Mobile Engineer", "Systems Engineer", "Technical Consultant", "IT Operations Engineer",
          "Research Engineer", "Web Developer", "Automation Engineer", "Database Developer"]
COMPANIES = ["a regional bank", "an online retailer", "a logistics provider", "a health-tech scale-up", "a utility company",
             "a public administration", "a games studio", "an insurance group", "a telecom operator", "a SaaS vendor",
             "a consulting firm", "a university hospital", "a travel platform", "a car manufacturer", "a media group"]
TASKS = ["deliver customer-facing features", "automate internal workflows", "support a platform migration",
         "build reporting for the operations team", "maintain a legacy product", "integrate third-party services",
         "reduce infrastructure costs", "harden the release process"]

REQ_SKILL = ["Proficiency in {x}", "Hands-on knowledge of {x}", "Practical {x} skills", "Working knowledge of {x}",
             "Demonstrable experience using {x}", "Solid command of {x}", "{x} know-how"]
REQ_YEARS = ["Minimum of {n} years working with {x}", "At least {n} years of hands-on {x}",
             "{x}: {n}+ years of professional use", "{n} or more years of {x} experience"]
REQ_EXPERT = ["Expert-level {x}", "Deep, advanced {x} expertise", "Senior-level mastery of {x}"]
REQ_CONTRA = ["Trainee position; at least {n} years leading {x} teams expected",
              "Internship for students, requires {n}+ years as principal {x} engineer",
              "No experience needed - minimum {n} years of {x} required"]

CV_USE = ["Used {t} daily to {task}.", "Delivered a project for {co} with {t}.", "Applied {t} to {task} at {co}.",
          "Key contribution: {t} work to {task}.", "Responsible for the {t} part of a programme at {co}."]
CV_YEARS = ["{n} years of hands-on {t} work.", "{t} - {n} yrs in production settings.",
            "Worked with {t} for {n} years at {co}.", "{t} ({n} years, professional)."]
CV_RANGE = ["{t} projects from {a} to {b}.", "{t} in production, {a}-{b}."]
CV_VAGUE = ["Touched {t} on a few occasions.", "Some exposure to {t} in past projects.",
            "Occasionally supported colleagues using {t}.", "Familiar with {t} from internal tooling."]
CV_BASIC = ["Basic {t} knowledge (self-taught).", "Beginner level in {t}.", "{t}: elementary, learning on the job."]
CV_NEG = ["Never used {t} professionally.", "Not yet worked with {t}.", "{t}: no practical experience so far.",
          "I have no hands-on {t} experience."]
CV_CERT = ["Certified: {c} ({y})", "{c}, obtained {y}", "Holder of {c} since {y}"]
CV_CERT_NOT = ["{c}: exam scheduled for {y}", "{c} (lapsed, not renewed since {y})", "Preparing for {c}; not yet passed"]

# type -> (weight, decision, basis)
TYPES = {
    "exact": (12, "MET", "supported"), "equivalence": (10, "MET", "supported"), "years_met": (10, "MET", "supported"),
    "cert_met": (5, "MET", "supported"), "edu_met": (4, "MET", "supported"), "lang_met": (4, "MET", "supported"),
    "not_documented": (10, "MISSING", "not_documented"), "related": (8, "MISSING", "not_documented"),
    "cert_related": (2, "MISSING", "not_documented"), "years_short": (5, "MISSING", "contradicted"),
    "negation": (5, "MISSING", "contradicted"), "cert_not": (2, "MISSING", "contradicted"),
    "edu_contra": (2, "MISSING", "contradicted"), "lang_contra": (2, "MISSING", "contradicted"),
    "vague": (7, "UNCERTAIN", "ambiguous"), "basic": (5, "UNCERTAIN", "ambiguous"),
    "listed_no_years": (5, "UNCERTAIN", "ambiguous"), "contradictory": (2, "UNCERTAIN", "ambiguous"),
}
SINGLETON = {"cert": ("cert_met", "cert_related", "cert_not"), "edu": ("edu_met", "edu_contra"),
             "lang": ("lang_met", "lang_contra")}


def mentions(text, term):
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.I) is not None


def make_case(i, rng):
    title, co = rng.choice(TITLES), rng.choice(COMPANIES)
    n_req = rng.choice([4, 5, 5, 5, 6, 6])
    names, weights = list(TYPES), [TYPES[t][0] for t in TYPES]
    types, used_groups = [], set()
    while len(types) < n_req:
        t = rng.choices(names, weights)[0]
        grp = next((g for g, ts in SINGLETON.items() if t in ts), None)
        if grp in used_groups:
            continue
        if grp:
            used_groups.add(grp)
        types.append(t)
    skills = rng.sample(SKILLS, n_req + 4)
    req_skills, fillers = skills[:n_req], skills[n_req:]

    exp, skill_lines, cert_lines, edu_lines, lang_lines = [], [], [], [], []
    reqs, golds, absent_checks, sole_checks = [], [], [], []
    for k, (t, sk) in enumerate(zip(types, req_skills), 1):
        x, eqs, confs, implied = sk
        term = rng.choice(eqs) if (t == "equivalence" and eqs) else x
        if t == "equivalence" and not eqs:
            t = "exact"
        dec, basis = TYPES[t][1:]
        cat, terms, years, ev, tags = "skill", [x], None, [], []
        text = rng.choice(REQ_SKILL).format(x=x)
        fmt = dict(t=term, task=rng.choice(TASKS), co=rng.choice(COMPANIES))
        if t in ("exact", "equivalence"):
            line = rng.choice(CV_USE).format(**fmt)
            exp.append(line)
            ev, tags = [line], [t]
        elif t in ("years_met", "years_short"):
            need = rng.choice([2, 3, 4, 5, 6, 8])
            have = rng.randint(need, need + 5) if t == "years_met" else rng.randint(1, need - 1)
            if rng.random() < 0.3:
                b = rng.choice(["present", REF_YEAR]) if t == "years_met" else rng.randint(2018, REF_YEAR - 1)
                end = REF_YEAR if b == "present" else b
                line = rng.choice(CV_RANGE).format(t=term, a=end - have, b=b)
            else:
                line = rng.choice(CV_YEARS).format(n=have, **fmt)
            exp.append(line)
            text, cat, years = rng.choice(REQ_YEARS).format(n=need, x=x), "experience", need
            ev, tags = [line], ["experience_years"]
        elif t == "vague":
            line = rng.choice(CV_VAGUE).format(**fmt)
            exp.append(line)
            need = rng.choice([2, 3, 4, 5])
            text, cat, years = rng.choice(REQ_YEARS).format(n=need, x=x), "experience", need
            ev, tags = [line], ["ambiguous_duration"]
        elif t == "listed_no_years":
            others = [f[0] for f in rng.sample(fillers, 2)]
            line = "Familiar tools: " + ", ".join(rng.sample([term, *others], 3))
            skill_lines.append(line)
            need = rng.choice([3, 4, 5])
            text, cat, years = rng.choice(REQ_YEARS).format(n=need, x=x), "experience", need
            ev, tags = [line], ["ambiguous_duration"]
        elif t == "basic":
            line = rng.choice(CV_BASIC).format(**fmt)
            skill_lines.append(line)
            text, ev, tags = rng.choice(REQ_EXPERT).format(x=x), [line], ["exact"]
        elif t == "negation":
            line = rng.choice(CV_NEG).format(**fmt)
            skill_lines.append(line)
            ev, tags = [line], ["negation"]
        elif t == "related":
            c = rng.choice(confs)
            exp.append(rng.choice(CV_USE).format(t=c, task=fmt["task"], co=fmt["co"]))
            tags = ["related_not_equivalent", "not_documented"]
            absent_checks.append([x, *eqs, *implied])
        elif t == "not_documented":
            tags = ["not_documented"]
            absent_checks.append([x, *eqs, *implied])
        elif t == "contradictory":
            need = rng.choice([8, 10, 12, 15])
            text, cat, years, tags = rng.choice(REQ_CONTRA).format(n=need, x=x), "experience", need, \
                ["contradictory_requirement"]
        elif t.startswith("cert_"):
            cert, rel = rng.choice(CERTS)
            y = rng.randint(2015, 2025)
            if t == "cert_met":
                line = rng.choice(CV_CERT).format(c=cert, y=y)
            elif t == "cert_related":
                line = rng.choice(CV_CERT).format(c=rel, y=y)
            else:
                line = rng.choice(CV_CERT_NOT).format(c=cert, y=rng.choice([y, 2027]))
            cert_lines.append(line)
            text = rng.choice(["Holds the {c} certification", "{c} required", "Valid {c} certificate"]).format(c=cert)
            cat, terms = "certification", [cert]
            ev = [] if t == "cert_related" else [line]
            tags = ["certification"] + {"cert_met": [], "cert_related": ["related_not_equivalent"],
                                        "cert_not": ["negation"]}[t]
            if t == "cert_related":
                absent_checks.append([cert])
        elif t.startswith("edu_"):
            f = rng.choice(FIELDS)
            if t == "edu_met":
                line = f"{rng.choice(['BSc', 'MSc', 'BEng', 'MEng'])} {f}, {rng.randint(2005, 2023)}"
                text = f"Bachelor's degree or higher in {f} or a related discipline"
            else:
                low = rng.choice([f"Highest qualification: BSc {f}", "Highest qualification: vocational IT certificate",
                                  "Highest qualification: secondary school diploma"])
                line = f"{low} ({rng.randint(2005, 2023)})"
                text = f"{'Master' if 'BSc' in low else 'Bachelor'}'s degree in {f}"
            edu_lines.append(line)
            cat, terms, ev, tags = "education", [], [line], ["education"]
        elif t.startswith("lang_"):
            lang = rng.choice(LANGS)
            need = rng.randint(2, 5)  # B1..C2
            have = rng.randint(need, 5) if t == "lang_met" else rng.randint(0, need - 1)
            lvl = "native" if (t == "lang_met" and rng.random() < 0.2) else CEFR[have]
            line = f"{lang} {lvl}"
            lang_lines.append(line)
            text = rng.choice(["{l} at {v} level or above", "Professional {l} ({v}+)", "{l}: minimum {v}"]).format(
                l=lang, v=CEFR[need])
            cat, terms, ev, tags = "language", [lang], [line], ["language"]
        if t in ("years_short", "negation", "vague", "basic", "listed_no_years"):
            sole_checks.append(([x, *eqs, *implied], ev[0]))  # no other line may mention the skill
        kind = "must" if rng.random() < 0.75 else "nice"
        reqs.append({"req_id": f"q{k}", "text": text, "kind": kind, "category": cat, "skill_terms": terms,
                     "min_years": years})
        golds.append({"decision": dec, "basis": basis, "evidence": ev, "tags": tags})

    filler = [f[0] for f in fillers]
    exp.append(f"Also worked with {filler[0]} and {filler[1]}.")
    skill_lines.append("Other tools: " + ", ".join(filler[2:]))
    lang_lines.append(rng.choice(["English C1", "English native", "English C2"]))
    rng.shuffle(exp)
    text = render(rng, i, title, co, exp, skill_lines, cert_lines, edu_lines, lang_lines)
    for terms in absent_checks:
        if any(mentions(text, t) for t in terms):
            return None  # a supposedly absent skill leaked into the CV; caller resamples
    for terms, line in sole_checks:
        if any(mentions(text.replace(line, ""), t) for t in terms):
            return None
    for g in golds:
        assert all(q in text for q in g["evidence"])
    return {"case_id": f"train-{i:04d}", "split": "train", "source": "generated",
            "cv": {"cv_id": f"cv-train-{i:04d}", "text": text},
            "job": {"job_id": f"job-train-{i:04d}", "title": title, "requirements": reqs},
            "gold": {r["req_id"]: g for r, g in zip(reqs, golds)}}


def render(rng, i, title, co, exp, skills, certs, edu, langs):
    y0 = rng.randint(2008, 2020)
    head = f"{title} at {co}, {y0} onwards"
    layout = rng.randrange(5)
    if layout == 0:  # markdown
        parts = [f"# Applicant G{i:04d}", f"_{head}_", "## Experience", *[f"- {e}" for e in exp],
                 "## Skills", *[f"- {s}" for s in skills]]
        if certs:
            parts += ["## Certificates", *[f"- {c}" for c in certs]]
        parts += ["## Education", *([f"- {e}" for e in edu] or ["- not stated"]), "## Languages", "- " + "; ".join(langs)]
    elif layout == 1:  # yaml-like
        parts = [f"applicant: G{i:04d}", f"headline: {head}", "highlights:", *[f"  - {e}" for e in exp],
                 "skills:", *[f"  - {s}" for s in skills], "certificates:", *[f"  - {c}" for c in certs],
                 "education:", *[f"  - {e}" for e in edu], f"languages: {', '.join(langs)}"]
    elif layout == 2:  # prose
        parts = [f"Applicant G{i:04d}. {head}.", " ".join(exp), " ".join(s if s.endswith(".") else s + "." for s in skills)]
        parts += [" | ".join(certs + edu)] if certs or edu else []
        parts += [f"Spoken languages: {', '.join(langs)}"]
    elif layout == 3:  # caps headers with guillemets
        parts = [f"APPLICANT G{i:04d}", head.upper(), "", "WORK", *[f"» {e}" for e in exp], "", "TOOLING",
                 *[f"» {s}" for s in skills], "", "CREDENTIALS", *[f"» {c}" for c in certs + edu], "", "LANGUAGES",
                 *[f"» {lang}" for lang in langs]]
    else:  # numbered
        parts = [f"G{i:04d} :: {head}", *[f"{n}) {e}" for n, e in enumerate(exp, 1)],
                 "Toolbox >> " + " / ".join(skills), *[f"Credential >> {c}" for c in certs + edu],
                 "Languages >> " + " / ".join(langs)]
    return "\n".join(parts).strip()


def generate(n, seed):
    rng = random.Random(seed)
    out, i = [], 1
    while len(out) < n:
        case = make_case(i, rng)
        if case:
            out.append(case)
            i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--out", default=str(Path(__file__).parent / "data/train.jsonl"))
    args = ap.parse_args()
    cases = generate(args.n, args.seed)
    held = set()
    for split in ("val", "test"):
        p = Path(args.out).parent / f"{split}.jsonl"
        if p.exists():
            held |= {json.loads(line)["cv"]["text"].strip() for line in open(p, encoding="utf-8") if line.strip()}
    assert not any(c["cv"]["text"].strip() in held for c in cases), "train CV text overlaps val/test"
    with open(args.out, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"train: {len(cases)} cases, {sum(len(c['gold']) for c in cases)} requirements -> {args.out}")


if __name__ == "__main__":
    main()
