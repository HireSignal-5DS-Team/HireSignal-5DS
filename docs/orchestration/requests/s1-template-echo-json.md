# Request S1 → S6 (owner of `matcher/prompt.py`, `matcher/validate.py`) and S2 (owner of `matcher/backends_api.py`)

Status: proposed, 2026-10-16. No frozen file was edited by S1. Evidence: `rag_opt/results/error_analysis.md`
(`python -m rag_opt.error_analysis`, recorded predictions only, no LLM run).

## Finding

Every unparsed answer of the base Qwen3-4B Q4 Matcher in the five recorded val runs is **valid JSON that copies the
enum template of the p1 system prompt**: `"decision": "MET|MISSING|UNCERTAIN", "basis": "supported|contradicted|..."`
(A′ 14/14, B′ 27/27, C 24/25, A 10/10, B 17/17; the remaining C case is another schema violation). None is
truncated (completion tokens 64–104 of 192). The echo rate rises with longer prompts (6.4 % / 15.8 % / 9.9 % by
prompt-length tertile; 8 % with no reference vs 17 % with three in B′) and also occurs on byte-identical prompts
(7 vs 6 of 87 in B′ vs A′): it is a prompt-format failure of the base model that RAG amplifies, not a RAG failure.
The LoRA Matcher shows **0** echoes in 138/202 recorded answers (checkpoint `302a424`, LoRA + legacy BM25).

## Options (decision for the owners)

1. **S2, no frozen-contract change (recommended for the base/fallback model):** send llama.cpp's
   `response_format: {"type": "json_schema", "schema": <ModelAnswer schema>}` (or a GBNF grammar) from
   `OpenAICompatBackend`, behind a flag, so the enum can only take a valid value. It keeps prompt p1 (the LoRA was
   trained on p1) and the validator unchanged. Measure on val before enabling it.
2. **S6, prompt p2:** replace the `A|B|C` template line with one concrete example object. Changes the frozen prompt,
   and the LoRA was trained on p1, so this needs its own comparison; not recommended now.
3. Not recommended: mapping an echoed enum to a decision in `validate.py` (it would invent a decision the model did
   not make).
