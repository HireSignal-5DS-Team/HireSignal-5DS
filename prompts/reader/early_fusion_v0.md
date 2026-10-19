# reader-early-fusion v0 — naive baseline

| field | value |
|---|---|
| prompt id | reader-early-fusion-v0 |
| station | 1 Reader, setup 4 "early fusion" (one vision-model call with the image + the OCR text) |
| version | v0 |
| date | 2026-10-18 (T10) |
| role | Correct the Tesseract OCR text of one CV page by looking at the page image. |
| technique | Zero-shot instruction with the OCR text pasted in the prompt (fenced by `<<< >>>`) and the image attached; the task's one-line wording. |
| change vs previous | First version. |

Code fills `{ocr}` with the OCR text of the page (`<<<` / `>>>` in it neutralised).

## User template

```text
Correct this OCR text using the image; do not add anything that is not in the image.

<<<
{ocr}
>>>
```
