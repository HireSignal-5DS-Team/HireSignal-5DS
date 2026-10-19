# reader-vision v1 — exact transcription rules

| field | value |
|---|---|
| prompt id | reader-vision-v1 |
| station | 1 Reader, path 2 (local vision model via Ollama) |
| version | v1 |
| date | 2026-10-18 (T10) |
| role | Transcribe the text of one CV page from an image (phone photo or scan), as plain text. |
| technique | Zero-shot instruction with explicit transcription rules: copy exactly, keep reading order and headings, plain-text output format (no Markdown, no comments), never add or guess, mark unreadable parts as `[unclear]`. |
| change vs previous | v0 only said "Read this CV.". On dev, qwen2.5vl:3b with v0 answered "Certainly! Here is a summary of the key points from the CV:" and rewrote the page as Markdown headings and shortened bullets (dev CER 0.50). v1 asks for an exact, complete, plain-text transcription and gives a marker for unreadable parts instead of guessing. |

The image of one page goes in the same user message (Ollama `images`).

## User

```text
Transcribe all the text in this image of one CV page, exactly as it is written.
Rules:
- Copy every word, number, date, e-mail and name exactly as printed. Do not correct, translate, summarise or rephrase.
- Keep the reading order: top to bottom; if the page has two columns, write the whole left column first, then the right column.
- Keep section headings (e.g. EXPERIENCE, EDUCATION, SKILLS) on their own line, and one text line per printed line.
- Never add text that is not in the image. Do not guess missing words.
- If a part is too blurry or cut off to read, write [unclear] in its place.
- Output plain text only: no Markdown (no **, #, tables), no comments, no introduction.
```
