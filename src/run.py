"""Run one model against all 50 items in data/items.jsonl and write a results CSV.

Same script, different --model/--provider args, run once per teammate/model.
This is what keeps the three runs comparable: identical prompt, identical
item order, identical temperature/max_tokens, one item at a time.

Usage:
    python src/run.py --model claude-opus-4 --provider anthropic \
        --items data/items.jsonl --prompt src/prompt.txt --out results/raw/top.csv
"""
import argparse
import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

TEMPERATURE = 0
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.5

FIELDNAMES = [
    "id",
    "driver",
    "model",
    "provider",
    "raw_output",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "tokens_per_second",
    "error",
    "timestamp_utc",
]


def load_items(path):
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def load_prompt(path):
    return Path(path).read_text(encoding="utf-8")


def render_prompt(template, bio_text):
    return template.replace("{{BIO_TEXT}}", bio_text)


def call_anthropic(prompt_text, model, max_tokens, base_url=None, api_key_env=None):
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=TEMPERATURE,
        messages=[{"role": "user", "content": prompt_text}],
    )
    raw_output = "".join(block.text for block in resp.content if block.type == "text")
    return raw_output, resp.usage.input_tokens, resp.usage.output_tokens, None


def call_openai(prompt_text, model, max_tokens, base_url=None, api_key_env=None):
    import openai

    client_kwargs = {"api_key": os.environ[api_key_env or "OPENAI_API_KEY"]}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = openai.OpenAI(**client_kwargs)
    resp = client.chat.completions.create(
        model=model,
        max_completion_tokens=max_tokens,
        temperature=TEMPERATURE,
        messages=[{"role": "user", "content": prompt_text}],
    )
    raw_output = resp.choices[0].message.content or ""
    return raw_output, resp.usage.prompt_tokens, resp.usage.completion_tokens, None


def call_google(prompt_text, model, max_tokens, base_url=None, api_key_env=None):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    resp = client.models.generate_content(
        model=model,
        contents=prompt_text,
        config=types.GenerateContentConfig(
            temperature=TEMPERATURE,
            max_output_tokens=max_tokens,
        ),
    )
    raw_output = resp.text or ""
    usage = resp.usage_metadata
    return raw_output, usage.prompt_token_count, usage.candidates_token_count, None


def call_ollama(prompt_text, model, max_tokens, base_url, api_key_env=None):
    import requests

    base_url = base_url or "http://localhost:11434"
    resp = requests.post(
        f"{base_url}/api/generate",
        json={
            "model": model,
            "prompt": prompt_text,
            "stream": False,
            "options": {"temperature": TEMPERATURE, "num_predict": max_tokens},
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()

    raw_output = data.get("response", "")
    prompt_tokens = data.get("prompt_eval_count")
    completion_tokens = data.get("eval_count")
    eval_duration_ns = data.get("eval_duration")

    tokens_per_second = None
    if completion_tokens and eval_duration_ns:
        tokens_per_second = completion_tokens / (eval_duration_ns / 1e9)

    return raw_output, prompt_tokens, completion_tokens, tokens_per_second


PROVIDERS = {
    "anthropic": call_anthropic,
    "openai": call_openai,
    "google": call_google,
    "ollama": call_ollama,
}


def get_status_code(exc):
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        return status_code
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) if response is not None else None


def is_retryable(exc):
    if get_status_code(exc) == 429:
        return True
    name = type(exc).__name__
    return "Timeout" in name or "Connection" in name


def run_one(item, prompt_text, args):
    call_fn = PROVIDERS[args.provider]
    attempt = 0

    while True:
        start = time.perf_counter()
        try:
            raw_output, prompt_tokens, completion_tokens, tps = call_fn(
                prompt_text, args.model, args.max_tokens, args.base_url, args.api_key_env
            )
            latency_ms = round((time.perf_counter() - start) * 1000, 1)
            return {
                "id": item["id"],
                "driver": item["driver"],
                "model": args.model,
                "provider": args.provider,
                "raw_output": raw_output,
                "latency_ms": latency_ms,
                "prompt_tokens": prompt_tokens if prompt_tokens is not None else "",
                "completion_tokens": completion_tokens if completion_tokens is not None else "",
                "tokens_per_second": round(tps, 2) if tps is not None else "",
                "error": "",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 1)
            if is_retryable(exc) and attempt < MAX_RETRIES:
                attempt += 1
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue

            if "Timeout" in type(exc).__name__:
                error_msg = "timeout"
            elif get_status_code(exc) == 429:
                error_msg = f"rate_limited (429) after retries: {exc}"
            else:
                error_msg = f"api_error: {exc}"
            return {
                "id": item["id"],
                "driver": item["driver"],
                "model": args.model,
                "provider": args.provider,
                "raw_output": "",
                "latency_ms": latency_ms,
                "prompt_tokens": "",
                "completion_tokens": "",
                "tokens_per_second": "",
                "error": error_msg,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--provider", required=True, choices=list(PROVIDERS))
    parser.add_argument("--items", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-tokens", type=int, default=600)
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override the provider's API endpoint (e.g. an OpenAI-compatible "
        "endpoint like Groq's for --provider openai). Defaults to "
        "http://localhost:11434 for ollama and each SDK's own default otherwise.",
    )
    parser.add_argument(
        "--api-key-env",
        default=None,
        help="Environment variable holding the API key (default: "
        "ANTHROPIC_API_KEY / OPENAI_API_KEY / GOOGLE_API_KEY depending on "
        "--provider). Not used for ollama.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N items -- for smoke-testing a provider, "
        "not for real bake-off runs (those must use all 50).",
    )
    args = parser.parse_args()

    items = load_items(args.items)
    if args.limit is not None:
        items = items[: args.limit]
    prompt_template = load_prompt(args.prompt)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

        for i, item in enumerate(items, start=1):
            prompt_text = render_prompt(prompt_template, item["bio_text"])
            row = run_one(item, prompt_text, args)
            writer.writerow(row)
            f.flush()

            status = f"error: {row['error']}" if row["error"] else "ok"
            print(f"{i}/{len(items)} done, {row['latency_ms']}ms ({status})")


if __name__ == "__main__":
    main()
