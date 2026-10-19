r"""Download the production models at the pinned revisions of models/MANIFEST.md, and verify every file's sha256 (T13).

  .venv\Scripts\python scripts\download_models.py            # download what is missing, then verify
  .venv\Scripts\python scripts\download_models.py --verify   # only verify the files in models\ against the manifest

Production set: Qwen3-4B-Instruct-2507 Q4_K_M (GGUF), the NLI Judge (DeBERTa-v3-base-mnli-fever-anli), the RAG
embedder (all-MiniLM-L6-v2). The Matcher LoRA GGUF (hiresignal-lora-f16.gguf) is not on the Hub: see INSTALL.md
(convert the team adapter with llama.cpp convert_lora_to_gguf.py, then verify its sha256 here). The vision model
qwen2.5vl:3b comes from Ollama (INSTALL.md). Benchmark-only models (e5, bge, rerankers, 0.6B) are optional (--all).
"""
import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
PROD = [  # (target in models/, repo, revision, files or None = whole repo snapshot)
    ("Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "unsloth/Qwen3-4B-Instruct-2507-GGUF",
     "a06e946bb6b655725eafa393f4a9745d460374c9", ["Qwen3-4B-Instruct-2507-Q4_K_M.gguf"]),
    ("DeBERTa-v3-base-mnli-fever-anli", "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli",
     "6f5cf0a2b59cabb106aca4c287eed12e357e90eb", None),
    ("all-MiniLM-L6-v2", "sentence-transformers/all-MiniLM-L6-v2", "1110a243fdf4706b3f48f1d95db1a4f5529b4d41", None),
]
OPTIONAL = [
    ("Qwen3-0.6B-Q8_0.gguf", "Qwen/Qwen3-0.6B-GGUF", "23749fefcc72300e3a2ad315e1317431b06b590a", ["Qwen3-0.6B-Q8_0.gguf"]),
    ("multilingual-e5-base", "intfloat/multilingual-e5-base", "d128750597153bb5987e10b1c3493a34e5a4502a", None),
    ("bge-small-en-v1.5", "BAAI/bge-small-en-v1.5", "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a", None),
    ("ms-marco-MiniLM-L-6-v2", "cross-encoder/ms-marco-MiniLM-L-6-v2", "233902d25c440f23af6f7d6e94d2946bac0bee0a", None),
    ("bge-reranker-base", "BAAI/bge-reranker-base", "2cfc18c9415c912f9d8155881c133215df768a70", None),
]


def manifest_hashes() -> dict[str, str]:
    """path (relative to models/) -> sha256, from the hash list and the table of models/MANIFEST.md."""
    text = (MODELS / "MANIFEST.md").read_text(encoding="utf-8")
    out = {}
    for h, path in re.findall(r"^([0-9a-f]{64})\s+(\S+)$", text, flags=re.M):
        out[path] = h
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify() -> bool:
    ok = True
    for rel, want in sorted(manifest_hashes().items()):
        p = MODELS / rel
        if not p.exists():
            print(f"missing   {rel}")
            continue
        got = sha256(p)
        print(f"{'OK      ' if got == want else 'MISMATCH'}  {rel}")
        ok &= got == want
    return ok


def download(items):
    os.environ["HF_HUB_OFFLINE"] = "0"
    from huggingface_hub import hf_hub_download, snapshot_download
    for target, repo, rev, files in items:
        dest = MODELS / target
        if dest.exists():
            print(f"present   {target}")
            continue
        print(f"download  {repo} @ {rev[:8]} -> models/{target}", flush=True)
        if files:
            for f in files:
                hf_hub_download(repo, f, revision=rev, local_dir=MODELS)
        else:
            snapshot_download(repo, revision=rev, local_dir=dest,
                              allow_patterns=["*.json", "*.txt", "*.model", "model.safetensors", "1_Pooling/*",
                                              "*.md", "spm.model"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="only verify")
    ap.add_argument("--all", action="store_true", help="also the benchmark-only models")
    a = ap.parse_args()
    if not a.verify:
        download(PROD + (OPTIONAL if a.all else []))
    sys.exit(0 if verify() else 1)


if __name__ == "__main__":
    main()
