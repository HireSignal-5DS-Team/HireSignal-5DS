# reader-vision v0 — naive baseline

| field | value |
|---|---|
| prompt id | reader-vision-v0 |
| station | 1 Reader, path 2 (local vision model via Ollama) |
| version | v0 |
| date | 2026-10-18 (T10) |
| role | Read the text of one CV page from an image (phone photo or scan). |
| technique | Zero-shot, one-line instruction, no rules (the naive baseline the task asks for). |
| change vs previous | First version. |

The image of one page goes in the same user message (Ollama `images`).

## User

```text
Read this CV.
```
