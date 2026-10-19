# reader-early-fusion v1 — correction rules + output format

| field | value |
|---|---|
| prompt id | reader-early-fusion-v1 |
| station | 1 Reader, setup 4 "early fusion" (one vision-model call with the image + the OCR text) |
| version | v1 |
| date | 2026-10-18 (T10) |
| role | Correct the Tesseract OCR text of one CV page by looking at the page image; output the corrected page as plain text. |
| technique | Zero-shot instruction, OCR text fenced by `<<< >>>` and marked as a draft, explicit rules: fix only misread characters/words, keep the OCR line order, delete OCR noise, never add or guess, `[unclear]` marker, plain-text output only. |
| change vs previous | v0 gave no output format and no limits. On dev (qwen2.5vl:3b) v0 opened 2/10 pages with a comment ("Certainly! Here is the corrected text based on the image:" + "---") and wrapped headings in Markdown bold (`**Education**`); dev CER 0.285. v1 says what may be changed (misreads, OCR noise), keeps the OCR line order, and asks for the plain text only: 0/10 comments, dev CER 0.191. |

Code fills `{ocr}` with the OCR text of the page (`<<<` / `>>>` in it neutralised).

## User template

```text
Below is the OCR text of the CV page in the image. OCR makes mistakes on photos and scans.
Correct it using the image:
- Fix misread characters and words so they match the image exactly (names of tools, dates, numbers, e-mails).
- Keep the line order of the OCR text; add a line only if it is clearly printed in the image and missing from the OCR text.
- Delete OCR noise that is not printed text (random symbols, screen or moire artefacts).
- Never add text that is not in the image. Do not guess. If a part cannot be read, write [unclear].
- Output only the corrected text, plain text: no Markdown, no comments, no introduction.

OCR text:
<<<
{ocr}
>>>
```
