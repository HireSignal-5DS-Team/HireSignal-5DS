"""Two chunking strategies for job descriptions, compared in the evaluation.

Both return chunks with character offsets into the job body, so retrieval hits can be
scored against the same gold evidence spans regardless of strategy.

S1 fixed:     sliding window of FIXED_WORDS words with FIXED_OVERLAP words overlap.
S2 structure: one chunk per section of the posting (split at its own headings),
              prefixed with "Job: <title> | Section: <heading>"; long sections are
              split at line or sentence boundaries. No overlap: boundaries are semantic.
"""
import re

FIXED_WORDS = 200    # ~260 subword tokens; holds about one JD section
FIXED_OVERLAP = 30   # 15%: a requirement bullet cut at a boundary survives whole in one window
MAX_SECTION_WORDS = 300

# A heading is a markdown heading, a short line ending with ":", a short ALL-CAPS line,
# or a short (<= 6 words) unpunctuated line that follows a blank line (e.g. "About the role").
HEADING = re.compile(r"^(#{1,6}\s+.+|[^\n]{2,80}:|[A-Z][A-Z0-9 &/,'()-]{2,79})\s*$"
                     r"|(?:\A|(?<=\n\n))([A-Z][^\n.!?;:]{1,60})\s*$", re.M)


def fixed_chunks(job):
    body = job["text"]
    words = [m.span() for m in re.finditer(r"\S+", body)]
    chunks, step = [], FIXED_WORDS - FIXED_OVERLAP
    for i in range(0, max(len(words) - FIXED_OVERLAP, 1), step):
        w = words[i:i + FIXED_WORDS]
        start, end = w[0][0], w[-1][1]
        chunks.append(_chunk(job, "fixed", len(chunks), start, end, body[start:end], section=None))
    return chunks


def structure_chunks(job):
    body = job["text"]
    heads = [m for m in HEADING.finditer(body) if m.group(1) or len(m.group(2).split()) <= 6]
    bounds = [(0, None)] + [(m.start(), (m.group(1) or m.group(2)).strip("#: ").strip()) for m in heads]
    chunks = []
    for (start, heading), nxt in zip(bounds, bounds[1:] + [(len(body), None)]):
        end = nxt[0]
        if not body[start:end].strip():
            continue
        for s, e in _split_long(body, start, end):
            label = heading or "Overview"
            text = f"Job: {job['title']} | Section: {label}\n{body[s:e].strip()}"
            chunks.append(_chunk(job, "structure", len(chunks), s, e, text, section=label))
    return chunks


def _split_long(body, start, end):
    """Split a section longer than MAX_SECTION_WORDS at line or sentence boundaries."""
    if len(body[start:end].split()) <= MAX_SECTION_WORDS:
        return [(start, end)]
    parts, s, count = [], start, 0
    # units are lines or sentences: scraped postings can hold a 1,000-word section on a single line
    for m in re.finditer(r".+?(?:[.!?;]\s+|\n+|$)", body[start:end], re.S):
        n = len(m.group().split())
        if count and count + n > MAX_SECTION_WORDS:
            parts.append((s, start + m.start()))
            s, count = start + m.start(), 0
        count += n
    parts.append((s, end))
    return parts


def _chunk(job, strategy, i, start, end, text, section):
    return {
        "chunk_id": f"{job['doc_id']}#{strategy}-{i}", "doc_id": job["doc_id"], "source_type": "job",
        "title": job["title"], "url": job.get("source_url"), "section": section,
        "start": start, "end": end, "text": text,
    }


STRATEGIES = {"fixed": fixed_chunks, "structure": structure_chunks}
