# T10 Part E: one real end-to-end run with a phone photo (real-GPU)

- Input: `data/raw/scans/K01_photo.jpg` (phone photo of a laptop screen showing L02.pdf = pair P15), sent as the `cv`
  file of the webhook with job J2 and the confirmed card `data/processed/jobs/J2_requirements.json`.
- Command: `.venv\Scripts\python scripts\n8n_e2e.py --out eval\results\2026-10-18_n8n_e2e_photo --runs scan:K01_photo.jpg:P15 --cards`
- Stack: llama-server :8090 (Qwen3-4B + LoRA, 3.25 GB resident), station API :8010 (`READER_MODE` default `late`),
  our Ollama :11434 (`qwen2.5vl:3b`, keep_alive 0, models in `models/ollama`), n8n 2.43.7 :5678 (workflow
  `n8n/hiresignal_v1.json`, `HTTP /reader` timeout 900 s).
- Result: execution 31, HTTP 200, valid JSON, outcome `review` (score 59, waiting at the recruiter form). The digital
  P15 run gives `review` too (T10 Part D). Identity values found in the execution data: 0; raw CV text in the execution
  data: no; all /match calls with LoRA scale 1; 4 quotes with verified positions.
- Reader block of the result: file_type `image`, mode `late`, read_path `["late"]`, OCR confidence 93.1, vision model
  `qwen2.5vl:3b`, `[unclear]` share 0, fusion: 313 words agree, 18 vision words used where OCR disagreed, 5 vision-only
  words kept as OCR-supported, 0 low-trust lines, no review reason.
- Timings: Reader 119.4 s (vision call 112.8 s), Profile 31.5 s, Match + Judge 19.5 s, total wall time 171.9 s.
- Peak VRAM (nvidia-smi, every 0.5 s): 5,912 of 6,141 MiB. With llama-server resident, Ollama still loads qwen2.5vl
  fully on the GPU and Windows spills into shared memory: the vision call takes ~113 s instead of ~10-15 s with a
  free GPU (benchmark). `num_gpu` 0 / 10 / 18 gave 100 / 77 / 72 s for the same page (no real gain).
- First attempt (execution 29) failed: `HTTP /reader` timed out at 120 s ("The connection was aborted") while the
  vision call was still running; the error workflow logged it. Fix: `HTTP /reader` timeout 900 s.
