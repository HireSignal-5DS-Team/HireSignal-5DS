# Licences of the main packages, tools, models and data (T13)

Collected on 2026-10-19 from the installed package metadata (`importlib.metadata`), the model cards (Hub / Ollama
manifests, `models/MANIFEST.md`) and the tool websites. Budget zero: everything is free. `pip check`: "No broken
requirements found."

## Python packages (`requirements.txt`, the main ones)

| package | version | licence |
|---|---|---|
| fastapi | 0.143.3 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| pydantic | 2.14.1 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| python-multipart | 0.0.32 | Apache-2.0 |
| python-dotenv | 1.2.4 | BSD-3-Clause |
| torch | 2.14.1+cu126 | BSD-3-Clause style (PyTorch licence; bundles Apache-2.0 / LLVM parts) |
| transformers | 5.20.1 | Apache-2.0 |
| tokenizers / safetensors | 0.23.3 / 0.8.0 | Apache-2.0 |
| huggingface-hub | 1.33.0 | Apache-2.0 |
| sentence-transformers | 6.1.0 | Apache-2.0 |
| scikit-learn | 1.9.1 | BSD-3-Clause |
| numpy | 2.5.2 | BSD-3-Clause (+ bundled MIT / Zlib / 0BSD / CC0 parts) |
| qdrant-client | 1.19.1 | Apache-2.0 |
| bm25s | 0.3.13 | MIT |
| **PyMuPDF** | 1.28.2 | **AGPL-3.0** (or an Artifex commercial licence) |
| pytesseract | 0.3.13 | Apache-2.0 |
| pillow | 12.3.0 | MIT-CMU (HPND) |
| python-docx | 1.2.0 | MIT |
| openpyxl | 3.1.5 | MIT |
| RapidFuzz | 3.14.6 | MIT |
| pytest | 9.1.1 | MIT |

**Note on PyMuPDF (AGPL-3.0).** It is fine for this course project. If the app were offered as a network service to
others, AGPL would require publishing the source, or buying a commercial licence. `pypdf` (BSD) is a possible swap
for the text route, but it has no page rendering for OCR.

## Tools

| tool | version | licence |
|---|---|---|
| llama.cpp (llama-server) | b11139 | MIT |
| Ollama | 0.40.6 | MIT |
| n8n | 2.43.7 | Sustainable Use License (fair-code: free for internal / personal / non-commercial use; not OSI open source) |
| Node.js | 24.22.0 | MIT |
| Tesseract OCR (UB Mannheim build) | 5.5.3 | Apache-2.0 |

## Models (`models/MANIFEST.md`: revision + sha256 of each file)

| model | role | licence |
|---|---|---|
| Qwen3-4B-Instruct-2507 Q4_K_M (unsloth GGUF) | Matcher base, Profile, Job Agent, Report Writer | Apache-2.0 |
| HireSignal Matcher LoRA (team adapter, converted to GGUF) | Matcher | Apache-2.0 (adapter repo) |
| DeBERTa-v3-base-mnli-fever-anli | Judge (NLI) | MIT |
| all-MiniLM-L6-v2 | RAG embedder (production) | Apache-2.0 |
| qwen2.5vl:3b (Ollama) | Reader vision path | Apache-2.0 per the Ollama manifest; the upstream Hugging Face card of Qwen2.5-VL-3B-Instruct names the Qwen Research License (non-commercial): to check before any commercial use |
| Benchmark only: Qwen3-0.6B, nli-deberta-v3-xsmall, multilingual-e5-base, bge-small-en-v1.5, ms-marco-MiniLM-L-6-v2, bge-reranker-base, granite3.2-vision:2b, gemma3:4b | | Apache-2.0 / MIT; gemma3: Gemma Terms of Use |

## Data

| data | licence |
|---|---|
| ESCO v1.1.1 (via the Tabiya CSV mirror) | CC BY 4.0 (European Commission) |
| Djinni Recruitment Dataset, English part (CVs, job posts; `data/processed/`) | MIT (`data/processed/NOTICE_DJINNI.md`: the copyright notice must stay with the copies) |
| Kaggle resume dataset (source of the dev photos) | CC0-1.0 (`data/DATA_CARD.md`) |
| other datasets listed in `data/DATA_CARD.md` | as recorded there (one is GPL-3.0) |
