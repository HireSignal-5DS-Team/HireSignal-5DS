# Matcher errors on the 40 real pairs (T06 baseline, real-GPU)

Every disagreement between the Matcher (after validator v1) and `gold_decision`. Gold quotes are the labelers' and may not be exact CV substrings. **Cause** is my one-line guess from reading the CV, not a measurement. Splits: dev + test (nothing was tuned).

**Cause summary (my reading, 58 errors; counted from the cause lines):**
- 26 partial / implied evidence (incl. course-only, bundled requirements, 2 borderline UNCERTAIN/MISSING calls): mostly
  gold UNCERTAIN while the model says MISSING; the LoRA almost never says UNCERTAIN (7 predicted vs 39 gold).
- 12 over-claimed MET: weak inference (4), partial evidence taken as full (4), wrong quote (2), degree read as years (1),
  "Python" in a list read as "excellent Python" (1).
- 7 soft trait (J2 r6 "research business logic"): 3 false MET on generic motivation lines, 4 others.
- 6 alias / buried-term gaps: PL/SQL, DWH, Lakehouse, ARIMA/MCMC, AWS RDS in a long list, TensorFlow at a line end.
- 3 years: MET on a min-years requirement with no years in the quote (validator v1 only flags `duration_not_in_evidence`).
- 4 other: "or other cloud providers" not applied (1), title-only gold MET (1), doubtful gold (1), quote not verbatim (1).
- No error comes from anonymiser damage after the Part 0 fix (no placeholder sits on a gold line).

## false MET (18)

- **P01 r1** (dev, must) Data Science: 4 years of experience or more
  - gold **UNCERTAIN** vs model **MET** (model decision MET, basis supported; p={'MET': 0.998304, 'MISSING': 0.001679, 'UNCERTAIN': 1.7e-05}; review: duration_not_in_evidence)
  - model quote: I have experience with cross-platform development of desktop applications for Windows and Mac OS X using C++ and Qt Framework. I also have experience in embedded development, especially for ARM STM32 MCUs. | I also successfully participated in many machine learning and classical algorithm competitio
  - CV line for gold: Over 10 years of C++/Python software development experience related with medical and GIS sphere. I have an experience with PyTorch and Keras frameworks for Deep Learning. I also familiar with various GIS frameworks and tools like GDAL, rasterio, geopandas, QGIS, GEE etc.
  - cause: years: model MET on a 4-year minimum with no data-science years in its quotes (the '10 years' line is C++/Python dev); validator only flagged duration_not_in_evidence

- **P02 r1** (test, must) Data Science: 4 years of experience or more
  - gold **MISSING** vs model **MET** (model decision MET, basis supported; p={'MET': 0.926706, 'MISSING': 0.072641, 'UNCERTAIN': 0.000653}; review: duration_not_in_evidence)
  - model quote: Master Degree in Data Science
  - CV line for gold: Position: Senior Computer Vision Engineer
  - cause: degree taken as experience: 'Master Degree in Data Science' quoted for a years requirement

- **P04 r2** (test, must) Good knowledge of probability theory and statistics
  - gold **UNCERTAIN** vs model **MET** (model decision MET, basis supported; p={'MET': 0.995939, 'MISSING': 0.003519, 'UNCERTAIN': 0.000542}; review: -)
  - model quote: Design and develop machine learning systems to create, train and deploy ML models | Establish reusable data processing pipelines to enable rapid re-training and iteration through different ML methodologies | Select appropriate datasets and data representation methods
  - CV line for gold: - Perform statistical analysis and fine-tuning using test results
  - cause: weak inference: ML pipeline duties read as probability/statistics knowledge

- **P06 r2** (test, must) Good knowledge of probability theory and statistics
  - gold **UNCERTAIN** vs model **MET** (model decision MET, basis supported; p={'MET': 0.991839, 'MISSING': 0.006873, 'UNCERTAIN': 0.001287}; review: -)
  - model quote: Strong knowledge in mathematical finance including stock prediction (LSTM + ARIMA + Monte Carlo Markov Chain), investment portfolio optimization and hedging
  - CV line for gold: Bachelor degree in Economic Cybernetics (KPI), currently studying for master's degree (same field), knowledge in quantitative finance, risk modelling, credit scoring modelling
  - cause: partial evidence taken as full: finance/Monte-Carlo modelling read as stats knowledge (gold: UNCERTAIN)

- **P07 r2** (dev, must) Good knowledge of probability theory and statistics
  - gold **MISSING** vs model **MET** (model decision MET, basis supported; p={'MET': 0.567037, 'MISSING': 0.222945, 'UNCERTAIN': 0.210018}; review: -)
  - model quote: Data analysis, reports preparation and insights generation based on the historical data | Sales forecasting of CPG products
  - CV line for gold: (gold quote not found in the anonymised CV) (none)
  - cause: weak inference: forecasting/reporting duties read as statistics knowledge

- **P13 r6** (dev, must) Willingness to research business logic
  - gold **MISSING** vs model **MET** (model decision MET, basis supported; p={'MET': 0.808997, 'MISSING': 0.069443, 'UNCERTAIN': 0.121561}; review: -)
  - model quote: Proactive and continuously growing. Always trying to deliver more and ahead of schedule. | Interpersonal skills: Active Listening, Communication, Flexibility, Helping Others, Humor, Motivation, Patience, Persuasive, Fast Learner, Knowledge Seeker, Responsive, Eager to go extra mile.
  - CV line for gold: (gold quote not found in the anonymised CV) (none)
  - cause: soft trait: generic motivation lines quoted for 'research business logic'

- **P14 r6** (test, must) Willingness to research business logic
  - gold **MISSING** vs model **MET** (model decision MET, basis supported; p={'MET': 0.658185, 'MISSING': 0.180123, 'UNCERTAIN': 0.161692}; review: -)
  - model quote: I would want to improve my skills and technology level if am employed by your organization. | To work with individual who are advance than me so I can also improve my skills along the line.
  - CV line for gold: (gold quote not found in the anonymised CV) (none)
  - cause: soft trait: wish to learn quoted for 'research business logic'

- **P16 r6** (test, must) Willingness to research business logic
  - gold **MISSING** vs model **MET** (model decision MET, basis supported; p={'MET': 0.944376, 'MISSING': 0.039727, 'UNCERTAIN': 0.015897}; review: -)
  - model quote: On my previous positions I have been mostly working as an Intern and a Junior Specialist. Want to develop myself as a Cloud Data Engineer (either with AWS or GCP) and Data Architect. Want to learn more about the Hadoop ecosystem, Stream Processing, MLOps and Cloud Native solutions for Big Data.
  - CV line for gold: (gold quote not found in the anonymised CV) (none)
  - cause: soft trait: career wishes quoted for 'research business logic'

- **P22 r5** (test, must) Practical experience with tabular data and time series
  - gold **UNCERTAIN** vs model **MET** (model decision MET, basis supported; p={'MET': 0.997234, 'MISSING': 0.002709, 'UNCERTAIN': 5.7e-05}; review: -)
  - model quote: Interpreting large amounts of data to formulate a problem statement, conclusions about dynamics, trends and opportunities for major fraud risks. | Analysis of the IT solutions market, analysis and identification of business needs, their implementation, verification of sold products for compliance wi
  - CV line for gold: Interpreting large amounts of data to formulate a problem statement, conclusions about dynamics, trends and opportunities for major fraud risks.
  - cause: partial evidence taken as full: 'large amounts of data' read as tabular + time series

- **P23 r3** (dev, must) Excellent Python coding skills
  - gold **UNCERTAIN** vs model **MET** (model decision MET, basis supported; p={'MET': 0.910765, 'MISSING': 0.040055, 'UNCERTAIN': 0.04918}; review: -)
  - model quote: R, Vba, C/C++, STL, Python
  - CV line for gold: R, Vba, C/C++, STL, Python
  - cause: strength not verified: a bare skills-list entry 'Python' quoted for 'Excellent Python' (gold: UNCERTAIN)

- **P25 r5** (dev, must) Practical experience with tabular data and time series
  - gold **UNCERTAIN** vs model **MET** (model decision MET, basis supported; p={'MET': 0.787782, 'MISSING': 0.132587, 'UNCERTAIN': 0.07963}; review: -)
  - model quote: Development of online analytical tools for auditors. Responsible for exploring opportunities to design red flags and risk indicators algorithms considering the available procurement data set and for designed red flags and risk indicators algorithms testing, ensuring their correct performance.
  - CV line for gold: Development of online analytical tools for auditors. Responsible for exploring opportunities to design red flags and risk indicators algorithms considering the available procurement data set and for designed red flags and risk indicators algorithms testing, ensuring their correct performance.
  - cause: partial evidence taken as full: procurement data set read as tabular + time series

- **P26 r4** (test, must) Proficiency with ML libraries (TensorFlow, PyTorch, LightGBM, Scikit-learn)
  - gold **MISSING** vs model **MET** (model decision MET, basis supported; p={'MET': 0.370423, 'MISSING': 0.361114, 'UNCERTAIN': 0.268463}; review: evidence_not_in_cv)
  - model quote: Generating python scripts for data cleaning and preprocessing.
  - CV line for gold: (gold quote not found in the anonymised CV) (none)
  - cause: wrong quote: a Python cleaning script quoted for ML libraries; one quote was not in the CV (dropped), the other does not name a library

- **P26 r5** (test, must) Practical experience with tabular data and time series
  - gold **UNCERTAIN** vs model **MET** (model decision MET, basis supported; p={'MET': 0.864951, 'MISSING': 0.079193, 'UNCERTAIN': 0.055856}; review: -)
  - model quote: -Data modeling of IFRS9 standards for the banking system. | -Generating python scripts for data cleaning and preprocessing. | -Development of Machine Learning models for various business domains.
  - CV line for gold: -Data modeling of IFRS9 standards for the banking system.
  - cause: partial evidence taken as full: data modelling lines read as tabular + time series

- **P27 r5** (dev, must) Practical experience with tabular data and time series
  - gold **MISSING** vs model **MET** (model decision MET, basis supported; p={'MET': 0.925386, 'MISSING': 0.059329, 'UNCERTAIN': 0.015285}; review: -)
  - model quote: Training project: creation of a neural network that classifies images of waste into organic and inorganic, using the fastai Python library. | Coursework: Analysis and prediction of the popularity of the top 50 songs according to Spotify.
  - CV line for gold: (gold quote not found in the anonymised CV) (none)
  - cause: wrong quote: an image classifier and a coursework project quoted for tabular + time series

- **P30 r7** (test, nice) Experience with data pipelines or big data
  - gold **MISSING** vs model **MET** (model decision MET, basis supported; p={'MET': 0.71554, 'MISSING': 0.2325, 'UNCERTAIN': 0.05196}; review: -)
  - model quote: Developed data scraping tool using Selenium and MITM Proxy. | Created serverless RESTful API using AWS Lambda, API Gateway, and RDS.
  - CV line for gold: (gold quote not found in the anonymised CV) (none)
  - cause: weak inference: scraping tool / serverless API read as data pipelines

- **P31 r2** (dev, must) Developing big systems with Python: 2 years of experience or more
  - gold **UNCERTAIN** vs model **MET** (model decision MET, basis supported; p={'MET': 0.953818, 'MISSING': 0.036159, 'UNCERTAIN': 0.010023}; review: duration_not_in_evidence)
  - model quote: Lead redesign and optimization of backend and deployment for two legacy projects in 3-4 member teams. | Developed a custom full-text search with complex ranking logics. | Implemented complex filter systems.
  - CV line for gold: Position: Python/Django full-stack web developer
  - cause: years: MET on a 2-year minimum, no years in the quotes; 'big systems' not shown (validator flag only)

- **P32 r3** (test, must) Asynchronous programming and developing performance-critical applications
  - gold **UNCERTAIN** vs model **MET** (model decision MET, basis supported; p={'MET': 0.992388, 'MISSING': 0.007543, 'UNCERTAIN': 6.9e-05}; review: -)
  - model quote: Project "Business Process System" | Role: Fullstack developer | Technologies: Python, Django (DRF + Graphen), PostgreSQL, Celery, Git, Linux, Docker, REST, graphQL, Channels, CI/CD (Gitlab)
  - CV line for gold: Technologies: Python, Django (DRF + Graphen), PostgreSQL, Celery, Git, Linux, Docker, REST, graphQL, Channels, CI/CD (Gitlab)
  - cause: weak inference: Celery/Channels in a tech list read as async + performance-critical

- **P34 r2** (test, must) Developing big systems with Python: 2 years of experience or more
  - gold **UNCERTAIN** vs model **MET** (model decision MET, basis supported; p={'MET': 0.968639, 'MISSING': 0.029253, 'UNCERTAIN': 0.002109}; review: duration_not_in_evidence)
  - model quote: During my work experience, I worked extensively with Amazon Web Services (AWS), utilizing the AWS SDK and programming languages such as Python and TypeScript. I built and managed serverless applications using AWS services such as Lambda, DynamoDB, StepFunctions, CloudFormation, CloudWatch, and S3.
  - CV line for gold: During my work experience, I worked extensively with Amazon Web Services (AWS), utilizing the AWS SDK and programming languages such as Python and TypeScript. I built and managed serverless applications using AWS services such as Lambda, DynamoDB, StepFunctions, CloudFormation, CloudWatch, and S3. I
  - cause: years: MET on a 2-year minimum, no years in the quote (validator flag only)

## false MISSING (10)

- **P06 r3** (test, must) Understanding of Bayesian methods, time series analysis or sensor signal processing
  - gold **MET** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.034866, 'MISSING': 0.641684, 'UNCERTAIN': 0.32345}; review: -)
  - model quote: (no quote)
  - CV line for gold: Strong knowledge in mathematical finance including stock prediction (LSTM + ARIMA + Monte Carlo Markov Chain), investment portfolio optimization and hedging
  - cause: alias/term gap: ARIMA / Monte Carlo Markov Chain not read as time series / Bayesian (ESCO knowledge did not help)

- **P11 r1** (dev, must) Knowledge of the general principles of Data Warehousing and Data Lakes
  - gold **MET** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.000648, 'MISSING': 0.926204, 'UNCERTAIN': 0.073148}; review: -)
  - model quote: (no quote)
  - CV line for gold: Position: Big Data Engineer
  - cause: title only: gold MET from 'Position: Big Data Engineer'; model wants an explicit DWH/Data Lake mention (gold arguably generous)

- **P12 r2** (test, must) Hands-on experience with SQL
  - gold **MET** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.005753, 'MISSING': 0.885787, 'UNCERTAIN': 0.108459}; review: -)
  - model quote: (no quote)
  - CV line for gold: - Oracle E-BS Developer; developed Oracle Forms, OAF, PL / SQL, Workflow, Discoverer, XML Publisher.
  - cause: alias gap: 'PL / SQL' not read as SQL

- **P13 r1** (dev, must) Knowledge of the general principles of Data Warehousing and Data Lakes
  - gold **MET** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.312213, 'MISSING': 0.498528, 'UNCERTAIN': 0.189259}; review: -)
  - model quote: (no quote)
  - CV line for gold: Interested only in DWBI/DWH/ETL projects as a Team/Tech Lead or Data Delivery Manager. No preferences for team size. Cloud stack is mandatory (Azure preferred).
  - cause: alias gap: 'DWBI/DWH/ETL' not read as Data Warehousing

- **P15 r1** (dev, must) Knowledge of the general principles of Data Warehousing and Data Lakes
  - gold **MET** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.014955, 'MISSING': 0.837765, 'UNCERTAIN': 0.147281}; review: -)
  - model quote: (no quote)
  - CV line for gold: Academy Accreditation - Databricks Lakehouse Fundamentals
  - cause: alias gap: 'Databricks Lakehouse Fundamentals' not read as Data Lakes

- **P15 r4** (dev, must) Experience with GCP or another cloud provider
  - gold **MET** vs model **MISSING** (model decision MISSING, basis contradicted; p={'MET': 0.000206, 'MISSING': 0.999254, 'UNCERTAIN': 0.00054}; review: -)
  - model quote: Cloud Knowledge: Azure and AWS services, holding certifications such as DP-203 Azure Data Engineer Associate and CLF-C01 AWS Certified Cloud Practitioner.
  - CV line for gold: - Cloud Knowledge: Azure and AWS services, holding certifications such as DP-203 Azure Data Engineer Associate and CLF-C01 AWS Certified Cloud Practitioner.
  - cause: 'or other cloud providers' not applied: Azure/AWS quoted but decided MISSING/contradicted (also seen in T05)

- **P20 r4** (test, must) Experience with GCP or another cloud provider
  - gold **MET** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.000124, 'MISSING': 0.994322, 'UNCERTAIN': 0.005554}; review: -)
  - model quote: (no quote)
  - CV line for gold: - Databases: Oracle 7, Oracle8i, Oracle 9i, Oracle 10g, Oracle 11g, Oracle 12c, Oracle 18c, Oracle 19c, DB2 6.x/7.x, Sybase 11.x/12.x, MS SQL 6.5/7.0, MS SQL 2000, Informix 9.x, MySQL 4.x, Postgres 9/10/11, AWS RDS, AWS Aurora Postgres;
  - cause: buried evidence: 'AWS RDS, AWS Aurora' inside a long database list

- **P21 r4** (dev, must) Proficiency with ML libraries (TensorFlow, PyTorch, LightGBM, Scikit-learn)
  - gold **MET** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.056816, 'MISSING': 0.903729, 'UNCERTAIN': 0.039455}; review: -)
  - model quote: (no quote)
  - CV line for gold: Skills: Python (Programming Language) · Research and Development (R&D) · Machine Learning · Data Science · Data Analysis · TensorFlow
  - cause: buried evidence: 'TensorFlow' at the end of a skills line

- **P23 r8** (dev, nice) Experience designing and implementing AutoML flows or frameworks
  - gold **MET** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 2.6e-05, 'MISSING': 0.999465, 'UNCERTAIN': 0.000509}; review: -)
  - model quote: (no quote)
  - CV line for gold: Data Science, a 9-course specialization by Johns Hopkins University on Coursera. Specialization Certificate earned on December 2, 2015 (Data Science Tools, R programming, Getting and cleaning data, Exploratory data analysis, Reproducible research, Statistical inference, Regression models, Machine le
  - cause: gold doubtful: a Coursera data-science course is weak evidence for AutoML (gold quote not an exact CV substring)

- **P30 r6** (test, must) Experience with microservices architecture, cloud technologies, Docker and Kubernetes
  - gold **MET** vs model **MISSING** (model decision MISSING, basis contradicted; p={'MET': 0.087726, 'MISSING': 0.567963, 'UNCERTAIN': 0.344311}; review: -)
  - model quote: Built cloud infrastructure on AWS with ECS, S3 and CloudFormation.
  - CV line for gold: (gold quote not found in the anonymised CV) AWS Certified Developer - Associate , Built cloud infrastructure on AWS with ECS, S3 and CloudFormation
  - cause: partial requirement: AWS/ECS shown, Docker/Kubernetes not; model said contradicted; gold MET looks generous (bundled requirement, see T03 draft note)

## missed UNCERTAIN (26)

- **P04 r3** (test, must) Understanding of Bayesian methods, time series analysis or sensor signal processing
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.001404, 'MISSING': 0.698635, 'UNCERTAIN': 0.299961}; review: -)
  - model quote: (no quote)
  - CV line for gold: - financial trading prediction
  - cause: partial evidence: 'financial trading prediction' (implied time series) -> model chose MISSING, gold UNCERTAIN

- **P06 r4** (test, must) Hands-on experience with probabilistic programming (Pyro, PyMC3, JAGS or similar)
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.000194, 'MISSING': 0.995812, 'UNCERTAIN': 0.003994}; review: -)
  - model quote: (no quote)
  - CV line for gold: Strong knowledge in mathematical finance including stock prediction (LSTM + ARIMA + Monte Carlo Markov Chain), investment portfolio optimization and hedging
  - cause: partial evidence: MCMC is probabilistic-programming-adjacent; model MISSING, gold UNCERTAIN

- **P07 r3** (dev, must) Understanding of Bayesian methods, time series analysis or sensor signal processing
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.000703, 'MISSING': 0.950972, 'UNCERTAIN': 0.048325}; review: -)
  - model quote: (no quote)
  - CV line for gold: - Sales forecasting of CPG products
  - cause: partial evidence: sales forecasting (implied time series); model MISSING

- **P11 r3** (dev, must) Knowledge of Python
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.005605, 'MISSING': 0.914262, 'UNCERTAIN': 0.080133}; review: -)
  - model quote: (no quote)
  - CV line for gold: T-Shaped Product Engineer having 5 years of Machine Learning, DataScience, and 12 years of Software Engineering. Took part in a variety of Data Science projects for e-commerce and advertising companies. My work covered both Engineering and Product parts. On the engineering side, I did R&Ds, prepared
  - cause: implied skill: ML/DS career without the word Python; model MISSING, gold UNCERTAIN

- **P11 r6** (dev, must) Willingness to research business logic
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.349163, 'MISSING': 0.436793, 'UNCERTAIN': 0.214045}; review: -)
  - model quote: (no quote)
  - CV line for gold: T-Shaped Product Engineer having 5 years of Machine Learning, DataScience, and 12 years of Software Engineering. Took part in a variety of Data Science projects for e-commerce and advertising companies. My work covered both Engineering and Product parts. On the engineering side, I did R&Ds, prepared
  - cause: soft trait: R&D / stakeholder work implies research of business logic; model MISSING

- **P12 r6** (test, must) Willingness to research business logic
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.009787, 'MISSING': 0.531827, 'UNCERTAIN': 0.458385}; review: -)
  - model quote: (no quote)
  - CV line for gold: - After the R12 transition was completed, developed warehouse and shop handheld terminal applications. Made improvements within the scope of Production, Sales, Purchasing, Shipping, Warehouse process improvement projects.
  - cause: soft trait: business-process improvement work; model MISSING (p UNCERTAIN 0.46)

- **P14 r1** (test, must) Knowledge of the general principles of Data Warehousing and Data Lakes
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.000414, 'MISSING': 0.857298, 'UNCERTAIN': 0.142288}; review: -)
  - model quote: (no quote)
  - CV line for gold: I used the open source ELT .
  - cause: partial evidence: 'open source ELT' only; model MISSING

- **P16 r1** (test, must) Knowledge of the general principles of Data Warehousing and Data Lakes
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.000505, 'MISSING': 0.885353, 'UNCERTAIN': 0.114141}; review: -)
  - model quote: (no quote)
  - CV line for gold: - Creating ETL Glue Jobs and AWS Lambdas for Data Processing and Automation
  - cause: partial evidence: AWS Glue ETL jobs; model MISSING

- **P17 r3** (dev, must) Knowledge of Python
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.001723, 'MISSING': 0.988392, 'UNCERTAIN': 0.009885}; review: -)
  - model quote: (no quote)
  - CV line for gold: Position: Machine Learning Engineer
  - cause: implied skill: 'Machine Learning Engineer' title, no Python; model MISSING

- **P18 r1** (test, must) Knowledge of the general principles of Data Warehousing and Data Lakes
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.002031, 'MISSING': 0.907268, 'UNCERTAIN': 0.090701}; review: -)
  - model quote: (no quote)
  - CV line for gold: 1. Data Pipeline Development: I design, develop, and maintain robust data pipelines and ETL processes to ensure accurate and timely delivery of data for various banking products and services. This involves collaborating with cross-functional teams to understand data requirements and implementing eff
  - cause: partial evidence: data pipelines/ETL; model MISSING

- **P18 r6** (test, must) Willingness to research business logic
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.034341, 'MISSING': 0.606044, 'UNCERTAIN': 0.359615}; review: -)
  - model quote: (no quote)
  - CV line for gold: 1. Data Pipeline Development: I design, develop, and maintain robust data pipelines and ETL processes to ensure accurate and timely delivery of data for various banking products and services. This involves collaborating with cross-functional teams to understand data requirements and implementing eff
  - cause: soft trait: cross-functional pipeline work; model MISSING

- **P19 r1** (dev, must) Knowledge of the general principles of Data Warehousing and Data Lakes
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.002382, 'MISSING': 0.88972, 'UNCERTAIN': 0.107899}; review: -)
  - model quote: (no quote)
  - CV line for gold: - This education plan is designed to train new specialists in the most common Big Data tools and solutions(Hadoop, Spark, Spark Streaming, Hive, Kafka, Cloud Computing, Docker, Airflow, NoSQL, ELK, etc.).
  - cause: course only: a Big Data training plan; model MISSING

- **P19 r4** (dev, must) Experience with GCP or another cloud provider
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.004082, 'MISSING': 0.902453, 'UNCERTAIN': 0.093465}; review: -)
  - model quote: (no quote)
  - CV line for gold: - This education plan is designed to train new specialists in the most common Big Data tools and solutions(Hadoop, Spark, Spark Streaming, Hive, Kafka, Cloud Computing, Docker, Airflow, NoSQL, ELK, etc.).
  - cause: course only: 'Cloud Computing' in a training plan; model MISSING

- **P21 r2** (dev, must) Proven experience with modern deep learning techniques and Gradient Boosting Trees
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.17475, 'MISSING': 0.683818, 'UNCERTAIN': 0.141432}; review: -)
  - model quote: (no quote)
  - CV line for gold: implemented Deep and Cross network via TFRS to offer a product that customers most likely to buy and increased conversion
  - cause: partial evidence: Deep & Cross network (DL), no gradient boosting; model MISSING

- **P21 r5** (dev, must) Practical experience with tabular data and time series
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.294741, 'MISSING': 0.564442, 'UNCERTAIN': 0.140818}; review: -)
  - model quote: (no quote)
  - CV line for gold: - Redeveloped product recommendation engines for seven different Banking products (ML models, RFM, and Rule-Based
  - cause: partial evidence: banking recommendation models (implied tabular); model MISSING

- **P21 r8** (dev, nice) Experience designing and implementing AutoML flows or frameworks
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 7e-05, 'MISSING': 0.99909, 'UNCERTAIN': 0.00084}; review: -)
  - model quote: (no quote)
  - CV line for gold: - Implemented a hyper-parameter optimization package using Optuna to improve the performance of the recommendation
  - cause: partial evidence: Optuna hyper-parameter tuning is AutoML-adjacent; model MISSING

- **P22 r1** (test, must) ML in production: 3 years of experience or more (training, testing, deployment, monitoring of real-time models)
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.310707, 'MISSING': 0.416188, 'UNCERTAIN': 0.273105}; review: -)
  - model quote: (no quote)
  - CV line for gold: Experience in building, implementing and testing scoring models, developing algorithms, developing methods for detecting and methods of preventive protection against fraud.
  - cause: partial evidence: scoring models without production / real-time words; model MISSING (p close: 0.42/0.31/0.27)

- **P24 r3** (test, must) Excellent Python coding skills
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.000164, 'MISSING': 0.963028, 'UNCERTAIN': 0.036808}; review: -)
  - model quote: (no quote)
  - CV line for gold: - machine learning models for fraud detection and anti-money laundering
  - cause: implied skill: ML for fraud detection, Python strength not stated; model MISSING

- **P27 r2** (dev, must) Proven experience with modern deep learning techniques and Gradient Boosting Trees
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis contradicted; p={'MET': 0.198029, 'MISSING': 0.435931, 'UNCERTAIN': 0.366041}; review: -)
  - model quote: Training project: creation of a neural network that classifies images of waste into organic and inorganic, using the fastai Python library.
  - CV line for gold: Training project: creation of a neural network that classifies images of waste into organic and inorganic, using the fastai Python library.
  - cause: partial evidence: one training-project neural net; model MISSING/contradicted

- **P27 r4** (dev, must) Proficiency with ML libraries (TensorFlow, PyTorch, LightGBM, Scikit-learn)
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis contradicted; p={'MET': 0.056514, 'MISSING': 0.527289, 'UNCERTAIN': 0.416198}; review: -)
  - model quote: Training project: creation of a neural network that classifies images of waste into organic and inorganic, using the fastai Python library.
  - CV line for gold: Training project: creation of a neural network that classifies images of waste into organic and inorganic, using the fastai Python library.
  - cause: partial evidence: fastai (built on PyTorch) only; model MISSING/contradicted

- **P29 r3** (dev, must) Excellent Python coding skills
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.009928, 'MISSING': 0.661809, 'UNCERTAIN': 0.328263}; review: -)
  - model quote: (no quote)
  - CV line for gold: Successfully finished 14 weeks of Data Science program by Data Root University. Got In-depth knowledge of various Machine Learning technics, supervised/unsupervised learning and RESTful API development on Flask.
  - cause: course only: Data Science program; model MISSING

- **P31 r3** (dev, must) Asynchronous programming and developing performance-critical applications
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.00019, 'MISSING': 0.963779, 'UNCERTAIN': 0.036031}; review: -)
  - model quote: (no quote)
  - CV line for gold: - Lead redesign and optimization of backend and deployment for two legacy projects in 3-4 member teams.
  - cause: implied: backend optimisation, no async word; model MISSING

- **P31 r6** (dev, nice) Algorithms development (collaborative filtering, similarity, data normalization, clustering)
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.013787, 'MISSING': 0.631744, 'UNCERTAIN': 0.354469}; review: -)
  - model quote: (no quote)
  - CV line for gold: - Developed a custom full-text search with complex ranking logics.
  - cause: partial evidence: full-text search ranking ~ similarity; model MISSING

- **P32 r5** (test, nice) Experience with Machine Learning
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.000116, 'MISSING': 0.996568, 'UNCERTAIN': 0.003316}; review: -)
  - model quote: (no quote)
  - CV line for gold: Project "Backend of Web service for recommendation system"
  - cause: implied: backend of a recommendation service; model MISSING

- **P38 r3** (test, must) Asynchronous programming and developing performance-critical applications
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.00092, 'MISSING': 0.977299, 'UNCERTAIN': 0.021781}; review: -)
  - model quote: (no quote)
  - CV line for gold: Python3, FastAPI, PostgreSQL, Docker, PyJWT, SQLAlchemy, Pydantic, Alembic
  - cause: implied: FastAPI (async framework) in a tech list; model MISSING

- **P38 r4** (test, nice) Working with AWS, Docker and microservices
  - gold **UNCERTAIN** vs model **MISSING** (model decision MISSING, basis not_documented; p={'MET': 0.11045, 'MISSING': 0.750284, 'UNCERTAIN': 0.139266}; review: -)
  - model quote: (no quote)
  - CV line for gold: Python3, FastAPI, PostgreSQL, Docker, PyJWT, SQLAlchemy, Pydantic, Alembic
  - cause: partial requirement: Docker yes, AWS/microservices no; model MISSING

## other (4)

- **P15 r6** (dev, must) Willingness to research business logic
  - gold **MISSING** vs model **UNCERTAIN** (model decision UNCERTAIN, basis ambiguous; p={'MET': 0.035962, 'MISSING': 0.415268, 'UNCERTAIN': 0.54877}; review: -)
  - model quote: (no quote)
  - CV line for gold: (gold quote not found in the anonymised CV) (none)
  - cause: soft trait: model UNCERTAIN, gold MISSING (borderline requirement)

- **P21 r7** (dev, nice) Experience with data pipelines or big data
  - gold **MET** vs model **UNCERTAIN** (model decision MET, basis ambiguous; p={'MET': 0.983476, 'MISSING': 0.016445, 'UNCERTAIN': 7.9e-05}; review: evidence_not_in_cv, met_without_verified_evidence)
  - model quote: (no quote)
  - CV line for gold: - Developed and constructed data pipelines to be used in the model, ensuring efficient and effective flow of data for analysis
  - cause: quote not verbatim: model said MET but its quote was not an exact CV substring, so validator rule 1 made it UNCERTAIN

- **P25 r7** (dev, nice) Experience with data pipelines or big data
  - gold **MISSING** vs model **UNCERTAIN** (model decision UNCERTAIN, basis ambiguous; p={'MET': 0.182285, 'MISSING': 0.369225, 'UNCERTAIN': 0.44849}; review: -)
  - model quote: (no quote)
  - CV line for gold: (gold quote not found in the anonymised CV) (none)
  - cause: borderline: model UNCERTAIN, gold MISSING (p close: 0.45 UNCERTAIN / 0.37 MISSING)

- **P28 r2** (test, must) Proven experience with modern deep learning techniques and Gradient Boosting Trees
  - gold **MISSING** vs model **UNCERTAIN** (model decision UNCERTAIN, basis ambiguous; p={'MET': 0.030692, 'MISSING': 0.453767, 'UNCERTAIN': 0.515541}; review: -)
  - model quote: (no quote)
  - CV line for gold: (gold quote not found in the anonymised CV) (none)
  - cause: borderline: model UNCERTAIN, gold MISSING (p close: 0.52 / 0.45)

