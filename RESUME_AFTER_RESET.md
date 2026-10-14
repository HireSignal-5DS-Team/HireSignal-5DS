# Resume after reset

Repo `semahayachi/HireSignal-5DS`, branch `claude/vigilant-albattani-dmn3pk` (never `main`, never `claude/kind-albattani-k7qlt9`).
Environment: `HireSignal-Kaggle` cloud env (Hugging Face reachable; `download.pytorch.org` blocked, install torch from PyPI).

Setup:
```bash
pip install torch "transformers>=4.51" peft huggingface_hub accelerate datasets pytest bm25s==0.3.13 qdrant-client fastapi httpx tabulate pandas
python -m pytest -q matcher rag/tests/test_rag.py benchmark finetune
```

State and next action: see `PROJECT_STATE.md` (authoritative). Results: `benchmark/results/`, LoRA runs: `finetune/runs/`.
All long jobs are resumable (`benchmark/run.py` skips finished requirements; `finetune/train_lora.py` resumes from the latest checkpoint).
