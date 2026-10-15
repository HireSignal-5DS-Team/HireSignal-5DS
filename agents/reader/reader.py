"""Reader (step 1 of HireSignal): turn any CV file into clean text + sections.

No AI model here, only tools:
    - text PDF       -> PyMuPDF (keeps reading order, handles two-column CVs)
    - scanned PDF    -> PyMuPDF renders each page, Tesseract OCR reads it
    - Word (.docx)   -> python-docx (body, tables, headers, text boxes)
    - photo / scan   -> Pillow cleans the image, Tesseract OCR reads it

Usage:
    from agents.reader import read_cv
    result = read_cv("cv.pdf")
    print(result.text, result.sections, result.warnings)
"""

from __future__ import annotations

import io
import os
import shutil
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import docx
import pymupdf
import pytesseract
from PIL import Image, ImageOps

from .cleaning import clean_text
from .sections import split_sections

# ---------------------------------------------------------------- settings ---

MIN_CHARS_TEXT_PAGE = 50     # fewer characters than this on a PDF page -> treat as a scan
OCR_DPI = 300                # resolution used to render scanned PDF pages
MIN_IMAGE_WIDTH = 1500       # small photos are upscaled before OCR
LOW_OCR_CONFIDENCE = 60      # below this (0-100), a person should check the text
MIN_CV_CHARS = 200           # a real CV has at least this much text

_WINDOWS_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


class ReaderError(Exception):
    """The file cannot be read (unsupported, corrupt, password-protected...)."""


@dataclass
class ReaderResult:
    file_name: str
    file_type: str                      # "pdf" | "docx" | "image"
    text: str                           # full clean text
    sections: dict[str, str]            # {"header": ..., "experience": ..., ...}
    pages: int
    page_routes: list[str]              # per page: "text" or "ocr"
    layout: str                         # "single_column" | "two_column" | "unknown"
    ocr_confidence: float | None        # average Tesseract confidence 0-100, None if no OCR
    needs_human_review: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------ tesseract set-up ---

def _setup_tesseract() -> None:
    """Find tesseract.exe on Windows even if it is not on PATH."""
    custom = os.environ.get("TESSERACT_CMD")
    if custom:
        pytesseract.pytesseract.tesseract_cmd = custom
    elif not shutil.which("tesseract") and Path(_WINDOWS_TESSERACT).exists():
        pytesseract.pytesseract.tesseract_cmd = _WINDOWS_TESSERACT


_setup_tesseract()


def _ocr_languages() -> str:
    """Use English + French when both are installed, else whatever exists."""
    try:
        installed = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"
    wanted = [lang for lang in ("eng", "fra") if lang in installed]
    return "+".join(wanted) or "eng"


# ----------------------------------------------------------------- OCR core ---

def _ocr_words(image: Image.Image) -> tuple[list, list[float]]:
    """Run Tesseract and return word boxes (x0, y0, x1, y1, text, 0, 0) + confidences."""
    try:
        data = pytesseract.image_to_data(
            image, lang=_ocr_languages(), output_type=pytesseract.Output.DICT
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise ReaderError(
            "Tesseract is not installed or not found. On Windows install it from "
            "the UB Mannheim build, or set the TESSERACT_CMD environment variable."
        ) from exc

    words, confidences = [], []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        x0, y0 = data["left"][i], data["top"][i]
        words.append((x0, y0, x0 + data["width"][i], y0 + data["height"][i], text, 0, 0))
        confidences.append(conf)
    return words, confidences


def _ocr_image(image: Image.Image) -> tuple[str, float | None, str]:
    """OCR one page image. Returns (text, average confidence 0-100, layout).

    Tesseract reads across two-column CVs and mixes the columns, even
    inside one line ("PostgreSQL Migrated monolith..."). So:
      1. a first pass finds where the words are;
      2. if there is a vertical gap (two columns), we cut the image into
         banner / left / right and OCR each part separately;
      3. words on the same row are glued back together, so right-aligned
         dates stay next to their job title.
    """
    words, confidences = _ocr_words(image)
    if not words:
        return "", None, "unknown"

    cols = _find_columns(words, image.width, max_cross_ratio=0.03)
    if cols is None:
        conf = round(sum(confidences) / len(confidences), 1)
        return _blocks_to_text(_merge_rows(words)), conf, "single_column"

    # Two columns: crop each region and read it on its own.
    cut, top_y = cols["cut"], cols["column_top"]
    regions = []
    if cols["top"]:
        regions.append((0, 0, image.width, int(top_y)))
    regions.append((0, int(top_y), int(cut), image.height))
    regions.append((int(cut), int(top_y), image.width, image.height))

    parts, all_conf = [], []
    for box in regions:
        region_words, region_conf = _ocr_words(image.crop(box))
        if region_words:
            parts.append(_blocks_to_text(_merge_rows(region_words)))
            all_conf += region_conf
    conf = round(sum(all_conf) / len(all_conf), 1) if all_conf else None
    return "\n\n".join(parts), conf, "two_column"


def _merge_rows(boxes: list) -> list:
    """Group boxes whose vertical centres line up into rows, read left to right.

    Small gaps get one space (words), large gaps two spaces (e.g. a date
    pushed to the right margin).
    """
    rows: list[list] = []
    for b in sorted(boxes, key=lambda b: (b[1] + b[3]) / 2):
        centre, height = (b[1] + b[3]) / 2, b[3] - b[1]
        if rows:
            row = rows[-1]
            row_centre = sum((r[1] + r[3]) / 2 for r in row) / len(row)
            row_height = max(r[3] - r[1] for r in row)
            if abs(centre - row_centre) < 0.5 * max(height, row_height):
                row.append(b)
                continue
        rows.append([b])

    merged = []
    for row in rows:
        row.sort(key=lambda b: b[0])
        height = max(b[3] - b[1] for b in row)
        text = row[0][4]
        for prev, cur in zip(row, row[1:]):
            text += ("  " if cur[0] - prev[2] > 2 * height else " ") + cur[4]
        merged.append((min(b[0] for b in row), min(b[1] for b in row),
                       max(b[2] for b in row), max(b[3] for b in row), text, 0, 0))
    return merged


def _blocks_to_text(blocks: list) -> str:
    """Join lines, leaving a blank line where there is a big vertical gap."""
    out, previous = [], None
    for b in blocks:
        if previous is not None:
            gap, height = b[1] - previous[3], previous[3] - previous[1]
            if gap > 1.2 * height or gap < -height:  # paragraph break or column jump
                out.append("")
        out.append(b[4])
        previous = b
    return "\n".join(out)


def _prepare_photo(image: Image.Image) -> Image.Image:
    """Make phone photos and scans easier for OCR."""
    image = ImageOps.exif_transpose(image)          # respect the phone's rotation flag
    image = image.convert("L")                      # grayscale
    image = ImageOps.autocontrast(image, cutoff=1)  # stretch faded scans
    if image.width < MIN_IMAGE_WIDTH:               # small photos -> upscale
        ratio = MIN_IMAGE_WIDTH / image.width
        image = image.resize((MIN_IMAGE_WIDTH, int(image.height * ratio)), Image.LANCZOS)
    try:                                            # fix pages photographed sideways
        osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
        if osd.get("rotate") and osd.get("orientation_conf", 0) > 2:
            image = image.rotate(-osd["rotate"], expand=True)
    except Exception:
        pass  # orientation detection is optional
    return image


# -------------------------------------------------------- PDF reading order ---

def _find_columns(boxes: list, page_width: float, max_cross_ratio: float = 0.1) -> dict | None:
    """Look for a vertical gap that splits the page into two real columns.

    Works on PDF text blocks or OCR word boxes (both as (x0, y0, x1, y1, text, ..)).
    Returns None for single-column pages.
    """
    if len(boxes) < 4:
        return None
    total_chars = sum(len(b[4]) for b in boxes)
    tol = page_width * 0.005  # ~3 pt on a PDF page, ~12 px on a 300-dpi scan
    best = None
    for candidate in boxes:
        x = candidate[2]  # try each box's right edge as the column gap
        if not 0.2 * page_width <= x <= 0.8 * page_width:
            continue
        left = [b for b in boxes if b[2] <= x + tol]
        right = [b for b in boxes if b[0] >= x - tol]
        crossing = [b for b in boxes if b[0] < x - tol and b[2] > x + tol]
        if len(left) < 2 or len(right) < 2:
            continue
        if len(crossing) > max(1, int(len(boxes) * max_cross_ratio)):
            continue
        # Guard 1: both sides must hold real content (not just right-aligned dates).
        if min(sum(len(b[4]) for b in left), sum(len(b[4]) for b in right)) < 0.15 * total_chars:
            continue
        # Guard 2: in real columns, many right items have no partner on the same
        # row on the left (the main column is longer). If almost all do,
        # it's a single column of "Title ........ 2021-2023" rows.
        aligned = sum(any(abs(r[1] - l[1]) < 0.5 * (r[3] - r[1]) for l in left) for r in right)
        if aligned > 0.7 * len(right):
            continue
        score = (len(crossing), -min(len(left), len(right)))
        if best is None or score < best[0]:
            best = (score, left, right, crossing)

    if best is None:
        return None
    _, left, right, crossing = best
    column_top = min(b[1] for b in left + right)
    top = [b for b in crossing if b[3] <= column_top + tol]   # e.g. a full-width name banner
    if top:
        column_top = max(b[3] for b in top) + tol
    return {
        "left": left, "right": right, "top": top,
        "bottom": [b for b in crossing if b not in top],
        "column_top": column_top,
        "cut": (max(b[2] for b in left) + min(b[0] for b in right)) / 2,
    }


def _order_blocks(blocks: list, page_width: float) -> tuple[list, str]:
    """Put PDF text blocks in human reading order (left column, then right)."""
    text_blocks = [b for b in blocks if b[6] == 0 and b[4].strip()]
    cols = _find_columns(text_blocks, page_width)
    if cols is None:
        return sorted(text_blocks, key=lambda b: (round(b[1]), b[0])), "single_column"
    by_y = lambda bs: sorted(bs, key=lambda b: (b[1], b[0]))  # noqa: E731
    return (by_y(cols["top"]) + by_y(cols["left"]) + by_y(cols["right"])
            + by_y(cols["bottom"])), "two_column"


# ---------------------------------------------------------------- readers ---

def _read_pdf(data: bytes, warnings: list[str]) -> tuple[str, list[str], str, float | None]:
    try:
        pdf = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ReaderError(f"Corrupt or unreadable PDF: {exc}") from exc
    if pdf.needs_pass:
        raise ReaderError("The PDF is password-protected.")
    if pdf.page_count == 0:
        raise ReaderError("The PDF has no pages.")

    page_texts, routes, layouts, confidences = [], [], [], []
    for page in pdf:
        raw = page.get_text("text").strip()
        if len(raw) >= MIN_CHARS_TEXT_PAGE:
            blocks, layout = _order_blocks(page.get_text("blocks"), page.rect.width)
            page_texts.append("\n\n".join(b[4].strip() for b in blocks))
            routes.append("text")
            layouts.append(layout)
        else:
            pix = page.get_pixmap(dpi=OCR_DPI)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            text, conf, layout = _ocr_image(_prepare_photo(image))
            page_texts.append(text)
            routes.append("ocr")
            layouts.append(layout)
            if conf is not None:
                confidences.append(conf)
    pdf.close()

    if "ocr" in routes:
        warnings.append(f"{routes.count('ocr')} page(s) had no text layer and were read with OCR.")
    known = {l for l in layouts if l != "unknown"}
    layout = known.pop() if len(known) == 1 else ("unknown" if not known else "two_column")
    conf = round(sum(confidences) / len(confidences), 1) if confidences else None
    return "\n\n".join(page_texts), routes, layout, conf


def _read_docx(data: bytes, warnings: list[str]) -> str:
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ReaderError(f"Corrupt or unreadable Word file: {exc}") from exc

    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    parts: list[str] = []

    # 1. Page headers often hold the name and contact details.
    for section in document.sections:
        for p in section.header.paragraphs:
            if p.text.strip():
                parts.append(p.text)

    # 2. Body paragraphs and tables, in document order.
    for element in document.element.body.iterchildren():
        if element.tag == f"{w}p":
            parts.append("".join(t.text or "" for t in element.iter(f"{w}t")
                                 if not _inside_textbox(t)))
        elif element.tag == f"{w}tbl":
            for row in element.iter(f"{w}tr"):
                cells = ["".join(t.text or "" for t in cell.iter(f"{w}t")).strip()
                         for cell in row.iter(f"{w}tc")]
                parts.append(" | ".join(c for c in cells if c))

    # 3. Text boxes (sidebars in Word CV templates) are invisible to
    #    python-docx's normal API, so we collect them from the XML.
    mc_fallback = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
    boxes = []
    for box in document.element.body.iter(f"{w}txbxContent"):
        if any(a.tag == mc_fallback for a in box.iterancestors()):
            continue  # Word stores each box twice; skip the old-format copy
        for p in box.iter(f"{w}p"):
            boxes.append("".join(t.text or "" for t in p.iter(f"{w}t")))
    if any(b.strip() for b in boxes):
        warnings.append("Text boxes found (sidebar layout); their text was added at the end.")
        parts += [""] + boxes

    return "\n".join(parts)


def _inside_textbox(element) -> bool:
    return any(a.tag.endswith("}txbxContent") for a in element.iterancestors())


def _read_image(data: bytes, warnings: list[str]) -> tuple[str, float | None, str]:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise ReaderError(f"Unreadable image: {exc}") from exc
    warnings.append("Image file: text was read with OCR.")
    return _ocr_image(_prepare_photo(image))


# ------------------------------------------------------------ file sniffing ---

def _detect_type(data: bytes, name: str) -> str:
    """Decide the type from the file's content, not only its extension."""
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:2] == b"PK":
        try:
            if "word/document.xml" in zipfile.ZipFile(io.BytesIO(data)).namelist():
                return "docx"
        except zipfile.BadZipFile:
            pass
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise ReaderError("Old Word format (.doc). Please save it as .docx or PDF.")
    try:
        Image.open(io.BytesIO(data)).verify()
        return "image"
    except Exception:
        pass
    raise ReaderError(f"Unsupported file type: {name}. Use PDF, DOCX, JPG or PNG.")


# ------------------------------------------------------------- entry point ---

def read_cv(source: str | Path | bytes, file_name: str | None = None) -> ReaderResult:
    """Read a CV from a path or raw bytes (e.g. an upload from n8n / FastAPI)."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        data = path.read_bytes()
        file_name = file_name or path.name
    else:
        data = source
        file_name = file_name or "upload"

    if not data:
        raise ReaderError("The file is empty.")

    warnings: list[str] = []
    file_type = _detect_type(data, file_name)
    ocr_conf, layout = None, "unknown"

    if file_type == "pdf":
        raw, routes, layout, ocr_conf = _read_pdf(data, warnings)
    elif file_type == "docx":
        raw, routes = _read_docx(data, warnings), ["text"]
    else:
        raw, ocr_conf, layout = _read_image(data, warnings)
        routes = ["ocr"]

    text = clean_text(raw)
    sections = split_sections(text)

    if len(text) < MIN_CV_CHARS:
        warnings.append(f"Very little text found ({len(text)} characters).")
    if ocr_conf is not None and ocr_conf < LOW_OCR_CONFIDENCE:
        warnings.append(f"Low OCR confidence ({ocr_conf}/100): the text may contain errors.")
    if set(sections) <= {"header"}:
        warnings.append("No section headings recognised (Experience, Education, ...).")

    needs_review = len(text) < MIN_CV_CHARS or (
        ocr_conf is not None and ocr_conf < LOW_OCR_CONFIDENCE
    )

    return ReaderResult(
        file_name=file_name,
        file_type=file_type,
        text=text,
        sections=sections,
        pages=len(routes),
        page_routes=routes,
        layout=layout,
        ocr_confidence=ocr_conf,
        needs_human_review=needs_review,
        warnings=warnings,
    )
