# Cheap model metrics — openai/gpt-oss-20b (via Groq)

Real 50-item run. `--provider openai`, `--base-url https://api.groq.com/openai/v1`,
`--api-key-env GROQ_API_KEY`, `--max-tokens 600`, temperature 0, same
`src/prompt.txt` and `data/items.jsonl` order used for every model.

## Accuracy

**48/50 correct (96.0%)**

Both misses are the same failure mode: `era` field mismatch, everything else
correct.

| id | driver | got | expected | other 4 fields |
|---|---|---|---|---|
| d03 | Max Verstappen | `"Modern Era"` | `"Turbo-Hybrid Era"` | all correct |
| d38 | Carlos Sainz Jr. | `"Modern Era"` | `"Turbo-Hybrid Era"` | all correct |

Both drivers debuted in 2015 — squarely inside the 2007-2021 Turbo-Hybrid Era
range given in the prompt, not a boundary year. The model correctly extracted
`debut_year: 2015` in both cases but misapplied its own stated classification
rule. Not a parsing or attribution failure (the distractor trap wasn't
involved in either miss) — a genuine reasoning error on the era rule.

## Latency

- p50: 6816ms
- p95: 8163ms

## Cost (Groq pricing used: $0.10 / 1M input tokens, $0.50 / 1M output tokens)

- Cost per 1k requests: **$0.22**
- Cost per 1k requests at 100x traffic: **$22.45** (same unit cost, just more of them)

## max_tokens finding (worth keeping, not just a bug to bury)

The first attempt at this run used the old default of `--max-tokens 200`
with the OpenAI SDK's `max_tokens` parameter, against 2 items as a smoke
test. All completions came back with `raw_output=""` and an empty `error`
column — the call succeeded, but produced nothing usable, and nothing in
run.py's output would have told you why without inspecting the raw API
response directly.

The cause: **gpt-oss-20b's hidden reasoning tokens share the same
output-token budget as the visible answer**, so a naive low limit silently
returns empty output with no error. Inspecting the raw response showed
`finish_reason: "length"` with 198 of the 200 completion tokens spent on a
`reasoning` field that had actually worked out the fully correct answer —
there was just no budget left to emit it as the final JSON `content`.

Two changes fixed it for this run:
- Switched `call_openai` from the deprecated `max_tokens` request parameter
  to `max_completion_tokens` (Groq's documented recommendation for reasoning
  models).
- Raised the shared `--max-tokens` default from 200 to 600, applied
  identically across all three models per the bake-off's "no per-model
  tweaks" rule — this run's actual completion token usage topped out at 521,
  so 600 leaves headroom without being an arbitrarily large number picked
  just for this model.

If you see a wall of empty `raw_output` with no `error` on some other
reasoning model, this is the first thing to check.
