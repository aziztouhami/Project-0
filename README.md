# F1 Driver Facts Bake-Off

Compares two LLMs (one cheap API model, one open-weights model run locally
via Ollama) on the same 50-item extraction task, under identical conditions:
same prompt, same item order, temperature 0, same max output tokens.

A top-tier API model was originally part of this comparison's scope but has
been dropped — this is now a two-model bake-off.

## Project layout

- `f1_drivers_database.csv` — source data, 50 real F1 drivers.
- `src/build_items.py` — one-off script that built `data/items.jsonl` from the
  CSV. Already run; `data/items.jsonl` is a frozen fixture and should not be
  regenerated casually.
- `data/items.jsonl` — the frozen 50-item task set, one JSON object per line.
- `src/prompt.txt` — the frozen prompt template, used verbatim for every item
  and every model. `{{BIO_TEXT}}` is substituted per item.
- `src/run.py` — runs one model against all 50 items and writes a results CSV.
  Reused unchanged across both models — only the CLI args differ.
- `src/score.py` — scores a raw results CSV against `data/items.jsonl`.
- `src/cost.py` — latency percentiles and cost-per-1k-requests from a raw
  results CSV (API token pricing or local hardware-hour pricing).
- `src/build_reports.py` — consolidates both models' raw/scored results into
  `results/per_item.csv` and `results/summary.csv`.
- `results/raw/` — one CSV per model, straight from `run.py`.
- `results/scored/` — one CSV per model, straight from `score.py`.
- `results/per_item.csv`, `results/summary.csv` — both models side by side.
- `results/hardware_note.md` — the machine the local model ran on, and why.
- `report.pdf` — the full write-up (task, data, setup, results, choice, cost).

## Setup (run once)

```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # Windows: copy .env.example .env — then fill in GROQ_API_KEY
```

`.env` is gitignored — never commit real keys. Ollama needs no API key, but
it must be running locally (`ollama serve`, default `http://localhost:11434`)
with the target model already pulled (`ollama pull phi4-mini`).

Any OpenAI-compatible endpoint (e.g. Groq) can be used with `--provider openai`
by overriding `--base-url` and `--api-key-env` (see below) — no separate
provider code is needed.

## Run (both models)

`src/run.py` calls the model sequentially, one item after another, so latency
numbers are honest. Run both lines, one at a time:

```bash
python src/run.py --model openai/gpt-oss-20b --provider openai --base-url https://api.groq.com/openai/v1 --api-key-env GROQ_API_KEY --items data/items.jsonl --prompt src/prompt.txt --out results/raw/cheap.csv
python src/run.py --model phi4-mini --provider ollama --items data/items.jsonl --prompt src/prompt.txt --out results/raw/open.csv
```

Swap `--provider` / `--model` for `openai` or `google` models as needed — the
same script handles all four provider types. `--max-tokens` defaults to 900
(reasoning models spend part of this budget on hidden reasoning tokens
before the visible answer, so this has needed raising twice as the prompt
grew — see `results/metrics/cheap_metrics.md`); pass `--max-tokens N` to
override (keep it identical across both runs).

`--base-url` overrides a provider's default API endpoint (used for Ollama's
local server, or to point `--provider openai` at any OpenAI-compatible API
such as Groq's). `--api-key-env` overrides which environment variable holds
the key (default: `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY`
depending on `--provider`; unused for ollama). `--limit N` processes only the
first N items — for smoke-testing a new provider/model before committing to a
full run; never use it for the real 50-item bake-off runs.

Each run writes exactly 50 rows to its output CSV, even if some calls fail
(a failed call gets `raw_output=""` and a filled-in `error` column — it is not
retried for malformed output, only for connection/timeout errors and HTTP 429
rate limits, and counts as a wrong answer during grading).

## Rules this project follows

- No per-model prompt tweaks, no per-model temperature/token differences.
- No hand-fixing model output, no retrying because output looked wrong.
- No hardcoded API keys anywhere in the repo.

## Results

| Model | Correct | Parse errors | p50 | p95 | Cost per 1k |
|---|---|---|---|---|---|
| openai/gpt-oss-20b (Groq) | 49/50 | 0 | 5,048 ms | 8,792 ms | $0.26 |
| phi4-mini (local, Ollama) | 0/50 | 50 | 13,224 ms | 25,070 ms | $0.61 + time |

phi4-mini's 0/50 is a format-compliance failure, not a reasoning failure: it
wraps every response in a ```` ```json ... ``` ```` code fence, which the
prompt explicitly forbids, so the strict parser (no repair, no retries)
correctly rejects all 50. It also never computes `win_percentage` or
`podium_percentage` (always `null`), so it would still score 0/50 even with
the fences stripped. Full breakdown, cost assumptions, and the choice we'd
make and why: see `report.pdf`.

## Contributions

Mohamed Aziz Touhami, Tarak Ben Sedrine, Ilyes Fatnassi, Farah Marnissi
