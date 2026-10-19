Ollama Modelfiles (T02).
- `Modelfile.hs-qwen3-4b`: created as `hs-qwen3-4b` and kept for the record. It is not used for the Matcher, Profile or Job Agent: since T02b these run on llama.cpp `llama-server` on port 8090.
- `Modelfile.hs-matcher`: refused by Ollama 0.40.5 ("LoRA adapters are no longer supported"). Kept as evidence for the decision to serve the LoRA with llama.cpp.
