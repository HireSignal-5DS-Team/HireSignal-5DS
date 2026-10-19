"""T06 anonymiser fix: no header-name search in a CV without section headings; tech/CV words are never a name."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from eval_anonymiser import readable  # noqa: E402
from services.profile import anonymise_cv  # noqa: E402

NO_HEADINGS = """Position: Junior Data Engineer
Experience years: 2

BI Tools: Experienced in working with PowerBI and Power BI dashboards.
ETL Tools: Azure Data Factory and SSIS."""


def test_tech_words_in_a_cv_without_headings_are_not_a_name():
    out = anonymise_cv(NO_HEADINGS, cv_id="cv-00000000")
    assert out.identity.name is None and "[NAME]" not in out.text
    assert "Power BI dashboards" in out.text and "ETL Tools" in out.text


@pytest.mark.parametrize("header", ["Spark Streaming", "AWS Certified", "Used SQL Server Management Studio", "Talend ETL"])
def test_common_tech_words_are_not_a_name_even_with_headings(header):
    out = anonymise_cv(f"{header}\n\nEXPERIENCE\nData Engineer at Vermeg, 2021 - 2024.", cv_id="cv-00000000")
    assert out.identity.name is None and header in out.text


def test_a_real_header_name_is_still_found_when_the_cv_has_headings():
    out = anonymise_cv("Sara Ben Ali\nsara.benali@example.com\n\nEXPERIENCE\nData Engineer at Vermeg.", cv_id="cv-00000000")
    assert out.identity.name == "Sara Ben Ali" and "Sara" not in out.text


def test_without_headings_the_name_is_still_found_through_the_email():
    out = anonymise_cv("Sarah Connolly, data engineer, sarah.connolly@example.com\nBuilt ETL pipelines in Airflow.",
                       cv_id="cv-00000000")
    assert out.identity.name == "Sarah Connolly" and "Connolly" not in out.text


@pytest.mark.parametrize("gold_file", sorted((ROOT / "tests/fixtures/profile/gold").glob("*.json")), ids=lambda p: p.stem)
def test_no_identity_leak_on_the_synthetic_gold_cvs(gold_file):
    gold = json.loads(gold_file.read_text(encoding="utf-8"))
    anon = anonymise_cv((ROOT / "tests/fixtures/profile/cvs" / f"{gold['cv']}.txt").read_text(encoding="utf-8"),
                        cv_id="cv-00000000").text
    assert [h for h in gold["must_hide"] + gold["other_people"] if readable(anon, h["kind"], h["value"])] == []


# ------------------------------------------------- T11b: skill / project phrases are not the name ---

_HEADED = "Position: Data Analyst\nExperience years: 5\n{line}\nI build dashboards.\n\nSkills\nSQL, Python"


@pytest.mark.parametrize("line,phrase", [
    ("- BI tools: Cognos, SAP business objects, Qlik Sense, Power BI", "Qlik Sense"),                    # skill in a list
    ("- ML solutions: Classification / Regression / Recommendation System / MAB", "Recommendation System"),  # technique
    ("kaggle competitions: Cassava Leaf Disease Classification - top 11%; MoA Prediction", "Cassava Leaf Disease"),  # project
    ("- Kaggle Notebooks Master", "Kaggle Notebooks"),                                                    # achievement
])
def test_skill_or_project_phrases_in_lists_are_not_taken_as_the_name(line, phrase):
    out = anonymise_cv(_HEADED.format(line=line), cv_id="cv-00000000")
    assert out.identity.name is None and phrase in out.text and "[NAME]" not in out.text  # the skill is kept


def test_real_header_name_still_masked_on_a_cv_with_headings_and_lists():
    text = "Omar Haddad\nPosition: Data Analyst\n- BI tools: Cognos, Qlik Sense, Power BI\n\nSkills\nSQL, Python"
    out = anonymise_cv(text, cv_id="cv-00000000")
    assert out.identity.name == "Omar Haddad" and "Haddad" not in out.text and "Qlik Sense" in out.text


def test_first_segment_name_of_a_list_line_is_still_found():
    out = anonymise_cv("Sara Ben Ali, Data Engineer, Tunis\n\nEXPERIENCE\nData Engineer at Vermeg.", cv_id="cv-00000000")
    assert out.identity.name == "Sara Ben Ali" and "Sara" not in out.text
