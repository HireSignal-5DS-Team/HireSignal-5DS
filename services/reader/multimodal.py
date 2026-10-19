"""Reader path 2 (a local vision model via Ollama) and the fusion of the two paths (T10).

Modes for one page image (photo, or a scanned PDF page without text layer):
    ocr    - path 1 only: Tesseract with image clean-up (reader.py)
    vision - path 2 only: the vision model transcribes the image (prompt reader-vision v1)
    late   - LATE FUSION (main method): both paths run separately, then CODE merges them (late_fuse below);
             no LLM decides the merge ("the LLM judges, code counts")
    early  - EARLY FUSION (compared): one vision-model call gets the image + the OCR text and corrects it
             (prompt reader-early-fusion v1)
If Ollama cannot be reached, every mode falls back to OCR with a warning (never a crash).
Settings (env): OLLAMA_BASE_URL, READER_VISION_MODEL, READER_VISION_KEEP_ALIVE, READER_VISION_MAX_SIDE,
READER_FUSION_MERGE (vision_backbone | ocr_backbone), READER_FUSION_MIN_CONF, READER_VISION_TIMEOUT_S.
Defaults = the setup chosen on dev in T10 (eval/results/2026-10-18_multimodal/, docs/MULTIMODAL_REPORT.md).
"""
from __future__ import annotations

import base64
import difflib
import io
import os
import re
import string
import time
from pathlib import Path

import httpx
from PIL import Image, ImageOps
from rapidfuzz import fuzz, process

from services.prompts import prompt_blocks

ROOT = Path(__file__).resolve().parents[2]
MODES = ("ocr", "vision", "late", "early")
VISION_PROMPT = "prompts/reader/vision_v1.md"
EARLY_PROMPT = "prompts/reader/early_fusion_v1.md"
UNCLEAR = "[unclear]"
MAX_KEPT_INSERT = 2          # vision-only runs of <= 2 words inside OCR-supported text are kept (a word OCR dropped)
OPTIONS = {"temperature": 0, "seed": 0, "num_ctx": 8192, "num_predict": 2048}


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


class VisionUnavailable(Exception):
    """Ollama is not reachable or answered with an error."""


# ------------------------------------------------------------------ vision path ---

def load_prompt(path: str) -> str:
    """The text of the prompt file's single fenced block ('## User' or '## User template')."""
    blocks = prompt_blocks(ROOT / path)
    return blocks.get("User") or blocks["User template"]


def image_b64(image: Image.Image, max_side: int | None = None) -> str:
    """JPEG (quality 90) of the page, longest side cut to max_side: the model's visual tokens grow with the size."""
    image = ImageOps.exif_transpose(image).convert("RGB")
    max_side = max_side or int(env("READER_VISION_MAX_SIDE", "1536"))
    if max(image.size) > max_side:
        image.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def strip_wrapping(text: str) -> str:
    """Remove a ``` fence around the whole answer (some models wrap their transcription in one)."""
    t = text.strip()
    m = re.fullmatch(r"```[a-zA-Z]*\n(.*?)\n?```", t, flags=re.S)
    return m.group(1) if m else t


def vision_call(image: Image.Image, prompt: str, model: str | None = None, client: httpx.Client | None = None) -> dict:
    """One Ollama /api/chat call with the page image. Returns {text, model, latency_s, eval_count, done_reason}."""
    model = model or env("READER_VISION_MODEL", "qwen2.5vl:3b")
    body = {"model": model, "stream": False, "keep_alive": env("READER_VISION_KEEP_ALIVE", "0"), "options": OPTIONS,
            "messages": [{"role": "user", "content": prompt, "images": [image_b64(image)]}]}
    url = env("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/chat"
    t = time.perf_counter()
    try:
        c = client or httpx.Client(timeout=float(env("READER_VISION_TIMEOUT_S", "300")))
        r = c.post(url, json=body)
        r.raise_for_status()
        out = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise VisionUnavailable(f"{type(exc).__name__}: {exc}") from exc
    return {"text": strip_wrapping(out["message"]["content"]), "model": model,
            "latency_s": round(time.perf_counter() - t, 2), "eval_count": out.get("eval_count"),
            "done_reason": out.get("done_reason")}


def early_prompt(ocr_text: str, template: str | None = None) -> str:
    safe = ocr_text.replace("<<<", "‹‹‹").replace(">>>", "›››")
    return (template or load_prompt(EARLY_PROMPT)).replace("{ocr}", safe)


# ------------------------------------------------------------------ late fusion ---

def tokens(text: str) -> list[str]:
    """Words, with '\\n' as a token at each line end (keeps the line structure through the alignment)."""
    out = []
    for line in text.splitlines():
        words = line.split()
        if words:
            out += words + ["\n"]
    return out


def norm(tok: str) -> str:
    t = tok.lower().strip(string.punctuation + "•·–—‘’“”")
    return t or tok.lower()


def join_tokens(toks: list[str]) -> str:
    lines = (" ".join(line.split()) for line in " ".join(toks).split("\n"))
    return "\n".join(x for x in lines if x)


def late_fuse(ocr_text: str, ocr_confs: list[float], vision_text: str, min_conf: float) -> dict:
    """Merge the two paths in code.

    Align the OCR words and the vision words (difflib on normalised words, line ends kept as tokens). Then:
    - equal               -> keep (both paths agree);
    - replace             -> the OCR words if their mean Tesseract confidence >= min_conf, else the vision words;
    - OCR only (delete)   -> keep if mean confidence >= min_conf, else drop (OCR noise, e.g. moire);
    - vision only (insert)-> a run of <= MAX_KEPT_INSERT words is kept (a word OCR dropped inside a supported line);
                             longer runs have no OCR support: NOT added to the text, returned as low-trust lines.
    Returns {text, low_trust_lines, stats}.
    """
    a = tokens(ocr_text)
    words = [t for t in a if t != "\n"]
    if len(words) != len(ocr_confs):  # cannot pair words with confidences: treat OCR words as unsure
        ocr_confs = [0.0] * len(words)
    it = iter(ocr_confs)
    conf = [None if t == "\n" else next(it) for t in a]
    b = tokens(vision_text)
    sm = difflib.SequenceMatcher(None, [norm(t) for t in a], [norm(t) for t in b], autojunk=False)
    out, low_trust = [], []
    stats = {"agree": 0, "ocr_kept": 0, "vision_used": 0, "ocr_dropped": 0, "vision_kept_short": 0, "low_trust_words": 0}

    def mean_conf(i1, i2):
        cs = [c for c in conf[i1:i2] if c is not None]
        return sum(cs) / len(cs) if cs else 100.0

    def n_words(toks):
        return sum(t != "\n" for t in toks)

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out += a[i1:i2]
            stats["agree"] += n_words(a[i1:i2])
        elif op == "replace":
            if mean_conf(i1, i2) >= min_conf:
                out += a[i1:i2]
                stats["ocr_kept"] += n_words(a[i1:i2])
            else:
                out += b[j1:j2] + (["\n"] if "\n" in a[i1:i2] and "\n" not in b[j1:j2] else [])
                stats["vision_used"] += n_words(b[j1:j2])
        elif op == "delete":
            if mean_conf(i1, i2) >= min_conf:
                out += a[i1:i2]
                stats["ocr_kept"] += n_words(a[i1:i2])
            else:
                out += [t for t in a[i1:i2] if t == "\n"]
                stats["ocr_dropped"] += n_words(a[i1:i2])
        else:  # insert
            run = b[j1:j2]
            if n_words(run) <= MAX_KEPT_INSERT and UNCLEAR not in " ".join(run):
                out += run
                stats["vision_kept_short"] += n_words(run)
            else:
                low_trust += [x for x in join_tokens(run).splitlines() if x.strip()]
                stats["low_trust_words"] += n_words(run)
    return {"text": join_tokens(out), "low_trust_lines": low_trust, "stats": stats}


SUPPORT_SHARE = 0.5          # a vision-only run counts as OCR-supported if >= half of its words occur in the OCR text
FUZZY_SUPPORT = 75           # ... "occur" = an OCR word with rapidfuzz ratio >= 75 (OCR misreads: "Managemest")


def supported_share(words: list[str], ocr_bag: set[str], ocr_list: list[str]) -> float:
    if not words:
        return 0.0
    hits = sum(w in ocr_bag or (len(w) > 3 and process.extractOne(w, ocr_list, scorer=fuzz.ratio,
                                                                  score_cutoff=FUZZY_SUPPORT) is not None)
               for w in words)
    return hits / len(words)


def late_fuse_vision(ocr_text: str, ocr_confs: list[float], vision_text: str, min_conf: float) -> dict:
    """Merge v2 (T10, designed on dev): the VISION text is the backbone (it keeps the reading order and the line
    structure better on photos), the OCR text checks it.

    Align vision words with OCR words (difflib, normalised words, line ends kept). Then:
    - equal                 -> keep;
    - replace               -> the OCR words if their mean Tesseract confidence >= min_conf, else the vision words;
    - vision only           -> kept if >= SUPPORT_SHARE of its words occur anywhere in the OCR text, exactly or as a
                               close OCR misread (FUZZY_SUPPORT) (same text, other reading order), or if it is a run
                               of <= MAX_KEPT_INSERT words; otherwise it has no
                               OCR support: NOT added to the text, returned as low-trust lines;
    - OCR only              -> kept if mean confidence >= min_conf (text the vision model skipped), else dropped.
    Returns {text, low_trust_lines, stats} like late_fuse.
    """
    a = tokens(vision_text)
    b = tokens(ocr_text)
    ocr_words = [t for t in b if t != "\n"]
    if len(ocr_words) != len(ocr_confs):
        ocr_confs = [0.0] * len(ocr_words)
    it = iter(ocr_confs)
    conf = [None if t == "\n" else next(it) for t in b]
    ocr_bag = {norm(t) for t in ocr_words}
    ocr_list = sorted(ocr_bag)
    sm = difflib.SequenceMatcher(None, [norm(t) for t in a], [norm(t) for t in b], autojunk=False)
    out, low_trust = [], []
    stats = {"agree": 0, "ocr_kept": 0, "vision_used": 0, "ocr_dropped": 0, "vision_kept_short": 0,
             "vision_kept_supported": 0, "low_trust_words": 0}

    def mean_conf(j1, j2):
        cs = [c for c in conf[j1:j2] if c is not None]
        return sum(cs) / len(cs) if cs else 100.0

    def n_words(toks):
        return sum(t != "\n" for t in toks)

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out += a[i1:i2]
            stats["agree"] += n_words(a[i1:i2])
        elif op == "replace":
            if mean_conf(j1, j2) >= min_conf:
                out += b[j1:j2] + (["\n"] if "\n" in a[i1:i2] and "\n" not in b[j1:j2] else [])
                stats["ocr_kept"] += n_words(b[j1:j2])
            else:
                out += a[i1:i2]
                stats["vision_used"] += n_words(a[i1:i2])
        elif op == "delete":  # vision only
            run = a[i1:i2]
            words = [norm(t) for t in run if t != "\n"]
            supported = supported_share(words, ocr_bag, ocr_list) >= SUPPORT_SHARE
            if supported:
                out += run
                stats["vision_kept_supported"] += len(words)
            elif len(words) <= MAX_KEPT_INSERT and UNCLEAR not in " ".join(run):
                out += run
                stats["vision_kept_short"] += len(words)
            else:
                low_trust += [x for x in join_tokens(run).splitlines() if x.strip()]
                stats["low_trust_words"] += len(words)
                out += [t for t in run if t == "\n"]
        else:  # insert: OCR only
            if mean_conf(j1, j2) >= min_conf:
                out += b[j1:j2]
                stats["ocr_kept"] += n_words(b[j1:j2])
            else:
                stats["ocr_dropped"] += n_words(b[j1:j2])
    return {"text": join_tokens(out), "low_trust_lines": low_trust, "stats": stats}


MERGES = {"ocr_backbone": late_fuse, "vision_backbone": late_fuse_vision}


def unclear_share(text: str) -> float:
    n = len(text.split())
    return round(text.count(UNCLEAR) / n, 4) if n else 0.0


# ------------------------------------------------------------- one page, one mode ---

def vision_or_error(image: Image.Image, prompt: str, client: httpx.Client | None = None):
    """The vision call for a worker thread (T10b): the result dict, or the VisionUnavailable error as a value."""
    try:
        return vision_call(image, prompt, client=client)
    except VisionUnavailable as exc:
        return exc


def read_image_page(image: Image.Image, mode: str, ocr: tuple, warnings: list[str],
                    client: httpx.Client | None = None, vision=None) -> dict:
    """ocr = (text, confidence, layout, word confidences) of path 1 for this page (always computed: it is the
    fallback and the input of both fusions). vision (T10b, late mode in parallel): the vision result already computed
    by vision_or_error (a dict or a VisionUnavailable); None = call the model here.
    Returns {text, route, ocr_confidence, layout, detail}."""
    text, conf, layout, word_confs = ocr
    page = {"text": text, "route": "ocr", "ocr_confidence": conf, "layout": layout, "detail": {}}
    if mode == "ocr":
        return page
    if mode not in MODES:
        raise ValueError(f"unknown reader mode {mode!r}; use one of {MODES}")
    try:
        if vision is not None:
            if isinstance(vision, VisionUnavailable):
                raise vision
            v = vision
        elif mode == "early":
            v = vision_call(image, early_prompt(text), client=client)
        else:
            v = vision_call(image, load_prompt(VISION_PROMPT), client=client)
    except VisionUnavailable as exc:
        warnings.append(f"Vision model not reachable ({exc}); page read with OCR only.")
        page["route"] = "ocr (vision fallback)"
        return page
    detail = {"vision_model": v["model"], "vision_latency_s": v["latency_s"], "unclear_share": unclear_share(v["text"])}
    if v["done_reason"] == "length":
        warnings.append("Vision model output was cut at the token limit.")
        detail["vision_truncated"] = True
    if mode in ("vision", "early"):
        return page | {"text": v["text"], "route": mode, "detail": detail}
    fuse = MERGES[env("READER_FUSION_MERGE", "vision_backbone")]
    fused = fuse(text, word_confs, v["text"], float(env("READER_FUSION_MIN_CONF", "101")))
    detail |= {"low_trust_lines": fused["low_trust_lines"], "fusion": fused["stats"]}
    if fused["low_trust_lines"]:
        warnings.append(f"{len(fused['low_trust_lines'])} line(s) read only by the vision model (no OCR support): "
                        "kept out of the text, listed as low-trust.")
    return page | {"text": fused["text"], "route": "late", "detail": detail}
