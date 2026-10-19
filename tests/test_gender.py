"""Decision 17: gendered pronouns, honorifics and role words are neutralised; words that contain them are not."""
import pytest

from services.profile import anonymise_cv
from services.profile.gender import neutralise_gender


@pytest.mark.parametrize("text,want", [
    ("She led the team.", "[PRONOUN] led the team."),
    ("he wrote his tests", "[PRONOUN] wrote [PRONOUN] tests"),
    ("I helped her and him; the code is hers.", "I helped [PRONOUN] and [PRONOUN]; the code is [PRONOUN]."),
    ("HE / SHE", "[PRONOUN] / [PRONOUN]"),
    ("(herself)", "([PRONOUN])"),
    ("Elle a travaillé. Il dirige.", "[PRONOUN] a travaillé. [PRONOUN] dirige."),
    ("Mr Data Engineer, Mrs. X, Ms Y, Mme Z", "[PERSONAL] Data Engineer, [PERSONAL] X, [PERSONAL] Y, [PERSONAL] Z"),
    ("Ingénieure DevOps", "Ingénieur·e DevOps"),
    ("Ingénieur DevOps", "Ingénieur·e DevOps"),
    ("ingenieure logiciel", "ingénieur·e logiciel"),
    ("INGÉNIEURE", "INGÉNIEUR·E"),
    ("Développeuse Python, directrice technique", "Développeur·se Python, directeur·rice technique"),
    ("Former chairwoman and salesman", "Former chairperson and salesperson"),
])
def test_gendered_words_are_neutralised(text, want):
    assert neutralise_gender(text)[0] == want


@pytest.mark.parametrize("text", [
    "the theory where hero chemistry", "this history here there", "shell Hermes heroic Sherlock",
    "HER2 his_id he2", "MS SQL Server and MS Office", "Consultant at Accenture, assistant manager",
    "Employee of the month", "data steward", "Missing values", "ingénieurs (plural)", "Ilford, Ellen",
])
def test_words_that_contain_them_are_not_touched(text):
    assert neutralise_gender(text) == (text, {})


def test_counts_and_anonymise_integration():
    out = anonymise_cv("Sara Ben Ali\nsara@example.com\n\nEXPERIENCE\nIngénieure DevOps. She automated CI with Jenkins.",
                       cv_id="cv-0000abcd")
    assert "Ingénieur·e DevOps. [PRONOUN] automated CI with Jenkins." in out.text
    assert out.report.placeholders["[PRONOUN]"] == 1 and out.report.placeholders["neutral role words"] == 1
    assert "Sara" not in out.text and "She" not in out.text
