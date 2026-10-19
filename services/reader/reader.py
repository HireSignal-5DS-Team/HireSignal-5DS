# Adapted from team V2: agents/reader/reader.py (feature/agent-integration @ a5a03ff)
"""Reader (step 1 of HireSignal): turn any CV file into clean text + sections.

No AI model here, only tools:
    - text PDF       -> PyMuPDF (keeps reading order, handles two-column CVs)
    - scanned PDF    -> PyMuPDF renders each page, Tesseract OCR reads it
    - Word (.docx)   -> python-docx (body, tables, headers, text boxes)
    - photo / scan   -> Pillow cleans the image, Tesseract OCR reads it

Usage:
    from services.reader import read_cv
    result = read_cv("cv.pdf")
    print(result.text, result.sections, result.warnings)
"""

from __future__ import annotations

import io
import re
import os
import shutil
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import docx
import pymupdf
import pytesseract
from PIL import Image, ImageFilter, ImageOps

import services.config  # noqa: F401  (loads .env before _setup_tesseract reads TESSERACT_CMD)

from .cleaning import clean_text
from .sections import split_sections

# ---------------------------------------------------------------- settings ---

MIN_CHARS_TEXT_PAGE = 50     # fewer characters than this on a PDF page -> treat as a scan
OCR_DPI = 300                # resolution used to render scanned PDF pages
MIN_IMAGE_WIDTH = 1500       # small photos are upscaled before OCR
LOW_OCR_CONFIDENCE = 60      # below this (0-100), a person should check the text
RETRY_OCR_CONFIDENCE = 80    # below this, also try denoised versions of the image
DENOISE_SIZES = (3, 5)       # median filter sizes tried on noisy scans
MIN_CV_CHARS = 200           # a real CV has at least this much text
MAX_UNCLEAR_SHARE = 0.05     # T10: more "[unclear]" marks than this (share of words) on a page -> review
MAX_LOW_TRUST_SHARE = 0.20   # T10: more vision-only (no OCR support) words than this, vs the page text -> review
MAX_PDF_PAGES = 10           # T13: a CV is a few pages; more is refused with a clear error (no hour-long OCR)
MAX_IMAGE_PIXELS = 40_000_000  # T13: a photo larger than ~40 MP is refused (a phone photo is 12-50 MP; OCR time)
MIN_ENGLISH_SHARE = 0.04     # T13: share of common English words; the 52 real CVs have >= 0.09, French / Russian 0.0
ENGLISH_WORDS = {"the", "and", "of", "in", "with", "for", "to", "a", "on", "experience", "years", "i", "my", "as", "is",
                 "at", "by", "skills"}

_WINDOWS_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


class ReaderError(Exception):
    """The file cannot be read (unsupported, corrupt, password-protected...)."""


@dataclass
class ReaderResult:
    # no file_name on purpose: it often holds the candidate's name ("Sami_Trabelsi_CV.pdf")
    file_type: str                      # "pdf" | "docx" | "image" | "text"
    text: str                           # full clean text
    sections: dict[str, str]            # {"header": ..., "experience": ..., ...}
    pages: int
    page_routes: list[str]              # per page: "text" or "ocr"
    layout: str                         # "single_column" | "two_column" | "unknown"
    ocr_confidence: float | None        # average Tesseract confidence 0-100, None if no OCR
    needs_human_review: bool
    warnings: list[str] = field(default_factory=list)
    mode: str = "ocr"                   # T10: ocr | vision | late | early (used for image pages only)
    page_details: list[dict] = field(default_factory=list)  # per page: route + vision / fusion details
    review_reasons: list[str] = field(default_factory=list)

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
    """Run Tesseract and return word boxes (x0, y0, x1, y1, text, confidence, 0) + confidences."""
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
        words.append((x0, y0, x0 + data["width"][i], y0 + data["height"][i], text, conf, 0))
        confidences.append(conf)
    return words, confidences


def _ocr_image(image: Image.Image) -> tuple[str, float | None, str, list[float]]:
    """OCR one page image. Returns (text, average confidence 0-100, layout, confidence of each word of the text).

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
        return "", None, "unknown", []

    cols = _find_columns(words, image.width, max_cross_ratio=0.03)
    if cols is None:
        conf = round(sum(confidences) / len(confidences), 1)
        rows = _merge_rows(words)
        return _blocks_to_text(rows), conf, "single_column", _blocks_confs(rows)

    # Two columns: crop each region and read it on its own.
    cut, top_y = cols["cut"], cols["column_top"]
    regions = []
    if cols["top"]:
        regions.append((0, 0, image.width, int(top_y)))
    regions.append((0, int(top_y), int(cut), image.height))
    regions.append((int(cut), int(top_y), image.width, image.height))

    parts, all_conf, word_confs = [], [], []
    for box in regions:
        region_words, region_conf = _ocr_words(image.crop(box))
        if region_words:
            rows = _merge_rows(region_words)
            parts.append(_blocks_to_text(rows))
            word_confs += _blocks_confs(rows)
            all_conf += region_conf
    conf = round(sum(all_conf) / len(all_conf), 1) if all_conf else None
    return "\n\n".join(parts), conf, "two_column", word_confs


def _ocr_with_cleanup(image: Image.Image, warnings: list[str]) -> tuple[str, float | None, str, list[float]]:
    """OCR the page; if confidence is low, retry on denoised copies and keep the best.

    A median filter removes "salt and pepper" dots from bad scans, which
    Tesseract otherwise reads as letters. It is not applied to clean images,
    because it can also thin out small letters.
    """
    text, conf, layout, word_confs = _ocr_image(image)
    if conf is not None and conf >= RETRY_OCR_CONFIDENCE:
        return text, conf, layout, word_confs

    best = (text, conf, layout, word_confs, None)
    for size in DENOISE_SIZES:
        t, c, l, w = _ocr_image(image.filter(ImageFilter.MedianFilter(size)))
        if c is not None and (best[1] is None or c > best[1]):
            best = (t, c, l, w, size)
    if best[4] is not None:
        warnings.append(f"Noisy image: denoised before OCR (median {best[4]}), "
                        f"confidence {conf} -> {best[1]}.")
    return best[:4]


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
                       max(b[2] for b in row), max(b[3] for b in row), text, [b[5] for b in row], 0))
    return merged


def _blocks_confs(rows: list) -> list[float]:
    """Word confidences in the order of the words of _blocks_to_text(rows) (Tesseract words hold no spaces)."""
    return [c for row in rows for c in row[5]]


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
    if image.mode in ("RGBA", "LA", "P"):           # transparent PNG -> white background
        image = image.convert("RGBA")
        background = Image.new("RGBA", image.size, "white")
        image = Image.alpha_composite(background, image)
    image = image.convert("L")                      # grayscale
    image = ImageOps.autocontrast(image, cutoff=1)  # stretch faded scans
    if image.width < MIN_IMAGE_WIDTH:               # small photos -> upscale
        ratio = MIN_IMAGE_WIDTH / image.width
        image = image.resize((MIN_IMAGE_WIDTH, int(image.height * ratio)), Image.LANCZOS)
    try:                                            # fix pages photographed sideways
        osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
        if osd.get("rotate") and osd.get("orientation_conf", 0) > 2:
            rotated = image.rotate(-osd["rotate"], expand=True)
            # T10: OSD said "rotate 180" for upright phone photos of dense pages (dev K05_p01, K08_p02), and OCR then
            # read the page upside down. Keep the rotation only if OCR is more confident on the rotated image.
            if _mean_conf(rotated) > _mean_conf(image):
                image = rotated
    except Exception:
        pass  # orientation detection is optional
    return image


def _mean_conf(image: Image.Image) -> float:
    _, confidences = _ocr_words(image)
    return sum(confidences) / len(confidences) if confidences else 0.0


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

def _image_page(image: Image.Image, mode: str, warnings: list[str], details: list[dict]) -> tuple[str, float | None, str, str]:
    """One page image (photo, or a scanned PDF page) read with the chosen mode (T10, multimodal.py).
    Path 1 (OCR) always runs: it is the fallback and the input of both fusions. Returns (text, conf, layout, route).
    T10b: in late mode with READER_PARALLEL=1 (default), OCR (CPU) and the vision call (GPU) run at the same time, then
    the same merge runs; the output is identical to the sequential path (READER_PARALLEL=0). One vision call at a time."""
    if mode == "late" and os.environ.get("READER_PARALLEL", "1") == "1":
        return _late_page_parallel(image, warnings, details)
    ocr = _ocr_with_cleanup(_prepare_photo(image), warnings)
    if mode == "ocr":
        details.append({"route": "ocr"})
        return ocr[0], ocr[1], ocr[2], "ocr"
    from .multimodal import read_image_page  # lazy: the OCR-only path needs no HTTP client
    page = read_image_page(image, mode, ocr, warnings)
    details.append({"route": page["route"], **page["detail"]})
    return page["text"], page["ocr_confidence"], page["layout"], page["route"]


def _late_page_parallel(image: Image.Image, warnings: list[str], details: list[dict]) -> tuple[str, float | None, str, str]:
    """Late fusion with both readers at once. Warnings keep the sequential order (OCR first, then vision / fusion).
    A vision error comes back as a value (OCR fallback, as before); an OCR error is raised after the vision call has
    finished, as in the sequential path."""
    from concurrent.futures import ThreadPoolExecutor

    from .multimodal import VISION_PROMPT, load_prompt, read_image_page, vision_or_error
    image.load()  # PIL loads lazily: load once here, not in two threads at the same time
    prompt = load_prompt(VISION_PROMPT)
    ocr_warnings: list[str] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        vision_job = pool.submit(vision_or_error, image, prompt)
        ocr_job = pool.submit(lambda: _ocr_with_cleanup(_prepare_photo(image), ocr_warnings))
        ocr = ocr_job.result()  # an OCR error leaves the block only after the vision call is done
        vision = vision_job.result()
    warnings.extend(ocr_warnings)
    page = read_image_page(image, "late", ocr, warnings, vision=vision)
    details.append({"route": page["route"], **page["detail"]})
    return page["text"], page["ocr_confidence"], page["layout"], page["route"]


def _read_pdf(data: bytes, warnings: list[str], mode: str = "ocr",
              details: list[dict] | None = None) -> tuple[str, list[str], str, float | None]:
    details = [] if details is None else details
    try:
        pdf = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ReaderError(f"Corrupt or unreadable PDF: {exc}") from exc
    if pdf.needs_pass:
        raise ReaderError("The PDF is password-protected.")
    if pdf.page_count == 0:
        raise ReaderError("The PDF has no pages.")
    if pdf.page_count > MAX_PDF_PAGES:
        raise ReaderError(f"The PDF has {pdf.page_count} pages; a CV may have at most {MAX_PDF_PAGES}.")

    page_texts, routes, layouts, confidences = [], [], [], []
    for page in pdf:
        raw = page.get_text("text").strip()
        if len(raw) >= MIN_CHARS_TEXT_PAGE:
            blocks, layout = _order_blocks(page.get_text("blocks"), page.rect.width)
            page_texts.append("\n\n".join(b[4].strip() for b in blocks))
            routes.append("text")
            layouts.append(layout)
            details.append({"route": "text"})
        else:
            pix = page.get_pixmap(dpi=OCR_DPI)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            text, conf, layout, route = _image_page(image, mode, warnings, details)
            page_texts.append(text)
            routes.append(route)
            layouts.append(layout)
            if conf is not None:
                confidences.append(conf)
    pdf.close()

    scanned = sum(r != "text" for r in routes)
    if scanned:
        warnings.append(f"{scanned} page(s) had no text layer and were read with "
                        f"{'OCR' if mode == 'ocr' else 'mode ' + mode}.")
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


def _read_image(data: bytes, warnings: list[str], mode: str = "ocr",
                details: list[dict] | None = None) -> tuple[str, float | None, str, str]:
    try:
        image = Image.open(io.BytesIO(data))
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ReaderError(f"The image is {image.width}x{image.height} pixels; at most {MAX_IMAGE_PIXELS // 10**6} "
                              "megapixels are accepted.")
        image.load()
    except ReaderError:
        raise
    except Exception as exc:
        raise ReaderError(f"Unreadable image: {exc}") from exc
    warnings.append(f"Image file: text was read with {'OCR' if mode == 'ocr' else 'mode ' + mode}.")
    return _image_page(image, mode, warnings, [] if details is None else details)


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
    if _decode_text(data) is not None and (
            Path(name).suffix.lower() in TEXT_EXTENSIONS or len(data) >= MIN_TEXT_FILE_BYTES):
        return "text"
    ext = Path(name).suffix.lower() or "no extension"
    raise ReaderError(f"Unsupported file type ({ext}). Use PDF, DOCX, JPG, PNG or TXT.")


TEXT_EXTENSIONS = {".txt", ".text", ".md"}
MIN_TEXT_FILE_BYTES = 200   # without a .txt name, only accept real text, not a few random bytes


def _decode_text(data: bytes) -> str | None:
    """UTF-8 (with or without BOM), UTF-16 with BOM, else Windows-1252. None if it is not text."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        candidates = ["utf-16"]
    else:
        candidates = ["utf-8-sig", "cp1252"]
    for encoding in candidates:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        printable = sum(c.isprintable() or c in "\n\r\t" for c in text)
        if text.strip() and printable / len(text) >= 0.97:
            return text
    return None


# ------------------------------------------------------------- entry point ---

def quality_reasons(text: str, ocr_conf: float | None, details: list[dict], warnings: list[str] | None = None) -> list[str]:
    """Review reasons when the read text cannot be trusted (the gate sends these pairs to review, T10)."""
    warnings = [] if warnings is None else warnings
    reasons = []
    if len(text) < MIN_CV_CHARS or (ocr_conf is not None and ocr_conf < LOW_OCR_CONFIDENCE):
        reasons.append("reader:low_confidence_or_little_text")
    if any(d.get("unclear_share", 0) > MAX_UNCLEAR_SHARE for d in details):
        reasons.append("reader:many_unclear_parts")
        warnings.append(f"The vision model marked more than {MAX_UNCLEAR_SHARE:.0%} of a page as [unclear].")
    low_trust = sum(d.get("fusion", {}).get("low_trust_words", 0) for d in details)
    if low_trust > MAX_LOW_TRUST_SHARE * max(1, len(text.split())):
        reasons.append("reader:many_low_trust_lines")
    if any(d.get("vision_truncated") for d in details):
        reasons.append("reader:vision_output_truncated")
    words = re.findall(r"[^\W\d_]+", text.lower())
    if len(words) >= 50 and sum(w in ENGLISH_WORDS for w in words) / len(words) < MIN_ENGLISH_SHARE:
        reasons.append("reader:non_english_text")  # T13: the Matcher and the prompts are English-only
        warnings.append("The CV does not look like English text: a person should read it.")
    return reasons


def read_cv(source: str | Path | bytes, file_name: str | None = None, mode: str = "ocr") -> ReaderResult:
    """Read a CV from a path or raw bytes (e.g. an upload from n8n / FastAPI).
    mode (T10) decides how image pages are read: ocr | vision | late | early (see multimodal.py)."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        data = path.read_bytes()
        file_name = file_name or path.name
    else:
        data = source
        file_name = file_name or "upload"

    if not data:
        raise ReaderError("The file is empty.")

    if mode not in ("ocr", "vision", "late", "early"):
        raise ReaderError(f"Unknown reader mode {mode!r}: use ocr, vision, late or early.")
    warnings: list[str] = []
    details: list[dict] = []
    file_type = _detect_type(data, file_name)
    ocr_conf, layout = None, "unknown"

    if file_type == "pdf":
        raw, routes, layout, ocr_conf = _read_pdf(data, warnings, mode, details)
    elif file_type == "docx":
        raw, routes = _read_docx(data, warnings), ["text"]
    elif file_type == "text":
        raw, routes = _decode_text(data), ["text"]
    else:
        raw, ocr_conf, layout, route = _read_image(data, warnings, mode, details)
        routes = [route]

    text = clean_text(raw)
    sections = split_sections(text)

    if len(text) < MIN_CV_CHARS:
        warnings.append(f"Very little text found ({len(text)} characters).")
    if ocr_conf is not None and ocr_conf < LOW_OCR_CONFIDENCE:
        warnings.append(f"Low OCR confidence ({ocr_conf}/100): the text may contain errors.")
    if set(sections) <= {"header"}:
        warnings.append("No section headings recognised (Experience, Education, ...).")

    reasons = quality_reasons(text, ocr_conf, details, warnings)
    needs_review = bool(reasons)

    return ReaderResult(
        file_type=file_type,
        text=text,
        sections=sections,
        pages=len(routes),
        page_routes=routes,
        layout=layout,
        ocr_confidence=ocr_conf,
        needs_human_review=needs_review,
        warnings=warnings,
        mode=mode,
        page_details=details,
        review_reasons=reasons,
    )
