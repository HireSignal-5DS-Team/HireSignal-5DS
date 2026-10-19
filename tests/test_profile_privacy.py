# Adapted from team V2: tests/test_profile_privacy.py (feature/agent-integration @ a5a03ff)
"""Profile Agent, steps 1-3: find the identity, hide it, check nothing leaked."""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.profile import anonymise_cv, anonymise_reader, leak_check  # noqa: E402
from services.profile.anonymise import apply_masks, name_variants  # noqa: E402
from services.profile.detect import (Span, find_emails, find_name, find_phones, find_proxies,  # noqa: E402
                                   find_urls, fold, header_region, private_regions)
from services.profile.contracts import Identity  # noqa: E402

CV = """JOHN SMITH | Data Scientist
john.smith92@gmail.com • +216 22 345 678 • linkedin.com/in/johnsmith
Tunisian | Born on 12/03/1999 | Single

SUMMARY
Data scientist with 3 years of experience. Smith built single-page dashboards.

EXPERIENCE
Data Scientist, Vermeg 2021 - 2024
- Churn models with XGBoost. Married data from 3 sources.

REFERENCES
Dr. Leila Haddad, ESPRIT, leila.haddad@esprit.tn
"""


def texts(spans):
    return [s.text for s in spans]


# ------------------------------------------------------------- detectors ---

def test_fold_keeps_the_length():
    for s in ["Éloïse Mäkelä", "ÇA İŞ", "naïve – ok"]:
        assert len(fold(s)) == len(s)
    assert fold("Éloïse") == "eloise"


def test_emails():
    assert texts(find_emails("mail: a.b-c+cv@mail.example.tn.")) == ["a.b-c+cv@mail.example.tn"]


@pytest.mark.parametrize("text,phone", [
    ("Tel: +216 22 345 678", "+216 22 345 678"), ("Tél : 98 765 432", "98 765 432"),
    ("06 12 34 56 78", "06 12 34 56 78"), ("+33 6 12 34 56 78", "+33 6 12 34 56 78"),
    ("(555) 123-4567", "(555) 123-4567"), ("0021697123456", "0021697123456"), ("22.345.678", "22.345.678"),
])
def test_phones_found(text, phone):
    assert texts(find_phones(text)) == [phone]


@pytest.mark.parametrize("text", [
    "2019 - 2021", "(2019 – 2024)", "2021 2022 2023", "06/2020 - 09/2020", "12/03/1999", "GPA 3.8/4",
    "2000 alerts per month", "SY0-601", "1M merchants", "from 70 to 98",
])
def test_not_phones(text):
    assert find_phones(text) == []


def test_urls_but_not_technologies():
    t = "linkedin.com/in/jsmith | https://jsmith.dev/blog | www.site.tn | @dev_jsmith | GitHub: jsmith"
    assert texts(find_urls(t)) == ["linkedin.com/in/jsmith", "https://jsmith.dev/blog", "www.site.tn",
                                   "@dev_jsmith", "jsmith"]
    assert find_urls("Node.js, Vue.js, ASP.NET, Socket.io, scikit-learn, e.g. this") == []
    assert find_urls("write to john@site.com") == []          # the email is not also a URL


@pytest.mark.parametrize("text,kind,value", [
    ("Born on 12/03/1999", "DOB", "12/03/1999"), ("Née le 4 mars 1997", "DOB", "4 mars 1997"),
    ("Date of birth: March 4, 1997", "DOB", "March 4, 1997"), ("Date de naissance : 1997-03-04", "DOB", "1997-03-04"),
    ("I am 24 years old", "AGE", "24 years old"), ("âgée de 27 ans", "AGE", "âgée de 27 ans"),
    ("Age: 31", "AGE", "31"), ("Gender: Male", "GENDER", "Male"), ("Sexe : F", "GENDER", "F"),
    ("Nationality: Moroccan", "NATIONALITY", "Moroccan"), ("Nationalité : Tunisienne", "NATIONALITY", "Tunisienne"),
    ("Marital status: Married", "MARITAL", "Married"), ("Situation familiale : Célibataire", "MARITAL", "Célibataire"),
    ("Lieu de naissance : Sousse", "BIRTHPLACE", "Sousse"), ("Mme Khelifi", "HONORIFIC", "Mme"),
])
def test_bias_proxies(text, kind, value):
    found = [(s.kind, s.text) for s in find_proxies(text, [(0, 0)])]
    assert (kind, value) in found


def test_experience_years_are_not_ages():
    t = "5 years of experience, 3 ans d'expérience, a 2 years old project? no: 10 years in IT"
    assert [s for s in find_proxies(t, [(0, 0)]) if s.kind == "AGE"] == []


def test_bare_proxy_words_only_in_the_header():
    spans = find_proxies(CV, private_regions(CV))
    words = {(s.kind, s.text) for s in spans if s.source == "header"}
    assert ("NATIONALITY", "Tunisian") in words and ("MARITAL", "Single") in words
    assert not any(s.text in ("single", "Married") for s in spans)   # "single-page", "Married data" stay


def test_contact_section_at_the_end_counts_as_private():
    t = "AMINE GHARBI\nML Engineer\n\nEXPERIENCE\nInstaDeep 2022\n\nCONTACT\nParis, France\nSingle\n"
    regions = private_regions(t)
    assert len(regions) == 2
    result = anonymise_cv(t, cv_id="cv-x")
    assert "Paris" not in result.text and "Single" not in result.text and "InstaDeep 2022" in result.text


# ------------------------------------------------------------------ name ---

@pytest.mark.parametrize("header,name", [
    ("JOHN SMITH | Data Scientist\n", "JOHN SMITH"),
    ("John Smith Data Scientist\n", "John Smith"),
    ("AMINE\nGHARBI\nMachine Learning Engineer\n", None),         # one word per line: second chance below
    ("Curriculum Vitae — Omar Haddad\n", "Omar Haddad"),
    ("Mme Yasmine Khelifi\n", "Yasmine Khelifi"),
    ("Yasmine EL AMRI — Data Engineer\n", "Yasmine EL AMRI"),
    ("Mohamed Ali Ben Salah\nIngénieur\n", "Mohamed Ali Ben Salah"),
    ("Ingénieure DevOps\nInes TRABELSI\n", "Ines TRABELSI"),
])
def test_name_in_the_header(header, name):
    text = header + "\nEXPERIENCE\nSomething 2020\n"
    found = find_name(text, header_region(text), find_emails(text))
    if name is None:
        return
    assert texts(found) == [name]


def test_name_on_two_lines_is_found_through_the_email():
    t = "AMINE\nGHARBI\nML Engineer\n\nEXPERIENCE\nInstaDeep\n\nCONTACT\namine.gharbi@proton.me\n"
    result = anonymise_cv(t, cv_id="cv-x")
    assert "AMINE" not in result.text and "GHARBI" not in result.text, result.text
    assert result.report.name_found


def test_french_split_labels():
    t = "Prénom : Mohamed Ali\nNom : Ben Salah\n\nEXPÉRIENCE\nBen Salah a développé une API. Mohamed aussi.\n"
    result = anonymise_cv(t, cv_id="cv-x")
    assert result.identity.name == "Mohamed Ali Ben Salah"
    assert not re.search(r"Mohamed|Ali\b|Ben Salah|Salah", result.text), result.text


def test_name_only_in_footer_and_email():
    t = "Resume\nsarah.connolly@outlook.com\n\nSKILLS\nReact\n\nSarah Connolly - references on request\n"
    result = anonymise_cv(t, cv_id="cv-x")
    assert "Sarah" not in result.text and "Connolly" not in result.text


def test_no_name_means_human_review():
    result = anonymise_cv("SKILLS\nPython, SQL\n", cv_id="cv-x")
    assert not result.report.name_found and result.report.needs_human_review


# --------------------------------------------------------------- masking ---

def test_every_form_of_the_name_is_hidden():
    t = ("Éloïse MARTIN-DUBOIS\n\nSUMMARY\nEloise Martin-Dubois, also E. Martin-Dubois, MARTIN and martin? "
         "Dubois wrote it.\n")
    result = anonymise_cv(t, cv_id="cv-x")
    for form in ("Éloïse", "Eloise", "MARTIN", "Dubois", "E. Martin"):
        assert form not in result.text, (form, result.text)
    assert "martin?" in result.text      # a lowercase common word is not a name part


def test_name_variants_skip_particles_alone():
    variants = [v for v, _ in name_variants("Yasmine El Amri")]
    assert "Yasmine El Amri" in variants and "El Amri" in variants and "El" not in variants


def test_neighbour_placeholders_collapse():
    assert apply_masks("John Smith", [Span(0, 4, "NAME", "John", "x"), Span(5, 10, "NAME", "Smith", "x")]) == "[NAME]"


def test_overlaps_hide_the_union():
    spans = [Span(0, 10, "ADDRESS", "", "x"), Span(5, 20, "PHONE", "", "x")]
    assert apply_masks("a" * 25, spans) == "[PHONE]" + "a" * 5


def test_full_example():
    result = anonymise_cv(CV, cv_id="cv-x")
    anon = result.text
    for secret in ("JOHN", "SMITH", "Smith", "john.smith92", "345 678", "linkedin", "Tunisian", "1999", "Single",
                   "Leila", "Haddad", "leila.haddad"):
        assert secret not in anon, (secret, anon)
    for fact in ("Data Scientist, Vermeg 2021 - 2024", "XGBoost", "3 years of experience", "single-page",
                 "Married data", "ESPRIT"):
        assert fact in anon, fact
    assert result.report.leaks_left == 0 and not result.report.needs_human_review


def test_referee_contacts_are_hidden_but_not_stored():
    result = anonymise_cv(CV, cv_id="cv-x")
    assert result.identity.emails == ["john.smith92@gmail.com"]
    assert "leila" not in json.dumps(result.identity.model_dump()).lower()


# ------------------------------------------------------------ leak check ---

def test_leak_check_finds_glued_name_and_other_phone_format():
    identity = Identity(cv_id="x", name="John Smith", phones=["+216 22 345 678"])
    leaks = leak_check("see johnsmith92 portfolio, call 22345678, [NAME] ok", identity)
    assert {(s.kind, s.text) for s in leaks} == {("NAME", "johnsmith92"), ("PHONE", "22345678")}


def test_leak_check_finds_fresh_patterns():
    leaks = leak_check("write to x.y@z.com or born on 1/2/1990", Identity(cv_id="x"))
    assert {s.kind for s in leaks} == {"EMAIL", "DOB"}


def test_leak_found_after_masking_is_hidden():
    t = "Karim Benali\n\nPROJECTS\nPortfolio at karimbenali (old name)\n"
    result = anonymise_cv(t, cv_id="cv-x")
    assert "karimbenali" not in result.text and result.report.leaks_fixed >= 1 and result.report.leaks_left == 0


# --------------------------------------------------------------- outputs ---

def test_matcher_cv_has_the_team_shape_and_no_personal_value():
    reader = {"text": CV, "file_name": "John_Smith_CV.pdf", "file_type": "pdf", "sections": {"header": CV[:120]},
              "pages": 1, "page_routes": ["text"], "layout": "single_column", "ocr_confidence": None,
              "needs_human_review": False, "warnings": ["page 1 of John_Smith_CV.pdf: small font"]}
    result = anonymise_reader(reader, cv_id="cv-x")
    cv = result.to_matcher_cv(reader)
    assert set(cv) == {"cv_id", "text", "structured"} and set(cv["structured"]) == {"privacy", "reader"}
    assert "file_name" not in cv["structured"]["reader"] and "sections" not in cv["structured"]["reader"]
    dumped = json.dumps(cv, ensure_ascii=False)
    identity = result.identity
    for value in [identity.name, *identity.emails, *identity.phones, *identity.urls, "Smith", "John"]:
        assert value not in dumped, value


def test_report_has_counts_not_values():
    result = anonymise_cv(CV, cv_id="cv-x")
    dumped = result.report.model_dump_json()
    assert "Smith" not in dumped and "gmail" not in dumped
    assert result.report.placeholders["[NAME]"] >= 2


def test_random_cv_id():
    a, b = anonymise_cv(CV), anonymise_cv(CV)
    assert a.cv_id != b.cv_id and re.fullmatch(r"cv-[0-9a-f]{8}", a.cv_id)


def test_matcher_cv_validates_against_the_team_schema_shape():
    """Same fields as matcher/schemas.py CV (strict): cv_id, non-empty text, structured dict."""
    cv = anonymise_cv(CV, cv_id="cv-x").to_matcher_cv()
    assert isinstance(cv["cv_id"], str) and cv["text"] and isinstance(cv["structured"], dict)


# Not ported (T04): V2's NER tests (agents/profile/ner.py is not copied, it was off in V2) and the tests that read
# V2's eval/profile_agent/ files (privacy eval script, real resume-ner output on p06).
