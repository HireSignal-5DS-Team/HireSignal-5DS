import pytest

from agents.reader import ReaderError, read_cv, split_sections
from agents.reader.cleaning import clean_text
from agents.reader.sections import detect_heading


# ------------------------------------------------------------ text PDF ---

def test_text_pdf_uses_text_route(text_pdf):
    r = read_cv(text_pdf, "cv.pdf")
    assert r.file_type == "pdf"
    assert r.page_routes == ["text"]
    assert r.ocr_confidence is None
    assert not r.needs_human_review


def test_text_pdf_sections(text_pdf):
    r = read_cv(text_pdf, "cv.pdf")
    assert {"header", "experience", "education", "skills", "languages"} <= set(r.sections)
    assert "sami.trabelsi@example.com" in r.sections["header"]
    assert "PyTorch" in r.sections["skills"]


def test_right_aligned_dates_stay_with_their_job(text_pdf):
    """'Data Engineer ...... 2022 - 2024' must not be mistaken for two columns."""
    r = read_cv(text_pdf, "cv.pdf")
    assert r.layout == "single_column"
    assert "2022 - 2024" in r.sections["experience"]


# ------------------------------------------------------- two-column PDF ---

def test_two_column_layout_detected(two_column_pdf):
    r = read_cv(two_column_pdf, "cv2.pdf")
    assert r.layout == "two_column"


def test_two_column_does_not_mix_columns(two_column_pdf):
    r = read_cv(two_column_pdf, "cv2.pdf")
    assert "Kubernetes" in r.sections["skills"]
    assert "Talan" not in r.sections["skills"]        # main column must not leak in
    assert "Talan Tunisie" in r.sections["experience"]
    assert "Python" not in r.sections["experience"]   # sidebar must not leak in
    assert "INSAT" in r.sections["education"]
    assert "ines.bs@example.com" in r.sections["contact"]  # not hidden in "languages"


# ---------------------------------------------------------------- DOCX ---

def test_docx_header_table_and_french_headings(word_docx):
    r = read_cv(word_docx, "cv.docx")
    assert r.file_type == "docx"
    assert "youssef.h@example.com" in r.sections["header"]
    assert "AWS, GCP" in r.sections["skills"]        # table cells kept
    assert "Ooredoo" in r.sections["experience"]
    assert "ENIT" in r.sections["education"]


# ----------------------------------------------------------- OCR routes ---

def test_photo_is_read_with_ocr(photo_png):
    r = read_cv(photo_png, "photo.png")
    assert r.file_type == "image"
    assert r.page_routes == ["ocr"]
    assert r.ocr_confidence is not None and r.ocr_confidence > 70
    assert "Python" in r.text
    assert "experience" in r.sections


def test_ocr_keeps_right_aligned_dates_with_their_job(photo_png):
    """Tesseract splits 'Title ...... 2022 - 2024' into two lines; we glue them back."""
    r = read_cv(photo_png, "photo.png")
    assert r.layout == "single_column"
    assert "2022 - 2024" in r.sections["experience"]
    assert "2019 - 2024" in r.sections["education"]
    assert "2022" not in r.sections["languages"]


def test_ocr_two_column_photo(two_column_photo):
    r = read_cv(two_column_photo, "cv2.png")
    assert r.layout == "two_column"
    assert "Kubernetes" in r.sections["skills"]
    assert "Talan" in r.sections["experience"]
    assert "Talan" not in r.sections["skills"]


def test_scanned_pdf_falls_back_to_ocr(scanned_pdf):
    r = read_cv(scanned_pdf, "scan.pdf")
    assert r.file_type == "pdf"
    assert r.page_routes == ["ocr"]
    assert "Vermeg" in r.text
    assert any("OCR" in w for w in r.warnings)


def test_type_detected_from_content_not_extension(text_pdf):
    r = read_cv(text_pdf, "wrongly_named.jpg")
    assert r.file_type == "pdf"


# --------------------------------------------------------------- errors ---

@pytest.mark.parametrize("data", [b"", b"just some random bytes", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest"])
def test_bad_files_raise_reader_error(data):
    with pytest.raises(ReaderError):
        read_cv(data, "bad.bin")


# ------------------------------------------------------- unit helpers ---

@pytest.mark.parametrize("line,expected", [
    ("EXPERIENCE", "experience"),
    ("Expérience Professionnelle :", "experience"),
    ("— Compétences —", "skills"),
    ("Centres d'intérêt", "interests"),
    ("FORMATION", "education"),
    ("Coordonnées", "contact"),
    ("I have experience with Python and SQL", None),   # sentence, not a heading
    ("Python", None),
])
def test_detect_heading(line, expected):
    assert detect_heading(line) == expected


def test_split_sections_merges_repeated_headings():
    text = "Name\nSKILLS\nPython\nEXPERIENCE\nJob A\nSkills\nDocker"
    s = split_sections(text)
    assert s["skills"] == "Python\nDocker"
    assert s["header"] == "Name"


def test_clean_text_fixes_ligatures_and_hyphens():
    assert clean_text("eﬃcient develop-\nment\n\n\n\nnext") == "efficient development\n\nnext"


# ------------------------------------------------- inline headings ---

def test_inline_heading_starts_a_section():
    """Real CV (cv02): 'Technical skills: ...' was swallowed by education."""
    text = ("Youssef Trabelsi - Backend Software Engineer\n"
            "EDUCATION\n"
            "Software Engineering degree, INSAT, 2019\n"
            "\n"
            "Technical skills: Java, Spring Boot, PostgreSQL\n"
            "Languages: Arabic, French, English")
    s = split_sections(text)
    assert s["education"] == "Software Engineering degree, INSAT, 2019"
    assert s["skills"] == "Java, Spring Boot, PostgreSQL"
    assert s["languages"] == "Arabic, French, English"


def test_tools_line_inside_a_job_does_not_switch_section():
    text = ("EXPERIENCE\n"
            "Backend Developer at Telnet, 2024 to present\n"
            "Tools: Docker, Git\n"
            "Junior Developer at Vermeg, 2021 to 2023")
    s = split_sections(text)
    assert "skills" not in s
    assert "Vermeg" in s["experience"] and "Docker" in s["experience"]


@pytest.mark.parametrize("line", [
    "Experience with Python and SQL",            # no colon: a sentence
    "Email: someone@example.com",                # not a section label
    "Note: available from January",
])
def test_lines_that_are_not_inline_headings(line):
    from agents.reader.sections import detect_inline_heading
    assert detect_inline_heading(line) is None
