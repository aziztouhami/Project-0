# Cheap model metrics — openai/gpt-oss-20b (via Groq)

Real 50-item run. `--provider openai`, `--base-url https://api.groq.com/openai/v1`,
`--api-key-env GROQ_API_KEY`, `--max-tokens 900`, temperature 0, same
`src/prompt.txt` and `data/items.jsonl` order used for every model.

The prompt now asks for 6 fields, not 5: `podium_percentage` was added
alongside `win_percentage`. Like win percentage, it is never stated as a
percentage anywhere in the bio text — only the raw podium count and Grand
Prix starts are given — so the model has to derive it from the same two
numbers used to compute the ground truth, not copy a number out of the text.

## Accuracy

**49/50 correct (98.0%)**

One genuine miss:

| id | driver | got | expected | other 5 fields |
|---|---|---|---|---|
| d03 | Max Verstappen | `era: "Modern Era"` | `era: "Turbo-Hybrid Era"` | all correct, including podium_percentage |

Verstappen debuted in 2015 — squarely inside the 2007-2021 Turbo-Hybrid Era
range given in the prompt, not a boundary year. Same failure mode seen on
the 5-field run: the model gets `debut_year` right but misapplies its own
stated era rule. Not a parsing or attribution failure.

## Latency

- p50: 5048ms
- p95: 8792ms

## Cost (Groq pricing used: $0.10 / 1M input tokens, $0.50 / 1M output tokens)

- Cost per 1k requests: **$0.26**
- Cost per 1k requests at 100x traffic: **$26.44** (same unit cost, just more of them)

## Two findings from adding this field (both worth keeping)

### 1. max_tokens needed recalibrating again: 600 → 900

The 5-field run had settled on `--max-tokens 600` with headroom to spare
(max usage 521/600). Re-running the exact same setup with the 6-field prompt
produced 2/50 rows that hit the 600 cap and came back truncated
(`finish_reason: "length"`, unparsable partial JSON) — confirming the
earlier finding still applies: **gpt-oss-20b's hidden reasoning tokens share
the same output-token budget as the visible answer**, and that budget isn't
fixed per item — it varies enough per driver that adding one more field to
extract was enough to push a couple of items over a limit that previously
had 15%+ headroom to spare.

Fix: raised the shared `--max-tokens` default to 900 (verified first against
just the two previously-truncated items, which needed 564 and 639 tokens —
before re-running the full 50-item set once, uniformly, not per-item). Final
run's max usage was 654/900. Whatever model runs next under this prompt
should start from 900, not 600.

### 2. A scoring bug, not a model error: floating-point tolerance boundary

The first full run under the 6-field prompt scored 47/50, with 2 of the 3
misses reported as `podium_percentage` mismatches — both exactly 0.1 away
from the expected value (24.1 vs 24.0, 24.9 vs 25.0). `score.py`'s tolerance
check was `abs(a - b) > 0.1` on raw Python floats: since 24.1 cannot be
represented exactly in binary floating point, `abs(24.1 - 24.0)` evaluates
to `0.10000000000000142`, not `0.1` — just over the tolerance, purely as a
float-representation artifact, not a real 0.1+ discrepancy.

Fixed in `src/score.py` by rounding the diff to 6 decimal places before
comparing (`exceeds_tolerance()`), applied to all three tolerance-based
fields (career_points, win_percentage, podium_percentage) for consistency.
Re-scoring the same raw output with the fix: 47/50 → 49/50 — both boundary
cases were correct all along.
