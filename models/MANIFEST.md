# Model manifest

The `models/` folder is git-ignored. Files were copied on 2026-10-18 from the V1 HF cache, which was only read (`C:\Users\semah\HireSignal-Integration\repo\.cache\hf\hub`), or downloaded from the Hugging Face Hub.

- **Hashes:** SHA-256 from `sha256sum`.
- **"Hub match":** our hash equals the LFS sha256 the Hub reports for that revision (checked 2026-10-18).
- **Licences:** from the Hub model cards.

| File | Source repo @ revision | Size (bytes) | SHA-256 | Hub match | Licence |
|---|---|---|---|---|---|
| `Qwen3-4B-Instruct-2507-Q4_K_M.gguf` | `unsloth/Qwen3-4B-Instruct-2507-GGUF` @ `a06e946bb6b655725eafa393f4a9745d460374c9` (base `Qwen/Qwen3-4B-Instruct-2507` @ `cdbee75f…`) | 2,497,281,120 | `3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597` | yes | Apache-2.0 |
| `hiresignal-lora-f16.gguf` | Converted from `HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora` @ `0b6925b1e3c89b6b266b10bcd30af4c6a0c2dc3a` (`adapter_model.safetensors`, r16, alpha 32). The team converted it locally with llama.cpp `convert_lora_to_gguf.py --outtype f16` (tag b5116, per V2 `RUN_LOCAL.md`). | 132,155,232 | `345ed967cb50f734340f2093b1ff011629bbd9adb166a2f5754c24ee4654d493` | n/a (the GGUF is not on the Hub) | Apache-2.0 (adapter repo) |
| `Qwen3-0.6B-Q8_0.gguf` | `Qwen/Qwen3-0.6B-GGUF` @ `23749fefcc72300e3a2ad315e1317431b06b590a` | 639,446,688 | `9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031` | yes; also equals the pin in V2 `reporter/slm.py` | Apache-2.0 |
| `nli-deberta-v3-xsmall/` | `cross-encoder/nli-deberta-v3-xsmall` @ `a150876415327c80daeff35ca6f68f5ed8cf5c24` | 294,477,138 (folder) | `model.safetensors`: `4e4fc4977f8d29d2a164255c8f69b9d6c158deeb309bb5e70445b94666ccd9e9` | yes | Apache-2.0 |
| `DeBERTa-v3-base-mnli-fever-anli/` | `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` @ `6f5cf0a2b59cabb106aca4c287eed12e357e90eb` (same pin as V2 `matcher/factory.py`). Downloaded from the Hub. | 380,025,162 (folder) | `model.safetensors`: `06d6fd89edd4f97816831626daafbdb0b029cf63bae8edc0bccab1d64e2e7707` | downloaded at the pinned revision | MIT |
| `all-MiniLM-L6-v2/` | `sentence-transformers/all-MiniLM-L6-v2` @ `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Downloaded from the Hub (T09 RAG benchmark). | 91,614,939 (folder) | `model.safetensors`: `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db` | downloaded at the pinned revision | Apache-2.0 |
| `multilingual-e5-base/` | `intfloat/multilingual-e5-base` @ `d128750597153bb5987e10b1c3493a34e5a4502a`. Downloaded from the Hub (T09 RAG benchmark). | 1,156,514,514 (folder) | `model.safetensors`: `a18a44fad1d0b46ded15928144138cff1135d5cc8233bdd90be5f18822de09a7` | downloaded at the pinned revision | MIT |
| `bge-small-en-v1.5/` | `BAAI/bge-small-en-v1.5` @ `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`. Downloaded from the Hub (T09 RAG benchmark). | 134,414,573 (folder) | `model.safetensors`: `3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad` | downloaded at the pinned revision | MIT |
| `ms-marco-MiniLM-L-6-v2/` | `cross-encoder/ms-marco-MiniLM-L-6-v2` @ `233902d25c440f23af6f7d6e94d2946bac0bee0a`. Downloaded from the Hub (T09 RAG benchmark). | 91,822,038 (folder) | `model.safetensors`: `821d1aa69520101d6e0737f78a042ae25b19e5cb9160701909d10434f4aeb0ae` | downloaded at the pinned revision | Apache-2.0 |
| `bge-reranker-base/` | `BAAI/bge-reranker-base` @ `2cfc18c9415c912f9d8155881c133215df768a70`. Downloaded from the Hub (T09 RAG benchmark). | 1,134,377,834 (folder) | `model.safetensors`: `ced967c45fd1902eb92716c9ceeca7c95a936770ea9db611f5a841b926e33fbd` | downloaded at the pinned revision | MIT |
| `ollama/` (Ollama store, `OLLAMA_MODELS`): `qwen2.5vl:3b` | Ollama library `qwen2.5vl:3b`, pulled 2026-10-18 with our Ollama 0.40.6 (`scripts/start_ollama.ps1`); 3.8B, Q4_K_M; **chosen Reader vision model (T10)** | 3,200,627,168 | manifest digest `fb90415cde1ef08aa669ae74b082d49b158729b6db1ab183c941417d507e71a1` | pulled by tag (Ollama checks every blob's sha256) | Apache-2.0 per the Ollama manifest. Note: the upstream Hugging Face card of Qwen2.5-VL-3B-Instruct names the Qwen Research License (non-commercial); fine for this course project, to check before any commercial use |
| `ollama/`: `granite3.2-vision:2b` | Ollama library `granite3.2-vision:2b`, pulled 2026-10-18; 2.5B, Q4_K_M (T10 benchmark only) | 2,437,852,465 | manifest digest `3be41a661804ad72cd08269816c5a145f1df6479ad07e2b3a7e29dba575d2669` | pulled by tag | Apache-2.0 |
| `ollama/`: `gemma3:4b` | Ollama library `gemma3:4b`, pulled 2026-10-18; 3.9B, Q4_K_M (T10 benchmark only) | 3,350,272,403 | manifest digest `68ceab7e468a31c988b44d5a4984a0e21f58c4f7158c6ce29c1804babac38df7` | pulled by tag | Gemma Terms of Use |

`pytorch_model.bin` was not copied for either DeBERTa model; `model.safetensors` holds the same weights.

## All file hashes

```
3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597  Qwen3-4B-Instruct-2507-Q4_K_M.gguf
345ed967cb50f734340f2093b1ff011629bbd9adb166a2f5754c24ee4654d493  hiresignal-lora-f16.gguf
9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031  Qwen3-0.6B-Q8_0.gguf
a4b6bfe668f2b3cf6f0cd535e98a0663d2d0d4a4a15f13075ad3597d33985a23  nli-deberta-v3-xsmall/added_tokens.json
8d9f07bf7ba54a6fc3b1962483056f94c39dcf188db4cf61843e1c88f94b2342  nli-deberta-v3-xsmall/config.json
4e4fc4977f8d29d2a164255c8f69b9d6c158deeb309bb5e70445b94666ccd9e9  nli-deberta-v3-xsmall/model.safetensors
ed7c099c988dbb414b18a6980d20cb57b91b7cd119f6f6941eb364b0e892e712  nli-deberta-v3-xsmall/special_tokens_map.json
c679fbf93643d19aab7ee10c0b99e460bdbc02fedf34b92b05af343b4af586fd  nli-deberta-v3-xsmall/spm.model
5124ef2ead1a10a717703bc436de7f353da76d6340e4587719b42b1693707964  nli-deberta-v3-xsmall/tokenizer.json
f3eecd07c370ef0bf7dd3780d3cd68cf9c8b00c267e21a208ddcd8f82bfec1a6  nli-deberta-v3-xsmall/tokenizer_config.json
4ffce2b113463476777ccc8efd1f0ea0571510a96a2c84f2d2aab152951b13ca  DeBERTa-v3-base-mnli-fever-anli/README.md
dc046d04c9b0ada7ae6f1dc89c465801799acdf0c9a6aab8c15a1b2d5ca4e91f  DeBERTa-v3-base-mnli-fever-anli/added_tokens.json
a6c616d6dabeacf90fd0e776c741d3f0f30a05533ccf0bd3b5b62e94cfaa8d57  DeBERTa-v3-base-mnli-fever-anli/config.json
06d6fd89edd4f97816831626daafbdb0b029cf63bae8edc0bccab1d64e2e7707  DeBERTa-v3-base-mnli-fever-anli/model.safetensors
9463f61e1b109a8eb4688b829260d7c6b1e6dff04c98ff7269bb89e2b92369b9  DeBERTa-v3-base-mnli-fever-anli/special_tokens_map.json
c679fbf93643d19aab7ee10c0b99e460bdbc02fedf34b92b05af343b4af586fd  DeBERTa-v3-base-mnli-fever-anli/spm.model
05402ffae6dd382a8491b1d29bfc139bec5d332662e86a026f433ce54c25c202  DeBERTa-v3-base-mnli-fever-anli/tokenizer.json
557b3d33d3f41b81ad769244e506549e98a1857d41dd58160aacd4d98d710b5a  DeBERTa-v3-base-mnli-fever-anli/tokenizer_config.json
53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db  all-MiniLM-L6-v2/model.safetensors
a18a44fad1d0b46ded15928144138cff1135d5cc8233bdd90be5f18822de09a7  multilingual-e5-base/model.safetensors
3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad  bge-small-en-v1.5/model.safetensors
821d1aa69520101d6e0737f78a042ae25b19e5cb9160701909d10434f4aeb0ae  ms-marco-MiniLM-L-6-v2/model.safetensors
ced967c45fd1902eb92716c9ceeca7c95a936770ea9db611f5a841b926e33fbd  bge-reranker-base/model.safetensors
```
