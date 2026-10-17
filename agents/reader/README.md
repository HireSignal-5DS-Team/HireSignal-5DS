# Reader (step 1)

Turns any CV file into **clean text + sections**. No AI model, only tools.

| Input | Tool | Notes |
|---|---|---|
| Text PDF | PyMuPDF | Detects two-column CVs and reads left column, then right |
| Scanned PDF | PyMuPDF renders the page, Tesseract reads it | A page with < 50 characters of text is treated as a scan |
| Word `.docx` | python-docx | Also reads page headers, tables and text boxes (sidebars) |
| Photo / image | Pillow cleans it, Tesseract reads it | Fixes rotation, transparency, contrast, small size; crops columns before OCR; denoises bad scans |
| Text `.txt` | read as is | UTF-8, UTF-16 or Windows-1252 (Notepad) |

The file type is detected from the file's **content**, not its extension.
The file name is **not** kept in the result: it often contains the candidate's name.

## Output (`ReaderResult`)

```json
{
  "file_type": "pdf",
  "text": "full clean text ...",
  "sections": {
    "header": "Sami Trabelsi\nsami@example.com | +216 ...",
    "experience": "Data Engineer - Vermeg 2022 - 2024\n...",
    "education": "...",
    "skills": "Python, SQL, PyTorch ..."
  },
  "pages": 1,
  "page_routes": ["text"],
  "layout": "single_column",
  "ocr_confidence": null,
  "needs_human_review": false,
  "warnings": []
}
```

- `header` = everything before the first heading (usually name + contact).
  `header` and `contact` hold personal data: the **Profile Agent** anonymises them.
- Section names: `header, contact, summary, experience, education, skills,
  projects, certifications, languages, interests`. English and French headings.
- `needs_human_review` is `true` when OCR confidence < 60 or the text is too short.

## Use it

```python
from agents.reader import read_cv, ReaderError

result = read_cv("cv.pdf")                    # from a path
result = read_cv(file_bytes, "upload.pdf")    # from an upload (FastAPI / n8n)
result.to_dict()                              # JSON-ready
```

From the command line:

```
python scripts/read_cv.py samples\cv1.pdf samples\cv2.docx --json out
```

## Setup on Windows

1. `pip install -r requirements.txt`
2. Install Tesseract (UB Mannheim installer), tick **French** in the languages
   screen, keep the default folder `C:\Program Files\Tesseract-OCR`.
   The Reader finds it there automatically. If you installed it elsewhere,
   set the environment variable `TESSERACT_CMD` to the full path of `tesseract.exe`.

## Tests

```
python -m pytest -q
```

The tests build fake CVs on the fly (single-column PDF, two-column PDF, DOCX,
photo, scanned PDF), so no real personal data is stored in the repo.

## What real CVs taught us (for the report)

| Real CV | Problem | Fix |
|---|---|---|
| cv02.pdf | `Technical skills: Java, ...` on the heading's line was swallowed by Education | Inline headings (`Label: content`) start a section; job-level labels like `Tools:` don't |
| 1.png | Salt-and-pepper noise: OCR confidence 53.5, text unreadable | If confidence < 80, retry with median filters (3, 5) and keep the best: 53.5 -> 88.1 |

## Known limits (for the report)

- CVs with **no headings at all** put everything in `header`. The full `text` is
  still complete, and the Profile Agent's NER finds titles, degrees and dates.

- Column detection handles **two** columns, not three.
- Old `.doc` files are refused (ask for `.docx` or PDF).
- Handwritten CVs and very blurry photos give low OCR confidence → flagged for a person.
- Section detection is rule-based: an unusual heading ("My journey") is not recognised
  and its text stays in the previous section.
