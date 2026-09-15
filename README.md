# F1 Driver Facts Bake-Off

Compares three LLMs (one top-tier API model, one cheap API model, one
open-weights model run locally via Ollama) on the same 50-item extraction
task, under identical conditions: same prompt, same item order, temperature 0,
same max output tokens.

## Project layout

- `f1_drivers_database.csv` — source data, 50 real F1 drivers.
- `src/build_items.py` — one-off script that built `data/items.jsonl` from the
  CSV. Already run; `data/items.jsonl` is a frozen fixture and should not be
  regenerated casually.
- `data/items.jsonl` — the frozen 50-item task set, one JSON object per line.
- `src/prompt.txt` — the frozen prompt template, used verbatim for every item
  and every model. `{{BIO_TEXT}}` is substituted per item.
- `src/run.py` — runs one model against all 50 items and writes a results CSV.
  Reused unchanged across all three models — only the CLI args differ.
- `results/raw/` — output CSVs, one per model.

## Setup

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in whichever API keys you need
(`.env` is gitignored — never commit real keys):

```
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
GROQ_API_KEY=...
```

Ollama needs no API key, but it must be running locally
(`ollama serve`, default `http://localhost:11434`) with the target model
already pulled (`ollama pull llama3.2:3b`).

Any OpenAI-compatible endpoint (e.g. Groq) can be used with `--provider openai`
by overriding `--base-url` and `--api-key-env` (see below) — no separate
provider code is needed.

## Running each model

Run these one at a time — `src/run.py` calls the model sequentially, one item
after another, so latency numbers are honest.

```bash
# Top-tier API model
python src/run.py --model claude-opus-4 --provider anthropic \
    --items data/items.jsonl --prompt src/prompt.txt --out results/raw/top.csv

# Cheap API model
python src/run.py --model claude-haiku-4-5 --provider anthropic \
    --items data/items.jsonl --prompt src/prompt.txt --out results/raw/cheap.csv

# Open-weights model via Ollama
python src/run.py --model llama3.2:3b --provider ollama \
    --items data/items.jsonl --prompt src/prompt.txt --out results/raw/open.csv

# Cheap model via Groq's OpenAI-compatible endpoint
python src/run.py --model openai/gpt-oss-20b --provider openai \
    --base-url https://api.groq.com/openai/v1 --api-key-env GROQ_API_KEY \
    --items data/items.jsonl --prompt src/prompt.txt --out results/raw/cheap.csv
```

Swap `--provider` / `--model` for `openai` or `google` models as needed — the
same script handles all four provider types. `--max-tokens` defaults to 600;
pass `--max-tokens N` to override (keep it identical across all three runs).

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
