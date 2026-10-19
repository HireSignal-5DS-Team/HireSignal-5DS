r"""Printable PDFs of 5 labelled CVs for the scan/photo robustness test (step 2 of the scan set).

Renders the gold-labelled Djinni CVs below as designed one-column A4 PDFs in data/raw/scans/L01.pdf .. L05.pdf. The CV
text is kept verbatim line by line (only styling and line wrapping change), so the gold quotes still apply and a photo
of the printout can be compared with the original decision. Also renames the 5 Kaggle IT PDFs already copied into
data/raw/scans/ to K01.pdf .. K05.pdf (sorted by Kaggle id) and writes data/raw/scans/MANIFEST.csv.
Fonts: Segoe UI from %WINDIR%\Fonts (covers the dashes, bullets and curly quotes in the CVs).
Usage: .venv\Scripts\python scripts\make_scan_cvs.py
"""
import csv
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
SCANS = ROOT / "data/raw/scans"
MANIFEST = SCANS / "MANIFEST.csv"
KAGGLE_IT = ROOT / "data/raw/kaggle_resume/data/data/INFORMATION-TECHNOLOGY"

# 2 invite, 2 review, 1 reject; all 4 jobs. Pairs whose CV header is English only (Reader is English OCR).
PICKS = [("L01", "P02"), ("L02", "P15"), ("L03", "P47"), ("L04", "P52"), ("L05", "P43")]

NAVY, ACCENT, GREY, LIGHT = HexColor("#1F2A44"), HexColor("#2E6DB4"), HexColor("#555555"), HexColor("#EEF2F7")
HEADER_KEYS = ("Position:", "Experience years:", "English level:")
BULLET = re.compile(r"^\s*([-•—–*]|\d+[.)])\s")


def fonts():
    fdir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    pdfmetrics.registerFont(TTFont("UI", str(fdir / "segoeui.ttf")))
    pdfmetrics.registerFont(TTFont("UI-Bold", str(fdir / "segoeuib.ttf")))
    pdfmetrics.registerFont(TTFont("UI-Light", str(fdir / "segoeuil.ttf")))


def styles():
    s = {
        "kicker": ParagraphStyle("kicker", fontName="UI-Bold", fontSize=8.5, textColor=HexColor("#AFC4E6"), leading=11),
        "title": ParagraphStyle("title", fontName="UI-Light", fontSize=20, textColor=HexColor("#FFFFFF"), leading=24),
        "meta": ParagraphStyle("meta", fontName="UI", fontSize=9.5, textColor=NAVY, leading=13),
        "head": ParagraphStyle("head", fontName="UI-Bold", fontSize=10.5, textColor=ACCENT, leading=14, spaceBefore=6,
                               spaceAfter=2),
        "role": ParagraphStyle("role", fontName="UI-Bold", fontSize=10, textColor=NAVY, leading=13.5, spaceBefore=5),
        "body": ParagraphStyle("body", fontName="UI", fontSize=9.5, textColor=HexColor("#222222"), leading=13.2),
    }
    s["bullet"] = ParagraphStyle("bullet", parent=s["body"], leftIndent=12, firstLineIndent=-8)
    return s


def line_style(line: str, s: dict) -> ParagraphStyle:
    t = line.strip()
    if BULLET.match(line):
        return s["bullet"]
    if t.startswith(("Position:", "Role:", "Project ")):
        return s["role"]
    if t.endswith(":") and len(t) <= 60:
        return s["head"]
    return s["body"]


def header_block(cv_id: str, header: list[str], s: dict, width: float):
    title = header[0].split(":", 1)[1].strip() if header and header[0].startswith("Position:") else "Candidate"
    band = Table([[Paragraph("CURRICULUM VITAE", s["kicker"])], [Paragraph(escape(title), s["title"])]],
                 colWidths=[width])
    band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("LEFTPADDING", (0, 0), (-1, -1), 14),
                              ("TOPPADDING", (0, 0), (-1, 0), 12), ("BOTTOMPADDING", (0, -1), (-1, -1), 12)]))
    cells = [Paragraph(escape(h), s["meta"]) for h in header]
    meta = Table([cells], colWidths=[width / max(len(cells), 1)] * len(cells))
    meta.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("LEFTPADDING", (0, 0), (-1, -1), 14),
                              ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                              ("LINEBELOW", (0, 0), (-1, -1), 1.5, ACCENT)]))
    return [band, meta, Spacer(1, 8)]


def render(cv_id: str, text: str, out: Path, s: dict):
    lines = text.split("\n")
    header = [ln.strip() for ln in lines[:3] if ln.strip().startswith(HEADER_KEYS)]
    body = lines[len(header):]
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"CV {cv_id}", author="", creator="", producer="")
    story = header_block(cv_id, header, s, doc.width)
    for ln in body:
        if not ln.strip():
            story.append(Spacer(1, 5))
            continue
        story.append(Paragraph(escape(ln.strip()), line_style(ln, s)))
    doc.build(story)


def main():
    fonts()
    s = styles()
    pairs = {p["pair_id"]: p for p in csv.DictReader(open(ROOT / "data/labels/gold/pairs_gold.csv", encoding="utf-8"))}
    rows = []
    kaggle = sorted(p for p in SCANS.glob("*.pdf") if re.fullmatch(r"\d+", p.stem))
    for i, src in enumerate(kaggle, 1):
        assert (KAGGLE_IT / src.name).exists(), src.name
        dst = SCANS / f"K{i:02d}.pdf"
        src.rename(dst)
        rows.append({"file_id": dst.stem, "source": "kaggle_resume/INFORMATION-TECHNOLOGY", "source_file": src.name,
                     "pair_id": "", "job": "", "gold_outcome": "", "split": ""})
    known = {r["file_id"] for r in rows}
    if MANIFEST.exists():  # re-run: keep the Kaggle rows from the first run
        rows += [r for r in csv.DictReader(open(MANIFEST, encoding="utf-8"))
                 if r["file_id"].startswith("K") and r["file_id"] not in known]
    for cv_id, pid in PICKS:
        p = pairs[pid]
        text = (ROOT / "data/processed/cvs" / p["cv_file"]).read_text(encoding="utf-8")
        render(cv_id, text, SCANS / f"{cv_id}.pdf", s)
        rows.append({"file_id": cv_id, "source": "djinni (data/processed/cvs)", "source_file": p["cv_file"],
                     "pair_id": pid, "job": p["job"], "gold_outcome": p["gold_outcome"], "split": p["split"]})
    rows.sort(key=lambda r: r["file_id"])
    with open(MANIFEST, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r["file_id"], r["source_file"], r["pair_id"], r["job"], r["gold_outcome"])


if __name__ == "__main__":
    main()
