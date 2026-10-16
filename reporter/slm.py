"""SLM backends for the report writer.

LlamaCppSLM: Qwen/Qwen3-0.6B, official GGUF (Qwen/Qwen3-0.6B-GGUF, Q8_0) run in-process by llama-cpp-python, CPU,
greedy decoding, JSON-schema grammar, thinking mode disabled (empty <think></think> block, see slm_prompt.chatml).
ScriptedSLM: fixed outputs for tests ONLY; its provenance says MOCK and the writer never labels it as the pinned model.
"""
import hashlib
import os
import time
from pathlib import Path

from . import slm_prompt

MODEL = {
    "model_id": "Qwen/Qwen3-0.6B",
    "model_revision": "c1899de289a04d12100db370d81485cdf75e47ca",
    "gguf_repo": "Qwen/Qwen3-0.6B-GGUF",
    "gguf_revision": "23749fefcc72300e3a2ad315e1317431b06b590a",
    "gguf_file": "Qwen3-0.6B-Q8_0.gguf",
    "gguf_sha256": "9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031",
    "licence": "apache-2.0",
    "params": "0.6B (0.44B non-embedding), 28 layers",
}


class SLMUnavailable(RuntimeError):
    pass


def find_gguf(env=None):
    """Path of the pinned GGUF: HS_REPORTER_MODEL_PATH, else the Hugging Face cache at the pinned revision.
    Downloads only if HS_REPORTER_DOWNLOAD=1. Raises SLMUnavailable otherwise."""
    env = os.environ if env is None else env
    if p := env.get("HS_REPORTER_MODEL_PATH"):
        if Path(p).is_file():
            return Path(p)
        raise SLMUnavailable(f"HS_REPORTER_MODEL_PATH={p} not found")
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as e:
        raise SLMUnavailable("huggingface_hub not installed") from e
    try:
        return Path(hf_hub_download(MODEL["gguf_repo"], MODEL["gguf_file"], revision=MODEL["gguf_revision"],
                                    local_files_only=env.get("HS_REPORTER_DOWNLOAD") != "1"))
    except Exception as e:  # noqa: BLE001 - offline / not cached
        raise SLMUnavailable(f"pinned GGUF not cached ({type(e).__name__}); set HS_REPORTER_DOWNLOAD=1") from e


def _sha256(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


class LlamaCppSLM:
    is_mock = False

    def __init__(self, path=None, threads=None, timeout_s=None, max_tokens=None, verify_sha=True, env=None):
        env = os.environ if env is None else env
        try:
            from llama_cpp import Llama, LlamaGrammar, StoppingCriteriaList
        except ImportError as e:
            raise SLMUnavailable("llama-cpp-python not installed") from e
        self.path = Path(path) if path else find_gguf(env)
        self.sha256 = _sha256(self.path) if verify_sha else None
        if verify_sha and self.sha256 != MODEL["gguf_sha256"]:
            raise SLMUnavailable(f"GGUF sha256 {self.sha256[:12]} != pinned {MODEL['gguf_sha256'][:12]}")
        self.threads = int(threads or env.get("HS_REPORTER_THREADS", 4))
        self.timeout_s = float(timeout_s or env.get("HS_REPORTER_TIMEOUT", 30))
        self.max_tokens = int(max_tokens or env.get("HS_REPORTER_MAX_TOKENS", 160))
        t0 = time.perf_counter()
        self.llm = Llama(str(self.path), n_ctx=4096, n_threads=self.threads, seed=0, verbose=False)
        self.load_s = time.perf_counter() - t0
        import json

        self.grammars = {k: LlamaGrammar.from_json_schema(json.dumps(v), verbose=False)
                         for k, v in slm_prompt.OUTPUT_SCHEMA.items()}
        import llama_cpp

        self._stops = StoppingCriteriaList
        self.runtime = f"llama-cpp-python {llama_cpp.__version__}, CPU, {self.threads} threads, n_ctx 4096"

    def info(self):
        return {**MODEL, "model": f"{MODEL['gguf_repo']}@{MODEL['gguf_revision'][:8]}/{MODEL['gguf_file']}",
                "verified_sha256": self.sha256, "runtime": self.runtime,
                "decoding": {"temperature": 0, "max_tokens": self.max_tokens, "grammar": "JSON schema per section",
                             "thinking": "disabled (empty <think></think>, enable_thinking=False)",
                             "timeout_s": self.timeout_s},
                "load_s": round(self.load_s, 2), "mock": False}

    def generate(self, kind, facts, feedback=None):
        """Raw text for one section. Raises TimeoutError when the per-call budget is exceeded."""
        prompt = slm_prompt.chatml(slm_prompt.messages(kind, facts, feedback))
        t0 = time.perf_counter()
        timed_out = []

        def stop(_ids, _logits):
            if time.perf_counter() - t0 > self.timeout_s:
                timed_out.append(True)
                return True
            return False

        out = self.llm.create_completion(prompt, max_tokens=self.max_tokens, temperature=0.0, top_k=1,
                                         grammar=self.grammars[kind], stopping_criteria=self._stops([stop]))
        if timed_out:
            raise TimeoutError(f"SLM call exceeded {self.timeout_s:g}s")
        return out["choices"][0]["text"]


class ScriptedSLM:
    """Test double: returns scripted strings (or raises scripted exceptions). Labelled MOCK in provenance."""
    is_mock = True

    def __init__(self, fn):
        self.fn, self.calls = fn, []

    def info(self):
        return {"model": "scripted-test-double", "mock": True, "runtime": "python"}

    def generate(self, kind, facts, feedback=None):
        self.calls.append((kind, facts, feedback))
        r = self.fn(kind, facts, len(self.calls))
        if isinstance(r, BaseException):
            raise r
        return r
