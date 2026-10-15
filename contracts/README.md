# Job Agent contract (`JobRequirements`)

What the **Job Agent** produces from a job post: a requirements card.
It was missing from `pipeline.schema.json`, so this file fills that gap in the same style.

- Python model: [`job_requirements.py`](job_requirements.py) (Pydantic v2)
- JSON Schema: [`job_requirements.schema.json`](job_requirements.schema.json)
  (regenerate with `python -m contracts.job_requirements`)
- Example: [`../examples/job_post.example.txt`](../examples/job_post.example.txt) →
  [`../examples/job_requirements.example.json`](../examples/job_requirements.example.json)

## One requirement

| Field | Meaning | Example |
|---|---|---|
| `req_id` | id inside the job: `r1`, `r2`, ... | `r1` |
| `text` | the requirement, one short statement | `At least 3 years of professional experience with Java` |
| `evidence` | **exact quote** from the job post (code checks it) | `At least 3 years of professional experience with Java and Spring Boot.` |
| `kind` | `must` (required) or `nice` (a plus, preferred) | `must` |
| `category` | `skill`, `experience`, `education`, `certification`, `language`, `other` | `experience` |
| `skill_terms` | skill/tool names, used as search queries by the Matcher | `["Java"]` |
| `min_years` | minimum years if the post gives a number, else `null` | `3` |
| `chunk_ids` | RAG chunks of the job post it came from (empty until indexed) | `["JD-001-C03"]` |

Around the list: `job_id`, `title`, `language`, `uncertain` (what the agent could not
establish), `needs_human_review`, `warnings`.

## Design choices

- **`evidence` on every requirement**, like `ParsedCV`: the agent cannot invent a
  requirement that is not in the post, because code checks the quote.
- **One requirement = one thing to check.** "3 years of Java and Spring Boot" becomes
  two requirements (r1 Java, r2 Spring Boot), so a CV can meet one and miss the other.
  Both share the same `evidence`.
- **`must` / `nice`** follows the post's wording ("required" vs "a plus", "preferred",
  "would be appreciated").
- **Compatible with the Matcher:** `card.to_matcher_job()` gives exactly the `Job`
  object in `matcher/schemas.py`. `chunk_ids` links to the RAG chunks of
  `pipeline.schema.json` (`RequirementMatch.chunk_ids`).
- **Strict:** unknown fields, empty quotes, duplicate ids and wrong values are refused.

## Open questions for the team

1. Should `RequirementMatch.requirement` in `pipeline.schema.json` hold our `req_id`
   or the requirement `text`?
2. Who fills `chunk_ids`: the Job Agent (if the job post is chunked first) or the RAG step?
