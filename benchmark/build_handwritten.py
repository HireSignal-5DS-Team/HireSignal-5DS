"""Hand-authored val/test cases for the HireSignal Matcher benchmark (see benchmark/CONTRACT.md, LABELING.md).

All CVs are synthetic and anonymized. Cases are literal data so every label can be reviewed here.
Run: python benchmark/build_handwritten.py  -> writes benchmark/data/val.jsonl and benchmark/data/test.jsonl

Label codes: MET (supported), MISS (MISSING/not_documented), CONTRA (MISSING/contradicted), UNC (UNCERTAIN/ambiguous).
"""
import json
import textwrap
from pathlib import Path

LABELS = {"MET": ("MET", "supported"), "MISS": ("MISSING", "not_documented"),
          "CONTRA": ("MISSING", "contradicted"), "UNC": ("UNCERTAIN", "ambiguous")}


def R(rid, text, label, ev=(), tags=(), cat="skill", terms=(), years=None, kind="must"):
    return {"req": {"req_id": rid, "text": text, "kind": kind, "category": cat, "skill_terms": list(terms),
                    "min_years": years},
            "label": label, "evidence": list(ev), "tags": list(tags)}


def C(case_id, title, cv, reqs):
    return {"case_id": case_id, "title": title, "cv": textwrap.dedent(cv).strip(), "reqs": reqs}


# ----------------------------------------------------------------------------------------------------------------
# VALIDATION SPLIT
# ----------------------------------------------------------------------------------------------------------------
VAL = [
    C("val-001", "Backend Python Developer", """
        CANDIDATE V01 - Backend Developer
        Location: EU (remote)

        SUMMARY
        Backend developer with 6 years of professional Python experience building REST services for logistics and fintech clients.

        EXPERIENCE
        Senior Backend Developer, FreightCo (anonymized) | 2021 - present
        - Designed REST APIs in Python (FastAPI, Django REST Framework) serving 2M requests/day.
        - Migrated reporting jobs from MySQL to Postgres 14; wrote partitioning and index tuning scripts.
        - Containerised services with Docker; deployments run on K8s (EKS) via Helm charts.
        Backend Developer, PayLab (anonymized) | 2019 - 2021
        - Built payment reconciliation services in Python and Celery with Redis as broker.
        - Introduced pytest with 85% coverage and GitHub Actions pipelines.

        SKILLS
        Python, FastAPI, Django, SQL, Postgres, MySQL, Redis, Celery, Docker, Git, Linux
        Infrastructure as code: no hands-on experience with Terraform yet (completed online course only).

        EDUCATION
        BSc Computer Science, 2019

        LANGUAGES
        English (C1), German (B1)
        """, [
        R("r1", "5+ years of professional Python development", "MET",
          ["Backend developer with 6 years of professional Python experience building REST services for logistics and fintech clients."],
          ["experience_years", "exact"], "experience", ["Python"], 5),
        R("r2", "Strong PostgreSQL skills", "MET",
          ["Migrated reporting jobs from MySQL to Postgres 14; wrote partitioning and index tuning scripts."],
          ["equivalence", "rag_only_term"], terms=["PostgreSQL"]),
        R("r3", "Experience running workloads on Kubernetes", "MET",
          ["Containerised services with Docker; deployments run on K8s (EKS) via Helm charts."],
          ["equivalence"], terms=["Kubernetes"]),
        R("r4", "Terraform for infrastructure as code", "CONTRA",
          ["Infrastructure as code: no hands-on experience with Terraform yet (completed online course only)."],
          ["negation"], terms=["Terraform"]),
        R("r5", "Message streaming with Apache Kafka", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["Apache Kafka"], kind="nice"),
        R("r6", "Bachelor's degree in Computer Science or a related field", "MET", ["BSc Computer Science, 2019"],
          ["education"], "education"),
        R("r7", "German at C1 level or higher", "CONTRA", ["English (C1), German (B1)"], ["language"], "language",
          ["German"]),
        R("r8", "Experience leading a backend team", "UNC",
          ["Senior Backend Developer, FreightCo (anonymized) | 2021 - present"], ["exact"], "experience",
          ["team lead"], kind="nice"),
    ]),
    C("val-002", "Data Engineer", """
        Profile - Candidate V02
        I am a data engineer focused on batch and streaming pipelines. Over the last years I have built ETL workflows for retail and energy companies and I enjoy making data reliable.

        Work history
        Data Engineer, GridAnalytics (anonymized), Jul 2021 – present
        Built streaming ingestion with Apache Kafka and Spark Structured Streaming on Databricks. Orchestrated nightly loads with Airflow and modelled the warehouse in Snowflake using dbt.

        BI Developer, ShopMetrics (anonymized), Mar 2018 – Jun 2021
        Developed SSIS packages and T-SQL stored procedures on Microsoft SQL Server; designed star schemas for sales reporting in Power BI.

        Tools: Python, PySpark, SQL, Airflow, dbt, Snowflake, Kafka, Databricks, Azure Data Factory, Git
        Certifications: Microsoft Certified: Azure Data Engineer Associate (2022)
        Education: MSc Business Informatics (2018)
        Languages: Dutch (native), English (fluent)
        """, [
        R("r1", "3+ years of experience with Apache Spark", "MET",
          ["Data Engineer, GridAnalytics (anonymized), Jul 2021 – present",
           "Built streaming ingestion with Apache Kafka and Spark Structured Streaming on Databricks."],
          ["experience_years"], "experience", ["Apache Spark"], 3),
        R("r2", "Experience building pipelines with extract, transform, load processes", "MET",
          ["Over the last years I have built ETL workflows for retail and energy companies"],
          ["rag_only_term", "equivalence"], terms=["extract, transform, load"]),
        R("r3", "Hands-on experience with Google BigQuery", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["BigQuery"]),
        R("r4", "Workflow orchestration with Apache Airflow", "MET",
          ["Orchestrated nightly loads with Airflow and modelled the warehouse in Snowflake using dbt."], ["exact"],
          terms=["Airflow"]),
        R("r5", "Azure Data Engineer Associate certification", "MET",
          ["Certifications: Microsoft Certified: Azure Data Engineer Associate (2022)"], ["certification"],
          "certification", ["Azure Data Engineer Associate"]),
        R("r6", "4+ years of production Python for data processing", "UNC",
          ["Tools: Python, PySpark, SQL, Airflow, dbt, Snowflake, Kafka, Databricks, Azure Data Factory, Git"],
          ["ambiguous_duration"], "experience", ["Python"], 4),
        R("r7", "Fluent English", "MET", ["Languages: Dutch (native), English (fluent)"], ["language"], "language",
          ["English"]),
        R("r8", "Stream processing with Apache Flink", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["Apache Flink"], kind="nice"),
    ]),
    C("val-003", "DevOps Engineer", """
        V03 | DevOps / Infrastructure Engineer

        Key skills
        * CI/CD: Jenkins, GitLab CI
        * Cloud: Microsoft Azure (AKS, Azure DevOps), some exposure to Google Cloud
        * IaC: Terraform (4 years), Ansible
        * Containers: worked with Docker on several projects
        * Monitoring: Prometheus, Grafana
        * Scripting: Bash, PowerShell, Python

        Experience
        2022 - present  DevOps Engineer, InsureNet (anonymized)
          Maintained 40+ Jenkins pipelines and migrated half of them to GitLab CI.
          Provisioned Azure landing zones with Terraform modules.
        2020 - 2022  Systems Administrator, CityHosting (anonymized)
          Administered RHEL and Ubuntu servers; automated patching with Ansible playbooks.

        Certifications
        - Microsoft Certified: Azure Administrator Associate (AZ-104)
        - Certified Kubernetes Administrator (CKA) - in preparation, exam planned

        Education
        Higher professional diploma in Network Engineering (2019)
        """, [
        R("r1", "3+ years of Docker experience", "UNC", ["Containers: worked with Docker on several projects"],
          ["ambiguous_duration"], "experience", ["Docker"], 3),
        R("r2", "Hands-on AWS experience (EC2, IAM, VPC)", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["AWS"]),
        R("r3", "Infrastructure as code with Terraform, 3+ years", "MET", ["IaC: Terraform (4 years), Ansible"],
          ["experience_years"], "experience", ["Terraform"], 3),
        R("r4", "Certified Kubernetes Administrator (CKA)", "CONTRA",
          ["Certified Kubernetes Administrator (CKA) - in preparation, exam planned"], ["certification", "negation"],
          "certification", ["Certified Kubernetes Administrator"]),
        R("r5", "CI/CD pipelines with Jenkins or GitLab CI", "MET",
          ["Maintained 40+ Jenkins pipelines and migrated half of them to GitLab CI."], ["exact"],
          terms=["Jenkins", "GitLab CI"]),
        R("r6", "Linux server administration", "MET",
          ["Administered RHEL and Ubuntu servers; automated patching with Ansible playbooks."], ["equivalence"],
          terms=["Linux"]),
        R("r7", "Observability with Datadog", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["Datadog"], kind="nice"),
        R("r8", "Bachelor's degree in Computer Science", "UNC",
          ["Higher professional diploma in Network Engineering (2019)"], ["education"], "education"),
    ]),
    C("val-004", "Frontend Developer", """
        Candidate V04 – Frontend Engineer
        Junior-to-mid frontend engineer (3 years) with a design background.

        Experience
        Frontend Engineer — Mediapress (anonymized), Sep 2023 – present
        • Built a component library in React with TypeScript and Storybook.
        • Improved Lighthouse performance score from 54 to 91.
        • Fixed colour-contrast and keyboard navigation issues reported in an accessibility audit.
        Junior Web Developer — Studio North (anonymized), Jan 2022 – Aug 2023
        • Maintained WordPress themes (PHP) and jQuery widgets.
        • Wrote unit tests with Jest.

        Skills: JavaScript (ES2022), TypeScript, React, Redux Toolkit, HTML5, CSS/Sass, Figma, Jest, Cypress, REST
        Education: Bachelor of Arts in Graphic Design (2021)
        Languages: Polish (native), English (B2)
        """, [
        R("r1", "4+ years of professional frontend development", "CONTRA",
          ["Junior-to-mid frontend engineer (3 years) with a design background."], ["experience_years"], "experience",
          ["frontend"], 4),
        R("r2", "Strong React skills", "MET", ["Built a component library in React with TypeScript and Storybook."],
          ["exact"], terms=["React"]),
        R("r3", "Experience with Angular", "MISS", [], ["related_not_equivalent", "not_documented"], terms=["Angular"]),
        R("r4", "End-to-end testing (e.g. Cypress or Playwright)", "MET",
          ["Skills: JavaScript (ES2022), TypeScript, React, Redux Toolkit, HTML5, CSS/Sass, Figma, Jest, Cypress, REST"],
          ["exact"], terms=["Cypress", "Playwright"]),
        R("r5", "Delivering WCAG 2.1 AA compliant interfaces", "UNC",
          ["Fixed colour-contrast and keyboard navigation issues reported in an accessibility audit."],
          ["equivalence"], terms=["WCAG"]),
        R("r6", "Bachelor's degree in Computer Science", "CONTRA", ["Education: Bachelor of Arts in Graphic Design (2021)"],
          ["education"], "education"),
        R("r7", "Web performance optimisation", "MET", ["Improved Lighthouse performance score from 54 to 91."],
          ["equivalence"], terms=["web performance"]),
        R("r8", "Java for occasional backend tasks", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["Java"], kind="nice"),
    ]),
    C("val-005", "Machine Learning Engineer", """
        CV V05
        Machine Learning Engineer — 5+ years building production ML systems.

        2021 - present: ML Engineer, RetailAI (anonymized)
         - Trained demand forecasting models with gradient boosting (LightGBM) and scikit-learn pipelines.
         - Served models behind a FastAPI service; tracked experiments with MLflow.
         - Fine-tuned BERT-based text classifiers for product categorisation with PyTorch and Hugging Face Transformers.
        2019 - 2021: Data Scientist, TelcoInsights (anonymized)
         - Churn models in Python (pandas, scikit-learn); A/B test analysis.

        Technical: Python, PyTorch, TensorFlow (basic), scikit-learn, LightGBM, MLflow, Docker, SQL, Spark (basic)
        Education: MSc Artificial Intelligence, 2019; BSc Mathematics, 2017
        Publications: one workshop paper on text classification
        """, [
        R("r1", "5+ years of machine learning experience", "MET",
          ["Machine Learning Engineer — 5+ years building production ML systems."], ["experience_years"],
          "experience", ["machine learning"], 5),
        R("r2", "Classical ML libraries such as scikit-learn", "MET",
          ["Trained demand forecasting models with gradient boosting (LightGBM) and scikit-learn pipelines."],
          ["exact"], terms=["scikit-learn"]),
        R("r3", "Computer vision (image classification, object detection)", "MISS", [],
          ["rag_only_term", "not_documented"], terms=["computer vision"]),
        R("r4", "Natural language processing", "MET",
          ["Fine-tuned BERT-based text classifiers for product categorisation with PyTorch and Hugging Face Transformers."],
          ["rag_only_term", "equivalence"], terms=["natural language processing"]),
        R("r5", "MLOps: experiment tracking and model serving", "MET",
          ["Served models behind a FastAPI service; tracked experiments with MLflow."], ["equivalence"],
          terms=["MLOps", "MLflow"]),
        R("r6", "PhD in machine learning or a related field", "MISS", [], ["education", "not_documented"], "education",
          kind="nice"),
        R("r7", "3+ years of TensorFlow in production", "UNC",
          ["Technical: Python, PyTorch, TensorFlow (basic), scikit-learn, LightGBM, MLflow, Docker, SQL, Spark (basic)"],
          ["ambiguous_duration"], "experience", ["TensorFlow"], 3),
    ]),
    C("val-006", "Junior Data Analyst", """
        Name withheld (V06)
        Recent graduate looking for a first role in data analytics.

        EDUCATION
        BSc Economics and Statistics, University (anonymized), 2022 – 2025
        Thesis: regression analysis of regional housing prices in R.

        INTERNSHIP
        Data Analytics Intern, HealthGroup (anonymized), Jun 2024 – Sep 2024
        - Cleaned survey data in Excel and built pivot-table dashboards.
        - Wrote SQL queries against a MySQL database to extract monthly KPIs.
        - Created a Tableau dashboard for the operations team.

        SKILLS
        Excel (advanced), SQL (intermediate), R, Tableau, basic Python
        Languages: Spanish (native), English (C1), French (A2)
        """, [
        R("r1", "Entry-level position: 10+ years of experience in data analysis required", "UNC", [],
          ["contradictory_requirement"], "experience", ["data analysis"], 10),
        R("r2", "SQL for data extraction", "MET", ["Wrote SQL queries against a MySQL database to extract monthly KPIs."],
          ["exact"], terms=["SQL"]),
        R("r3", "Dashboarding in Power BI", "MISS", [], ["related_not_equivalent", "not_documented"], terms=["Power BI"]),
        R("r4", "Degree in statistics, economics or another quantitative field", "MET",
          ["BSc Economics and Statistics, University (anonymized), 2022 – 2025"], ["education"], "education"),
        R("r5", "Statistical analysis", "MET", ["Thesis: regression analysis of regional housing prices in R."],
          ["equivalence"], terms=["statistics"]),
        R("r6", "Python for data analysis with pandas", "UNC",
          ["Excel (advanced), SQL (intermediate), R, Tableau, basic Python"], ["exact"], terms=["Python", "pandas"]),
        R("r7", "French at B2 level", "CONTRA", ["Languages: Spanish (native), English (C1), French (A2)"], ["language"],
          "language", ["French"], kind="nice"),
    ]),
    C("val-007", "IT Support Specialist", """
        V07 — IT Support / Service Desk

        Summary: Service desk analyst with 2 years in first- and second-line support for a 600-seat organisation.

        Experience
        IT Support Analyst | LogiParts (anonymized) | 2024 - present
        - Resolved ~40 tickets/day in ServiceNow following ITIL incident and request processes.
        - Managed user accounts and group policies in Active Directory; reset MFA for Microsoft 365.
        - Imaged and deployed Windows 11 laptops with Intune.
        Helpdesk Assistant (part-time) | College IT Office | 2022 - 2024
        - Answered phone and walk-in support requests; replaced printer toner and peripherals.

        Certifications: ITIL 4 Foundation (2023); CompTIA A+ (2022)
        Languages: English (native), Welsh (conversational)
        Driving licence: yes
        """, [
        R("r1", "3+ years of IT support experience", "UNC",
          ["Summary: Service desk analyst with 2 years in first- and second-line support for a 600-seat organisation.",
           "Helpdesk Assistant (part-time) | College IT Office | 2022 - 2024"],
          ["experience_years", "ambiguous_duration"], "experience", ["IT support"], 3),
        R("r2", "ITIL Foundation certification", "MET", ["Certifications: ITIL 4 Foundation (2023); CompTIA A+ (2022)"],
          ["certification"], "certification", ["ITIL"]),
        R("r3", "Active Directory administration", "MET",
          ["Managed user accounts and group policies in Active Directory; reset MFA for Microsoft 365."], ["exact"],
          terms=["Active Directory"]),
        R("r4", "macOS device management with Jamf", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["Jamf", "macOS"]),
        R("r5", "Ticketing system experience (e.g. Jira Service Management)", "MET",
          ["Resolved ~40 tickets/day in ServiceNow following ITIL incident and request processes."], ["equivalence"],
          terms=["Jira Service Management"]),
        R("r6", "Experience with directory services", "MET",
          ["Managed user accounts and group policies in Active Directory; reset MFA for Microsoft 365."],
          ["rag_only_term", "equivalence"], terms=["directory service"]),
        R("r7", "Fluent Welsh", "UNC", ["Languages: English (native), Welsh (conversational)"], ["language"],
          "language", ["Welsh"], kind="nice"),
        R("r8", "CompTIA Network+ certification", "MISS", [], ["certification", "related_not_equivalent"],
          "certification", ["CompTIA Network+"], kind="nice"),
    ]),
    C("val-008", "Azure Cloud Architect", """
        Candidate V08
        Cloud solutions architect with a background in .NET development. Since 2017 I have designed workloads on Microsoft Azure, first as a developer and from 2020 onwards as lead architect for a public-sector integrator. Deployments were scripted where possible.

        Selected projects
        - Hub-and-spoke network topology for a regional health authority (Azure Firewall, ExpressRoute, Private Endpoints).
        - Migration of 120 on-premises VMs from VMware to Azure using Azure Migrate.
        - Event-driven integration platform built on Azure Functions and Service Bus.

        Certifications
        Microsoft Certified: Azure Solutions Architect Expert (AZ-305), 2021
        TOGAF 9 Foundation, 2019

        Earlier career
        .NET developer (C#, ASP.NET MVC, SQL Server), 2012 – 2017

        Languages: German (native), English (C1)
        """, [
        R("r1", "7+ years of hands-on Azure experience", "MET",
          ["Since 2017 I have designed workloads on Microsoft Azure"], ["experience_years"], "experience", ["Azure"], 7),
        R("r2", "Azure Solutions Architect Expert certification", "MET",
          ["Microsoft Certified: Azure Solutions Architect Expert (AZ-305), 2021"], ["certification"], "certification",
          ["Azure Solutions Architect Expert"]),
        R("r3", "Google Cloud Professional Cloud Architect certification", "MISS", [],
          ["certification", "related_not_equivalent"], "certification", ["Professional Cloud Architect"], kind="nice"),
        R("r4", "Migration of on-premises workloads to the cloud", "MET",
          ["Migration of 120 on-premises VMs from VMware to Azure using Azure Migrate."], ["exact"],
          terms=["cloud migration"]),
        R("r5", "Kubernetes (AKS) platform design", "MISS", [], ["not_documented"], terms=["Kubernetes", "AKS"]),
        R("r6", "Enterprise architecture framework (TOGAF)", "MET", ["TOGAF 9 Foundation, 2019"], ["certification", "exact"],
          terms=["TOGAF"]),
        R("r7", "Infrastructure as code with Bicep or Terraform", "UNC", ["Deployments were scripted where possible."],
          ["related_not_equivalent"], terms=["Bicep", "Terraform"]),
        R("r8", "Azure networking (firewalls, private connectivity)", "MET",
          ["Hub-and-spoke network topology for a regional health authority (Azure Firewall, ExpressRoute, Private Endpoints)."],
          ["equivalence"], terms=["Azure networking"]),
    ]),
    C("val-009", "Database Administrator", """
        V09 · Database Administrator

        PROFILE
        Oracle DBA with 8 years of experience (Oracle 11g–19c, RAC, Data Guard). Recently supporting a small number of MySQL instances.

        EXPERIENCE
        Senior DBA — Telecom operator (anonymized) — 2018 to present
        • Administered 30+ Oracle 19c databases including RAC clusters and Data Guard standby sites.
        • Automated RMAN backups and restore tests with shell scripts.
        • Tuned slow queries using AWR reports and execution plans.
        DBA — Software vendor (anonymized) — 2016 to 2018
        • Supported Oracle and some PostgreSQL test environments for QA teams.

        CERTIFICATIONS
        Oracle Database Administration 2019 Certified Professional

        EDUCATION
        BSc Information Systems (2015)
        """, [
        R("r1", "5+ years administering PostgreSQL in production", "CONTRA",
          ["DBA — Software vendor (anonymized) — 2016 to 2018",
           "Supported Oracle and some PostgreSQL test environments for QA teams."],
          ["experience_years"], "experience", ["PostgreSQL"], 5),
        R("r2", "Oracle Database administration (RAC, Data Guard)", "MET",
          ["Administered 30+ Oracle 19c databases including RAC clusters and Data Guard standby sites."], ["exact"],
          terms=["Oracle Database"]),
        R("r3", "MySQL administration, 3+ years", "UNC", ["Recently supporting a small number of MySQL instances."],
          ["ambiguous_duration"], "experience", ["MySQL"], 3),
        R("r4", "Backup and recovery automation", "MET", ["Automated RMAN backups and restore tests with shell scripts."],
          ["equivalence"], terms=["backup and recovery"]),
        R("r5", "Microsoft SQL Server administration", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["SQL Server"]),
        R("r6", "Oracle Certified Professional (OCP)", "MET",
          ["Oracle Database Administration 2019 Certified Professional"], ["certification", "equivalence"],
          "certification", ["Oracle Certified Professional"]),
        R("r7", "MongoDB or another NoSQL database", "MISS", [], ["not_documented"], terms=["MongoDB", "NoSQL"],
          kind="nice"),
        R("r8", "SQL performance tuning", "MET", ["Tuned slow queries using AWR reports and execution plans."], ["exact"],
          terms=["performance tuning"]),
    ]),
    C("val-010", "QA Automation Engineer", """
        QA Engineer — candidate V10
        Experience: 4 yrs
        Mostly manual testing, moving into automation.

        2022–present  QA Engineer, BankApp (anonymized)
          – Wrote and executed manual regression test cases in TestRail.
          – Started automating smoke tests with Selenium WebDriver (Java) in 2025.
          – Logged and triaged defects in Jira.
        2021–2022  Junior Tester, GameStudio (anonymized)
          – Exploratory testing of mobile games on Android and iOS.

        Certifications: ISTQB Certified Tester Foundation Level (CTFL)
        Tools: TestRail, Jira, Postman, Selenium, Java (basic), SQL
        Education: Diploma in Software Testing (vocational), 2021
        """, [
        R("r1", "3+ years of test automation experience", "CONTRA",
          ["Started automating smoke tests with Selenium WebDriver (Java) in 2025."], ["experience_years"],
          "experience", ["test automation"], 3),
        R("r2", "ISTQB certification", "MET", ["Certifications: ISTQB Certified Tester Foundation Level (CTFL)"],
          ["certification"], "certification", ["ISTQB"]),
        R("r3", "UI automation with Selenium or Playwright", "MET",
          ["Started automating smoke tests with Selenium WebDriver (Java) in 2025."], ["exact"],
          terms=["Selenium", "Playwright"]),
        R("r4", "2+ years of API test automation", "UNC", ["Tools: TestRail, Jira, Postman, Selenium, Java (basic), SQL"],
          ["ambiguous_duration"], "experience", ["API testing"], 2),
        R("r5", "JavaScript test frameworks such as Cypress", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["JavaScript", "Cypress"]),
        R("r6", "Performance testing with JMeter or k6", "MISS", [], ["not_documented"], terms=["JMeter", "k6"],
          kind="nice"),
        R("r7", "Bachelor's degree in Computer Science", "CONTRA", ["Education: Diploma in Software Testing (vocational), 2021"],
          ["education"], "education", kind="nice"),
        R("r8", "Mobile app testing", "MET", ["Exploratory testing of mobile games on Android and iOS."],
          ["equivalence"], terms=["mobile testing"], kind="nice"),
    ]),
    C("val-011", "Security Analyst (SOC)", """
        V11 — Security Operations

        Profile
        SOC analyst (Tier 2). I monitor alerts, investigate incidents and tune detection rules. Around three years in security operations, previously network support.

        Experience
        SOC Analyst, MSSP (anonymized), Feb 2023 – present
        - Triage of SIEM alerts in Splunk; wrote SPL correlation searches.
        - Incident response for phishing and ransomware cases; playbooks in Cortex XSOAR.
        - Vulnerability scanning with Nessus and follow-up with system owners.
        Network Support Technician, ISP (anonymized), Oct 2020 – Jan 2023
        - Configured Cisco switches and FortiGate firewalls.

        Certifications: CompTIA Security+ (2022); currently studying for OSCP
        Education: BSc Cyber Security (2020)
        Languages: English (C2), Arabic (native)
        """, [
        R("r1", "SIEM experience (Splunk, QRadar or Sentinel)", "MET",
          ["Triage of SIEM alerts in Splunk; wrote SPL correlation searches."], ["exact"], terms=["SIEM", "Splunk"]),
        R("r2", "OSCP certification", "CONTRA", ["Certifications: CompTIA Security+ (2022); currently studying for OSCP"],
          ["certification", "negation"], "certification", ["OSCP"]),
        R("r3", "5+ years of security operations experience", "CONTRA",
          ["Around three years in security operations, previously network support."], ["experience_years"],
          "experience", ["security operations"], 5),
        R("r4", "Penetration testing experience", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["penetration testing"]),
        R("r5", "Proactive threat hunting", "UNC", ["I monitor alerts, investigate incidents and tune detection rules."],
          ["related_not_equivalent"], terms=["threat hunting"], kind="nice"),
        R("r6", "Degree in cyber security or computer science", "MET", ["Education: BSc Cyber Security (2020)"],
          ["education"], "education"),
        R("r7", "Fluent Arabic and English", "MET", ["Languages: English (C2), Arabic (native)"], ["language"],
          "language", ["Arabic", "English"]),
        R("r8", "Graduate programme (0-1 years experience); must have led a SOC team for 5+ years", "UNC", [],
          ["contradictory_requirement"], "experience", ["SOC team lead"], 5),
    ]),
    C("val-012", "Android Developer", """
        V12 Android Developer

        • 2020 – present: Android Developer at FitTrack (anonymized). Kotlin, Jetpack Compose, Coroutines, Room. Published 3 apps with 500k+ installs on Google Play.
        • 2018 – 2020: Java Developer at InsureSoft (anonymized). Spring Boot microservices; occasional Android bug fixes in Java.

        Other: familiar with Flutter from a hackathon; no iOS experience.
        Education: BEng Software Engineering (2018)
        Languages: Portuguese (native), English (B2), Spanish (B1)
        """, [
        R("r1", "5+ years of native Android development", "MET",
          ["2020 – present: Android Developer at FitTrack (anonymized)."], ["experience_years"], "experience",
          ["Android"], 5),
        R("r2", "Kotlin", "MET", ["Kotlin, Jetpack Compose, Coroutines, Room."], ["exact"], terms=["Kotlin"]),
        R("r3", "iOS development with Swift", "CONTRA", ["Other: familiar with Flutter from a hackathon; no iOS experience."],
          ["negation"], terms=["iOS", "Swift"]),
        R("r4", "Cross-platform development with Flutter, 2+ years", "UNC",
          ["Other: familiar with Flutter from a hackathon; no iOS experience."], ["ambiguous_duration"], "experience",
          ["Flutter"], 2),
        R("r5", "Owning app releases end-to-end", "UNC", ["Published 3 apps with 500k+ installs on Google Play."],
          ["equivalence"], terms=["release management"]),
        R("r6", "Backend experience with Java", "MET",
          ["2018 – 2020: Java Developer at InsureSoft (anonymized). Spring Boot microservices; occasional Android bug fixes in Java."],
          ["exact"], terms=["Java"], kind="nice"),
        R("r7", "Engineering degree", "MET", ["Education: BEng Software Engineering (2018)"], ["education"], "education"),
        R("r8", "English at C1 level", "CONTRA", ["Languages: Portuguese (native), English (B2), Spanish (B1)"],
          ["language"], "language", ["English"]),
    ]),
    C("val-013", "IT Project Manager / Scrum Master", """
        Candidate V13 — IT Project Manager

        Summary
        Project manager for software delivery teams. Experienced with Kanban and waterfall delivery; facilitated retrospectives and backlog refinement sessions.

        Professional experience
        2019 - present: IT Project Manager, Public Agency (anonymized)
          Led 3 cross-functional teams (25 people) delivering a case-management platform; managed budget of EUR 2.4M.
          Introduced a Kanban board in Jira and weekly stakeholder reporting.
        2015 - 2019: Business Analyst, Consultancy (anonymized)
          Requirements workshops, UML use cases, user acceptance testing.

        Certifications: PRINCE2 Foundation (2018). PMP: not certified.
        Education: MA Public Administration (2014)
        Languages: Dutch (native), English (fluent), French (basic)
        """, [
        R("r1", "Certified ScrumMaster (CSM) or PSM I", "MISS", [],
          ["certification", "rag_only_term", "not_documented"], "certification", ["Scrum"]),
        R("r2", "3+ years as Scrum Master in agile teams", "UNC",
          ["Experienced with Kanban and waterfall delivery; facilitated retrospectives and backlog refinement sessions."],
          ["related_not_equivalent"], "experience", ["Scrum"], 3),
        R("r3", "Stakeholder management and reporting", "MET",
          ["Introduced a Kanban board in Jira and weekly stakeholder reporting."], ["exact"],
          terms=["stakeholder management"]),
        R("r4", "Budget responsibility", "MET", ["managed budget of EUR 2.4M"], ["equivalence"],
          terms=["budget management"]),
        R("r5", "PMP certification", "CONTRA", ["PMP: not certified."], ["certification", "negation"],
          "certification", ["PMP"], kind="nice"),
        R("r6", "PRINCE2 Practitioner", "UNC", ["Certifications: PRINCE2 Foundation (2018)."],
          ["certification", "related_not_equivalent"], "certification", ["PRINCE2 Practitioner"]),
        R("r7", "Business analysis background", "MET", ["2015 - 2019: Business Analyst, Consultancy (anonymized)"],
          ["exact"], terms=["business analysis"], kind="nice"),
        R("r8", "French at B2 level", "CONTRA", ["Languages: Dutch (native), English (fluent), French (basic)"],
          ["language"], "language", ["French"]),
    ]),
    C("val-014", "Network Engineer", """
        V14 / Network Engineer
        CCNA certified network engineer, 5+ years in enterprise LAN/WAN.

        Work
        Network Engineer – Manufacturing group (anonymized) – 2021 - present
         * Designed and rolled out SD-WAN across 14 plants; OSPF and BGP routing.
         * Managed Cisco Catalyst and Meraki switching; segmented OT networks with VLANs and ACLs.
        Network Administrator – School district (anonymized) – 2019 - 2021
         * Operated Wi-Fi (Aruba) and DHCP/DNS services on Windows Server.

        Certs: Cisco CCNA (2019, renewed 2022), Fortinet NSE 4 (expired)
        Automation: some Python scripting for config backups (Netmiko)
        Education: Associate degree in Network Technology
        """, [
        R("r1", "CCNP Enterprise certification", "MISS", [], ["certification", "related_not_equivalent"],
          "certification", ["CCNP"]),
        R("r2", "5+ years of enterprise networking", "MET",
          ["CCNA certified network engineer, 5+ years in enterprise LAN/WAN."], ["experience_years"], "experience",
          ["enterprise networking"], 5),
        R("r3", "Routing protocols (BGP, OSPF)", "MET",
          ["Designed and rolled out SD-WAN across 14 plants; OSPF and BGP routing."], ["exact"], terms=["BGP", "OSPF"]),
        R("r4", "Strong network automation skills (Python, Ansible)", "UNC",
          ["Automation: some Python scripting for config backups (Netmiko)"], ["exact"],
          terms=["network automation", "Python", "Ansible"]),
        R("r5", "Valid Fortinet NSE 4 certification", "CONTRA",
          ["Certs: Cisco CCNA (2019, renewed 2022), Fortinet NSE 4 (expired)"], ["certification", "negation"],
          "certification", ["Fortinet NSE 4"]),
        R("r6", "Juniper Junos experience", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["Juniper", "Junos"], kind="nice"),
        R("r7", "Enterprise Wi-Fi design including site surveys", "UNC",
          ["Operated Wi-Fi (Aruba) and DHCP/DNS services on Windows Server."], ["related_not_equivalent"],
          terms=["Wi-Fi design"], kind="nice"),
        R("r8", "Bachelor's degree in networking or IT", "CONTRA", ["Education: Associate degree in Network Technology"],
          ["education"], "education"),
    ]),
]

# ----------------------------------------------------------------------------------------------------------------
# TEST SPLIT (LOCKED: final report only; never used for tuning or model selection)
# ----------------------------------------------------------------------------------------------------------------
TEST = [
    C("test-001", "Full-Stack JavaScript Developer", """
        T01 — Full-stack developer

        About me
        Full-stack developer, 4 years with Node.js and TypeScript, before that 2 years of PHP (Laravel).

        Employment
        Mar 2022 – present · Full-stack Developer · TravelBooking (anonymized)
          Node.js/Express and NestJS services, React frontend, GraphQL gateway.
          Data in MongoDB and PostgreSQL; caching with Redis.
        Jan 2020 – Feb 2022 · PHP Developer · Agency (anonymized)
          Laravel and Vue 2 for e-commerce shops on MySQL.

        Stack: TypeScript, JavaScript, Node.js, NestJS, React, Vue, GraphQL, MongoDB, PostgreSQL, Redis, Docker
        Cloud: deployed side projects to Heroku and Vercel
        Education: self-taught; completed a 6-month coding bootcamp (2019)
        Languages: Italian (native), English (C1)
        """, [
        R("r1", "3+ years of Node.js", "MET",
          ["Full-stack developer, 4 years with Node.js and TypeScript, before that 2 years of PHP (Laravel)."],
          ["experience_years"], "experience", ["Node.js"], 3),
        R("r2", "GraphQL API design", "MET", ["Node.js/Express and NestJS services, React frontend, GraphQL gateway."],
          ["exact"], terms=["GraphQL"]),
        R("r3", "Production AWS experience (Lambda, S3)", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["AWS"]),
        R("r4", "Vue 3 with the Composition API", "UNC", ["Laravel and Vue 2 for e-commerce shops on MySQL."],
          ["related_not_equivalent"], terms=["Vue 3"], kind="nice"),
        R("r5", "Computer science degree", "CONTRA",
          ["Education: self-taught; completed a 6-month coding bootcamp (2019)"], ["education"], "education"),
        R("r6", "PostgreSQL performance tuning", "UNC", ["Data in MongoDB and PostgreSQL; caching with Redis."],
          ["exact"], terms=["PostgreSQL"]),
        R("r7", "5+ years of TypeScript", "CONTRA",
          ["Full-stack developer, 4 years with Node.js and TypeScript"], ["experience_years"], "experience",
          ["TypeScript"], 5),
        R("r8", "Native-level Italian", "MET", ["Languages: Italian (native), English (C1)"], ["language"], "language",
          ["Italian"], kind="nice"),
    ]),
    C("test-002", "Site Reliability Engineer", """
        Candidate T02
        Site Reliability / Platform

        I have spent the last four years keeping high-traffic services up. At StreamCo (anonymized; 2022 – present) I run the on-call rotation for a video platform, define SLOs and error budgets, and write post-mortems. Before that I was a Linux administrator at a hosting company (2019 – 2022).

        Technologies I use every day: Kubernetes (GKE), Helm, Argo CD, Prometheus, Grafana, Loki, Go, Python, Terraform, Google Cloud.
        I have only read about service meshes; we have not adopted Istio.
        Certificates: Google Professional Cloud DevOps Engineer (2024), CKA (2023).
        Degree: MSc Computer Engineering.
        Languages: English, Hindi, Marathi.
        """, [
        R("r1", "Kubernetes in production", "MET",
          ["Technologies I use every day: Kubernetes (GKE), Helm, Argo CD, Prometheus, Grafana, Loki, Go, Python, Terraform, Google Cloud."],
          ["exact"], terms=["Kubernetes"]),
        R("r2", "SLO definition and incident post-mortems", "MET",
          ["I run the on-call rotation for a video platform, define SLOs and error budgets, and write post-mortems."],
          ["exact"], terms=["SLO", "post-mortem"]),
        R("r3", "Service mesh (Istio or Linkerd)", "CONTRA",
          ["I have only read about service meshes; we have not adopted Istio."], ["negation"],
          terms=["service mesh", "Istio"]),
        R("r4", "Programming in Go", "MET",
          ["Technologies I use every day: Kubernetes (GKE), Helm, Argo CD, Prometheus, Grafana, Loki, Go, Python, Terraform, Google Cloud."],
          ["exact"], terms=["Go"]),
        R("r5", "Certified Kubernetes Administrator", "MET",
          ["Certificates: Google Professional Cloud DevOps Engineer (2024), CKA (2023)."],
          ["certification", "equivalence"], "certification", ["Certified Kubernetes Administrator"]),
        R("r6", "6+ years of site reliability engineering", "UNC",
          ["I have spent the last four years keeping high-traffic services up.",
           "Before that I was a Linux administrator at a hosting company (2019 – 2022)."],
          ["experience_years", "related_not_equivalent"], "experience", ["site reliability engineering"], 6),
        R("r7", "Experience with AWS", "MISS", [], ["related_not_equivalent", "not_documented"], terms=["AWS"],
          kind="nice"),
        R("r8", "Professional proficiency in Hindi", "UNC", ["Languages: English, Hindi, Marathi."], ["language"],
          "language", ["Hindi"], kind="nice"),
    ]),
    C("test-003", "NLP Engineer", """
        T03 · NLP Engineer
        ---------------------------------
        Experience
        * 2023-present | NLP Engineer | LegalTech startup (anonymized)
          - Built retrieval-augmented question answering over contracts (sentence-transformers, FAISS, Llama-based models).
          - Fine-tuned token classification models for clause extraction with Hugging Face.
        * 2021-2023 | Data Scientist | Insurance (anonymized)
          - Text mining of claim notes: TF-IDF, topic models, spaCy pipelines.
          - Sentiment classifier prototype in Keras.
          - Dashboards in Power BI.

        Skills
        NLP, information extraction, PyTorch, Hugging Face, spaCy, FAISS, SQL, Docker, basic Kubernetes
        Education
        PhD candidate in Computational Linguistics (thesis not yet submitted)
        MSc Computational Linguistics (2021)
        Languages
        English (C2), Romanian (native)
        """, [
        R("r1", "Natural language processing, 3+ years", "MET",
          ["2023-present | NLP Engineer | LegalTech startup (anonymized)",
           "2021-2023 | Data Scientist | Insurance (anonymized)",
           "Text mining of claim notes: TF-IDF, topic models, spaCy pipelines."],
          ["rag_only_term", "equivalence", "experience_years"], "experience", ["natural language processing"], 3),
        R("r2", "Vector search (e.g. FAISS, Milvus)", "MET",
          ["Built retrieval-augmented question answering over contracts (sentence-transformers, FAISS, Llama-based models)."],
          ["exact"], terms=["FAISS", "vector search"]),
        R("r3", "PhD in NLP or computational linguistics", "CONTRA",
          ["PhD candidate in Computational Linguistics (thesis not yet submitted)"], ["education", "negation", "rag_only_term"],
          "education"),
        R("r4", "Speech recognition (ASR)", "MISS", [], ["not_documented"], terms=["speech recognition"], kind="nice"),
        R("r5", "Production Kubernetes operations", "UNC",
          ["NLP, information extraction, PyTorch, Hugging Face, spaCy, FAISS, SQL, Docker, basic Kubernetes"], ["exact"],
          terms=["Kubernetes"], kind="nice"),
        R("r6", "Hugging Face Transformers", "MET",
          ["Fine-tuned token classification models for clause extraction with Hugging Face."], ["exact"],
          terms=["Hugging Face"]),
        R("r7", "Computer vision (OCR on scanned documents)", "MISS", [], ["rag_only_term", "not_documented"],
          terms=["computer vision"]),
        R("r8", "Romanian language", "MET", ["English (C2), Romanian (native)"], ["language"], "language",
          ["Romanian"], kind="nice"),
    ]),
    C("test-004", "BI Developer", """
        T04 BI DEVELOPER

        PROFILE: Business intelligence developer, 7 years. Power BI since 2019; previously Qlik.
        EXPERIENCE
        2019 - present: BI Developer, Energy retailer (anonymized) — Power BI dashboards (DAX, Power Query), Azure SQL Database, SSAS tabular models, row-level security.
        2017 - 2019: Reporting Analyst, Bank (anonymized) — QlikView reports, Excel VBA macros, Oracle SQL.
        SKILLS: Power BI, DAX, T-SQL, SSAS, SSIS, Qlik, Excel, data modelling (Kimball)
        CERTIFICATION: Microsoft Certified: Power BI Data Analyst Associate (PL-300)
        EDUCATION: BSc Business Administration (2017)
        LANGUAGES: English, Afrikaans (native)
        """, [
        R("r1", "5+ years of Power BI", "MET", ["Power BI since 2019"], ["experience_years"], "experience",
          ["Power BI"], 5),
        R("r2", "Tableau dashboard development", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["Tableau"]),
        R("r3", "T-SQL on Microsoft SQL Server", "MET",
          ["SKILLS: Power BI, DAX, T-SQL, SSAS, SSIS, Qlik, Excel, data modelling (Kimball)"], ["exact"],
          terms=["T-SQL"]),
        R("r4", "Dimensional modelling (star schema)", "MET",
          ["SKILLS: Power BI, DAX, T-SQL, SSAS, SSIS, Qlik, Excel, data modelling (Kimball)"], ["equivalence"],
          terms=["dimensional modelling"]),
        R("r5", "PL-300 certification", "MET", ["CERTIFICATION: Microsoft Certified: Power BI Data Analyst Associate (PL-300)"],
          ["certification"], "certification", ["PL-300"]),
        R("r6", "Excel VBA automation, 3+ years", "UNC",
          ["2017 - 2019: Reporting Analyst, Bank (anonymized) — QlikView reports, Excel VBA macros, Oracle SQL."],
          ["ambiguous_duration"], "experience", ["VBA"], 3),
        R("r7", "ETL with Azure Data Factory", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["Azure Data Factory"]),
        R("r8", "Degree in Computer Science, Information Systems or Statistics", "CONTRA",
          ["EDUCATION: BSc Business Administration (2017)"], ["education"], "education"),
    ]),
    C("test-005", "Java Backend Engineer", """
        T05 – Software Engineer (Backend)

        Summary
        Backend engineer working mainly in Java 17 and Spring Boot. 8 years of experience in total, of which the last 3 in fintech.

        Experience
        Backend Engineer, PaymentsHub (anonymized), Apr 2023 – present
        – Event-driven microservices with Spring Boot and Apache Kafka; PostgreSQL with Flyway migrations.
        – Introduced contract testing (Pact) and raised test coverage to 80%.
        Software Engineer, Logistics Corp (anonymized), Sep 2018 – Mar 2023
        – Maintained a monolith in Java 8 (Spring MVC, Hibernate, Oracle).
        – Wrote small internal tools in Kotlin.
        Junior Developer, Web agency (anonymized), 2017 – 2018
        – PHP and JavaScript websites.

        Skills: Java, Spring Boot, Kafka, PostgreSQL, Oracle, Hibernate, JUnit 5, Mockito, Maven, Gradle, Git, Docker
        Education: MSc Software Engineering
        Languages: Czech (native), English (C1), German (A2)
        """, [
        R("r1", "6+ years of Java development", "MET",
          ["Backend Engineer, PaymentsHub (anonymized), Apr 2023 – present",
           "Software Engineer, Logistics Corp (anonymized), Sep 2018 – Mar 2023",
           "Maintained a monolith in Java 8 (Spring MVC, Hibernate, Oracle)."],
          ["experience_years"], "experience", ["Java"], 6),
        R("r2", "Apache Kafka", "MET",
          ["Event-driven microservices with Spring Boot and Apache Kafka; PostgreSQL with Flyway migrations."],
          ["exact"], terms=["Apache Kafka"]),
        R("r3", "Kotlin backend development, 2+ years", "UNC", ["Wrote small internal tools in Kotlin."],
          ["ambiguous_duration"], "experience", ["Kotlin"], 2),
        R("r4", "Scala", "MISS", [], ["related_not_equivalent", "not_documented"], terms=["Scala"], kind="nice"),
        R("r5", "Frontend development with React", "UNC", ["PHP and JavaScript websites."],
          ["related_not_equivalent"], terms=["React"], kind="nice"),
        R("r6", "Master's degree in Software Engineering or Computer Science", "MET",
          ["Education: MSc Software Engineering"], ["education"], "education"),
        R("r7", "German at B2 or higher", "CONTRA", ["Languages: Czech (native), English (C1), German (A2)"],
          ["language"], "language", ["German"]),
        R("r8", "Postgres database design", "MET",
          ["Event-driven microservices with Spring Boot and Apache Kafka; PostgreSQL with Flyway migrations."],
          ["equivalence", "rag_only_term"], terms=["Postgres"]),
    ]),
    C("test-006", "Embedded Software Engineer", """
        T06 — Embedded Software Engineer

        Experience
        • Firmware Engineer, Medical devices (anonymized), 2020 – present
          Bare-metal and FreeRTOS firmware in C for STM32 (ARM Cortex-M4) microcontrollers; IEC 62304 documentation.
          Drivers for SPI, I2C and UART peripherals; bring-up with oscilloscope and logic analyser.
        • Graduate Engineer, Automotive supplier (anonymized), 2018 – 2020
          Unit testing of infotainment software; some C++ for test harnesses.

        Skills: C (expert), C++ (intermediate), Python (test scripts), FreeRTOS, STM32, Git, Jenkins
        I have not worked with embedded Linux or Yocto.
        Education: BEng Electronic Engineering (2018)
        Languages: English (native)
        """, [
        R("r1", "Embedded C, 5+ years", "MET",
          ["Firmware Engineer, Medical devices (anonymized), 2020 – present",
           "Bare-metal and FreeRTOS firmware in C for STM32 (ARM Cortex-M4) microcontrollers; IEC 62304 documentation."],
          ["experience_years"], "experience", ["embedded C"], 5),
        R("r2", "Real-time operating systems", "MET",
          ["Bare-metal and FreeRTOS firmware in C for STM32 (ARM Cortex-M4) microcontrollers; IEC 62304 documentation."],
          ["equivalence"], terms=["RTOS"]),
        R("r3", "Embedded Linux (Yocto)", "CONTRA", ["I have not worked with embedded Linux or Yocto."], ["negation"],
          terms=["embedded Linux", "Yocto"]),
        R("r4", "Advanced modern C++ (C++17)", "UNC",
          ["Skills: C (expert), C++ (intermediate), Python (test scripts), FreeRTOS, STM32, Git, Jenkins"], ["exact"],
          terms=["C++"]),
        R("r5", "Medical device software standards (IEC 62304)", "MET",
          ["Bare-metal and FreeRTOS firmware in C for STM32 (ARM Cortex-M4) microcontrollers; IEC 62304 documentation."],
          ["exact"], terms=["IEC 62304"], kind="nice"),
        R("r6", "Rust for embedded targets", "MISS", [], ["not_documented"], terms=["Rust"], kind="nice"),
        R("r7", "Degree in electronics or computer engineering", "MET", ["Education: BEng Electronic Engineering (2018)"],
          ["education"], "education"),
        R("r8", "CAN bus communication", "MISS", [], ["related_not_equivalent", "not_documented"], terms=["CAN bus"]),
    ]),
    C("test-007", "Linux Systems Administrator", """
        Candidate T07

        Systems administrator. 10 yrs Linux (Debian, CentOS, RHEL) and VMware vSphere.

        2016 - present | Senior Sysadmin | University data centre (anonymized)
          Run ~400 Linux VMs on VMware vSphere; Puppet for configuration management.
          Backup with Bacula; monitoring with Zabbix and Nagios.
          Scripting in Bash and Perl.
        2014 - 2016 | Windows/Linux technician | Retail chain (anonymized)

        Certs: RHCSA (2017), RHCE (2019)
        Education: none listed beyond secondary school
        Languages: German (native), English (B2)
        Note: limited experience with public cloud.
        """, [
        R("r1", "8+ years of Linux administration", "MET",
          ["Systems administrator. 10 yrs Linux (Debian, CentOS, RHEL) and VMware vSphere."], ["experience_years"],
          "experience", ["Linux"], 8),
        R("r2", "Red Hat Certified Engineer (RHCE)", "MET", ["Certs: RHCSA (2017), RHCE (2019)"], ["certification"],
          "certification", ["RHCE"]),
        R("r3", "Configuration management with Ansible", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["Ansible"]),
        R("r4", "Public cloud administration (AWS or Azure)", "UNC", ["Note: limited experience with public cloud."],
          ["exact"], terms=["AWS", "Azure"]),
        R("r5", "Shell scripting", "MET", ["Scripting in Bash and Perl."], ["equivalence"], terms=["shell scripting"]),
        R("r6", "Virtualisation (VMware or KVM)", "MET",
          ["Run ~400 Linux VMs on VMware vSphere; Puppet for configuration management."], ["exact"],
          terms=["VMware", "KVM"]),
        R("r7", "Bachelor's degree in IT", "CONTRA", ["Education: none listed beyond secondary school"],
          ["education", "negation"], "education", kind="nice"),
        R("r8", "Monitoring with Prometheus", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["Prometheus"], kind="nice"),
    ]),
    C("test-008", "Data Scientist", """
        T08 — Data Scientist

        I'm a data scientist with a background in physics. After my PhD in Astrophysics (2020) I joined an e-commerce company where I have built recommendation and pricing models for the past five years. My daily tools are Python (pandas, NumPy, scikit-learn, XGBoost), SQL on BigQuery and Looker for reporting. I designed and analysed more than 60 A/B tests and I regularly present results to product leadership.

        I have used R mainly during my PhD. I have occasionally touched deep learning (a small PyTorch prototype), but it has not been the focus of my work.

        Languages: English (fluent), Greek (native).
        """, [
        R("r1", "PhD in a quantitative field", "MET", ["PhD in Astrophysics (2020)"], ["education"], "education"),
        R("r2", "4+ years building ML models in production", "MET",
          ["I joined an e-commerce company where I have built recommendation and pricing models for the past five years."],
          ["experience_years"], "experience", ["machine learning"], 4),
        R("r3", "Experimentation and A/B testing", "MET",
          ["I designed and analysed more than 60 A/B tests and I regularly present results to product leadership."],
          ["exact"], terms=["A/B testing"]),
        R("r4", "Deep learning in production (PyTorch or TensorFlow)", "CONTRA",
          ["I have occasionally touched deep learning (a small PyTorch prototype), but it has not been the focus of my work."],
          ["negation"], terms=["deep learning"]),
        R("r5", "Google BigQuery", "MET", ["SQL on BigQuery and Looker for reporting"], ["exact"], terms=["BigQuery"]),
        R("r6", "Snowflake data warehouse", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["Snowflake"], kind="nice"),
        R("r7", "Statistical programming in R, 3+ years", "UNC", ["I have used R mainly during my PhD."],
          ["ambiguous_duration"], "experience", ["R"], 3),
        R("r8", "Greek speaker", "MET", ["Languages: English (fluent), Greek (native)."], ["language"], "language",
          ["Greek"], kind="nice"),
    ]),
    C("test-009", "AWS Platform Engineer", """
        T09  Platform Engineer

        Skills matrix
        | Area | Tools | Years |
        | Cloud | AWS (EC2, ECS, Lambda, IAM, VPC) | 5 |
        | IaC | Terraform, CloudFormation | 4 |
        | CI/CD | GitHub Actions, CircleCI | 3 |
        | Containers | Docker, Amazon ECS | 4 |
        | Languages | Python, TypeScript | 5 |

        Experience
        2021 – present  Platform Engineer, Ad-tech company (anonymized): built internal developer platform on AWS; golden-path templates; cost dashboards.
        2019 – 2021  Backend Developer, same company.

        Certifications: AWS Certified Solutions Architect – Associate (2022), AWS Certified DevOps Engineer – Professional (2024)
        No Kubernetes in production (we use ECS); EKS only in a training lab.
        Education: BSc Applied Computer Science
        """, [
        R("r1", "5+ years of AWS", "MET", ["| Area | Tools | Years |", "| Cloud | AWS (EC2, ECS, Lambda, IAM, VPC) | 5 |"],
          ["experience_years"], "experience", ["AWS"], 5),
        R("r2", "Kubernetes in production (EKS)", "CONTRA",
          ["No Kubernetes in production (we use ECS); EKS only in a training lab."], ["negation"],
          terms=["Kubernetes", "EKS"]),
        R("r3", "Terraform", "MET", ["| IaC | Terraform, CloudFormation | 4 |"], ["exact"], terms=["Terraform"]),
        R("r4", "AWS Solutions Architect certification", "MET",
          ["AWS Certified Solutions Architect – Associate (2022)"], ["certification"], "certification",
          ["AWS Certified Solutions Architect"]),
        R("r5", "Google Cloud experience", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["Google Cloud"], kind="nice"),
        R("r6", "CI/CD with Jenkins", "MISS", [], ["related_not_equivalent", "not_documented"], terms=["Jenkins"]),
        R("r7", "Cloud cost optimisation (FinOps)", "UNC", ["cost dashboards"], ["related_not_equivalent"],
          terms=["FinOps", "cost optimisation"], kind="nice"),
        R("r8", "Building an internal developer platform", "MET",
          ["built internal developer platform on AWS; golden-path templates"], ["exact"],
          terms=["internal developer platform"]),
    ]),
    C("test-010", "Service Desk Team Lead", """
        T10 — Service Desk Team Lead

        Career
        Team Lead, Service Desk — Insurance group (anonymized) — 2023 – present
          Leading 8 analysts across two shifts; KPI reporting (first-contact resolution, SLA compliance).
          Owner of the incident and problem management process in Jira Service Management.
        Service Desk Analyst — same employer — 2020 – 2023
          Windows 10/11 support, Microsoft 365, Citrix, printers.

        Qualifications
        ITIL v3 Foundation (2019)
        HDI Support Center Team Lead (2023)
        Diploma in IT Systems Support (2019)

        Languages: English (native), Irish (basic), Polish (fluent)
        """, [
        R("r1", "2+ years of people management in IT support", "MET",
          ["Team Lead, Service Desk — Insurance group (anonymized) — 2023 – present",
           "Leading 8 analysts across two shifts; KPI reporting (first-contact resolution, SLA compliance)."],
          ["experience_years"], "experience", ["people management"], 2),
        R("r2", "ITIL 4 Foundation", "UNC", ["ITIL v3 Foundation (2019)"], ["certification", "related_not_equivalent"],
          "certification", ["ITIL 4"]),
        R("r3", "Problem management", "MET",
          ["Owner of the incident and problem management process in Jira Service Management."], ["exact"],
          terms=["problem management"]),
        R("r4", "macOS support", "MISS", [], ["not_documented"], terms=["macOS"]),
        R("r5", "ServiceNow administration", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["ServiceNow"]),
        R("r6", "Fluent Polish", "MET", ["Languages: English (native), Irish (basic), Polish (fluent)"], ["language"],
          "language", ["Polish"]),
        R("r7", "Bachelor's degree", "CONTRA", ["Diploma in IT Systems Support (2019)"], ["education"], "education",
          kind="nice"),
        R("r8", "Entry-level support role; 10+ years as a team lead required", "UNC", [],
          ["contradictory_requirement"], "experience", ["team lead"], 10),
    ]),
    C("test-011", "Penetration Tester", """
        T11 Offensive Security Consultant
        Pentester, 6 years. OSCP since 2021.
        - 2020-present: Security Consultant @ boutique firm (anonymized). Web application and internal network penetration tests for banks; Burp Suite Pro, Metasploit, BloodHound; report writing for C-level.
        - 2018-2020: Junior Security Analyst @ MSSP (anonymized). Vulnerability scanning (Qualys), patch tracking.
        Certifications: OSCP (2021), CRTO (2023), eWPT
        Programming: Python, Bash, some C#
        Cloud: AWS security reviews (2 engagements)
        Education: BSc Computer Science (2018)
        Clearance: none
        """, [
        R("r1", "5+ years of penetration testing", "MET", ["Pentester, 6 years."], ["experience_years", "equivalence"],
          "experience", ["penetration testing"], 5),
        R("r2", "OSCP", "MET", ["Certifications: OSCP (2021), CRTO (2023), eWPT"], ["certification"], "certification",
          ["OSCP"]),
        R("r3", "Web application security testing", "MET",
          ["Web application and internal network penetration tests for banks"], ["equivalence"],
          terms=["web application security"]),
        R("r4", "Active Directory attack techniques", "UNC",
          ["Web application and internal network penetration tests for banks; Burp Suite Pro, Metasploit, BloodHound;"],
          ["related_not_equivalent"], terms=["Active Directory"]),
        R("r5", "National security clearance", "CONTRA", ["Clearance: none"], ["negation"], "other",
          ["security clearance"], kind="nice"),
        R("r6", "Cloud penetration testing in Azure", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["Azure"], kind="nice"),
        R("r7", "Exploit development in C/C++", "MISS", [], ["related_not_equivalent", "not_documented"],
          terms=["C++", "exploit development"], kind="nice"),
        R("r8", "Report writing for executive audiences", "MET", ["report writing for C-level"], ["exact"],
          terms=["report writing"]),
    ]),
    C("test-012", "iOS Developer", """
        T12 iOS ENGINEER
        - 4+ yrs Swift; SwiftUI since 2022
        - Shipped a banking app (1M users) and a fitness tracker; App Store releases every two weeks
        - Objective-C: maintained legacy modules
        - Combine, Core Data, XCTest, Fastlane, Bitrise CI
        - Android: none
        - Education: BSc Information Technology (2019)
        - English B2 · Japanese N2 · Vietnamese native
        """, [
        R("r1", "5+ years of Swift", "UNC", ["4+ yrs Swift"], ["ambiguous_duration", "experience_years"],
          "experience", ["Swift"], 5),
        R("r2", "SwiftUI", "MET", ["SwiftUI since 2022"], ["exact"], terms=["SwiftUI"]),
        R("r3", "Junior iOS role: minimum 8 years of SwiftUI experience", "UNC", [], ["contradictory_requirement"],
          "experience", ["SwiftUI"], 8),
        R("r4", "Android development experience", "CONTRA", ["Android: none"], ["negation"], terms=["Android"],
          kind="nice"),
        R("r5", "Mobile CI/CD with Fastlane", "MET", ["Combine, Core Data, XCTest, Fastlane, Bitrise CI"], ["exact"],
          terms=["Fastlane"]),
        R("r6", "Japanese at JLPT N2 or higher", "MET", ["English B2 · Japanese N2 · Vietnamese native"], ["language"],
          "language", ["Japanese"]),
        R("r7", "English at C1 level", "CONTRA", ["English B2 · Japanese N2 · Vietnamese native"], ["language"],
          "language", ["English"]),
        R("r8", "Published apps with a large user base", "MET",
          ["Shipped a banking app (1M users) and a fitness tracker; App Store releases every two weeks"],
          ["equivalence"], terms=["App Store"]),
    ]),
    C("test-013", "Product Owner", """
        Candidate T13
        Product Owner — e-learning platform (anonymized), since 2021
        Before: UX researcher (2017–2021).
        I own the backlog for two Scrum teams, write user stories with acceptance criteria and run sprint reviews with stakeholders.
        I hold the PSPO I certificate.
        Analytics: Mixpanel, Google Analytics 4, basic SQL.
        I do not have a technical degree; my MA is in Psychology (2016).
        Languages: English (C1), Swedish (native), Norwegian (understanding only)
        """, [
        R("r1", "3+ years of product ownership in Scrum teams", "MET",
          ["Product Owner — e-learning platform (anonymized), since 2021",
           "I own the backlog for two Scrum teams, write user stories with acceptance criteria and run sprint reviews with stakeholders."],
          ["experience_years"], "experience", ["product owner", "Scrum"], 3),
        R("r2", "Professional Scrum Product Owner certification", "MET", ["I hold the PSPO I certificate."],
          ["certification", "equivalence"], "certification", ["Professional Scrum Product Owner"]),
        R("r3", "Technical degree (computer science or engineering)", "CONTRA",
          ["I do not have a technical degree; my MA is in Psychology (2016)."], ["education", "negation"], "education"),
        R("r4", "Advanced SQL", "UNC", ["Analytics: Mixpanel, Google Analytics 4, basic SQL."], ["exact"],
          terms=["SQL"], kind="nice"),
        R("r5", "UX research methods", "MET", ["Before: UX researcher (2017–2021)."], ["exact"],
          terms=["UX research"], kind="nice"),
        R("r6", "Fluent Norwegian", "CONTRA",
          ["Languages: English (C1), Swedish (native), Norwegian (understanding only)"], ["language"], "language",
          ["Norwegian"]),
        R("r7", "SAFe certification", "MISS", [], ["certification", "not_documented"], "certification", ["SAFe"],
          kind="nice"),
        R("r8", "Product analytics with Amplitude", "UNC", ["Analytics: Mixpanel, Google Analytics 4, basic SQL."],
          ["related_not_equivalent"], terms=["Amplitude"]),
    ]),
    C("test-014", "Computer Vision Engineer", """
        T14 — Computer Vision Engineer

        Summary: computer-vision engineer (3 years) working on defect detection for manufacturing lines.

        Experience
        Computer Vision Engineer, Factory automation vendor (anonymized), Jan 2023 – present
          - Trained YOLO and U-Net models in PyTorch; deployed with ONNX Runtime and TensorRT on NVIDIA Jetson.
          - Labelled data pipelines in CVAT; dataset versioning with DVC.
        Research Assistant, Robotics lab (university), Oct 2021 – Dec 2022
          - Camera calibration and stereo depth with OpenCV (C++).

        Skills: PyTorch, OpenCV, ONNX, TensorRT, CUDA (basic), Docker, Python, C++
        Education: MSc Robotics (2022)
        Languages: English (C1), Turkish (native)
        """, [
        R("r1", "Computer vision, 5+ years", "CONTRA",
          ["Summary: computer-vision engineer (3 years) working on defect detection for manufacturing lines.",
           "Research Assistant, Robotics lab (university), Oct 2021 – Dec 2022"],
          ["experience_years"], "experience", ["computer vision"], 5),
        R("r2", "Image segmentation models", "MET",
          ["Trained YOLO and U-Net models in PyTorch; deployed with ONNX Runtime and TensorRT on NVIDIA Jetson."],
          ["equivalence"], terms=["image segmentation"]),
        R("r3", "Edge deployment with TensorRT on Jetson", "MET",
          ["Trained YOLO and U-Net models in PyTorch; deployed with ONNX Runtime and TensorRT on NVIDIA Jetson."],
          ["exact"], terms=["TensorRT", "Jetson"]),
        R("r4", "Natural language processing", "MISS", [], ["not_documented"], terms=["natural language processing"],
          kind="nice"),
        R("r5", "Data version control", "MET", ["dataset versioning with DVC"], ["equivalence"], terms=["DVC"]),
        R("r6", "Advanced CUDA kernel programming", "UNC",
          ["Skills: PyTorch, OpenCV, ONNX, TensorRT, CUDA (basic), Docker, Python, C++"], ["exact"], terms=["CUDA"],
          kind="nice"),
        R("r7", "Master's degree in robotics, computer science or related", "MET", ["Education: MSc Robotics (2022)"],
          ["education"], "education"),
        R("r8", "Cloud training infrastructure (AWS SageMaker)", "MISS", [], ["not_documented"],
          terms=["SageMaker"], kind="nice"),
    ]),
]


def to_record(case, split):
    n = case["case_id"].split("-")[1]
    reqs, gold = [], {}
    for r in case["reqs"]:
        decision, basis = LABELS[r["label"]]
        reqs.append(r["req"])
        gold[r["req"]["req_id"]] = {"decision": decision, "basis": basis, "evidence": r["evidence"], "tags": r["tags"]}
    return {"case_id": case["case_id"], "split": split, "source": "handwritten",
            "cv": {"cv_id": f"cv-{split}-{n}", "text": case["cv"]},
            "job": {"job_id": f"job-{split}-{n}", "title": case["title"], "requirements": reqs}, "gold": gold}


def main():
    out = Path(__file__).parent / "data"
    out.mkdir(exist_ok=True)
    for split, cases in (("val", VAL), ("test", TEST)):
        with open(out / f"{split}.jsonl", "w", encoding="utf-8") as f:
            for c in cases:
                f.write(json.dumps(to_record(c, split), ensure_ascii=False) + "\n")
        print(f"{split}: {len(cases)} cases, {sum(len(c['reqs']) for c in cases)} requirements")


if __name__ == "__main__":
    main()
