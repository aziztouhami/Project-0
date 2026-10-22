"""Build results/per_item.csv and results/summary.csv from the real run files.

One-off reporting script for this project's two models: the cheap API model
(results/raw/cheap.csv) and the local open-weights model (results/raw/open.csv).
Reuses score.py's load_items()/field_mismatches() as the single source of
truth for correctness -- this script does not re-derive scoring rules, only
reports on them and adds a per-item status classification.

status classification (ok / parse_error / refusal / timeout / api_error):
- timeout: run.py's error column contains "timeout"
- api_error: run.py's error column is non-empty and isn't a timeout (a
  connection/HTTP failure after retries). Not one of the four buckets named
  in the brief, kept only as a safety net -- both real runs in this project
  have zero rows here.
- ok: no run.py-level error, and raw_output parses as a JSON object
  (regardless of whether the extracted fields are correct -- field
  correctness is a separate column, not part of this status)
- refusal: no run.py-level error, raw_output does not parse as JSON, and
  either raw_output is empty or it contains natural-language refusal
  phrasing (see REFUSAL_MARKERS)
- parse_error: no run.py-level error, raw_output does not parse as JSON, and
  it isn't a refusal -- e.g. markdown-fenced JSON, truncated JSON, JSON with
  extra prose around it
"""
import csv
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import field_mismatches, load_items

REPO_ROOT = Path(__file__).resolve().parent.parent
ITEMS_PATH = REPO_ROOT / "data" / "items.jsonl"

MODELS = [
    {"model_id": "openai/gpt-oss-20b", "raw": REPO_ROOT / "results/raw/cheap.csv"},
    {"model_id": "phi4-mini", "raw": REPO_ROOT / "results/raw/open.csv"},
]

FIELDS = [
    "nationality",
    "debut_year",
    "career_points",
    "era",
    "win_percentage",
    "podium_percentage",
]

REFUSAL_MARKERS = [
    "i cannot",
    "i can't",
    "i'm sorry",
    "i am sorry",
    "as an ai",
    "unable to provide",
    "i do not have access",
    "i don't have access",
    "i won't",
    "i will not",
]


def try_parse(raw_output):
    try:
        parsed = json.loads(raw_output)
    except (json.JSONDecodeError, TypeError):
        return None, False
    if not isinstance(parsed, dict):
        return None, False
    return parsed, True


def classify_status(error, raw_output, parsed_ok):
    if error:
        return "timeout" if "timeout" in error.lower() else "api_error"
    if parsed_ok:
        return "ok"
    text = (raw_output or "").strip().lower()
    if not text or any(marker in text for marker in REFUSAL_MARKERS):
        return "refusal"
    return "parse_error"


def percentiles(values):
    if not values:
        return "", ""
    sorted_vals = sorted(values)
    if len(sorted_vals) < 2:
        return round(sorted_vals[0], 1), round(sorted_vals[0], 1)
    qs = statistics.quantiles(sorted_vals, n=100, method="inclusive")
    return round(qs[49], 1), round(qs[94], 1)


def mean_or_blank(values):
    return round(statistics.mean(values), 2) if values else ""


def main():
    items = load_items(ITEMS_PATH)
    per_item_rows = []
    summary_rows = []

    for spec in MODELS:
        with spec["raw"].open(newline="", encoding="utf-8") as f:
            raw_rows = list(csv.DictReader(f))

        field_correct_counts = {field: 0 for field in FIELDS}
        status_counts = {"ok": 0, "parse_error": 0, "refusal": 0, "timeout": 0, "api_error": 0}
        overall_correct = 0
        latencies, tokens_in, tokens_out, tps_values = [], [], [], []

        for row in raw_rows:
            expected = items[row["id"]]["expected"]
            error = (row.get("error") or "").strip()
            raw_output = row.get("raw_output") or ""
            parsed, parsed_ok = (None, False) if error else try_parse(raw_output)

            status = classify_status(error, raw_output, parsed_ok)
            status_counts[status] += 1

            mismatches = field_mismatches(parsed, expected) if parsed_ok else list(FIELDS)
            is_correct = parsed_ok and not mismatches
            if is_correct:
                overall_correct += 1
            for field in FIELDS:
                if parsed_ok and field not in mismatches:
                    field_correct_counts[field] += 1

            out_row = {"id": row["id"], "model": spec["model_id"]}
            for field in FIELDS:
                out_row[f"{field}_expected"] = expected[field]
                out_row[f"{field}_predicted"] = (parsed or {}).get(field) if parsed_ok else ""
            out_row["correct"] = is_correct
            out_row["status"] = status
            out_row["latency_ms"] = row.get("latency_ms", "")
            out_row["tokens_in"] = row.get("prompt_tokens", "")
            out_row["tokens_out"] = row.get("completion_tokens", "")
            per_item_rows.append(out_row)

            if row.get("latency_ms"):
                latencies.append(float(row["latency_ms"]))
            if row.get("prompt_tokens"):
                tokens_in.append(float(row["prompt_tokens"]))
            if row.get("completion_tokens"):
                tokens_out.append(float(row["completion_tokens"]))
            if row.get("tokens_per_second"):
                tps_values.append(float(row["tokens_per_second"]))

        p50, p95 = percentiles(latencies)
        summary_row = {
            "model": spec["model_id"],
            "n_items": len(raw_rows),
            "correct": overall_correct,
            "accuracy_pct": round(overall_correct / len(raw_rows) * 100, 1),
            "status_ok": status_counts["ok"],
            "status_parse_error": status_counts["parse_error"],
            "status_refusal": status_counts["refusal"],
            "status_timeout": status_counts["timeout"],
            "status_api_error": status_counts["api_error"],
            "latency_p50_ms": p50,
            "latency_p95_ms": p95,
            "mean_tokens_in": mean_or_blank(tokens_in),
            "mean_tokens_out": mean_or_blank(tokens_out),
            "mean_tokens_per_second": mean_or_blank(tps_values),
        }
        for field in FIELDS:
            summary_row[f"{field}_correct_of_50"] = field_correct_counts[field]
        summary_rows.append(summary_row)

    per_item_fieldnames = ["id", "model"]
    for field in FIELDS:
        per_item_fieldnames += [f"{field}_expected", f"{field}_predicted"]
    per_item_fieldnames += ["correct", "status", "latency_ms", "tokens_in", "tokens_out"]

    out_per_item = REPO_ROOT / "results" / "per_item.csv"
    with out_per_item.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=per_item_fieldnames)
        writer.writeheader()
        writer.writerows(per_item_rows)

    out_summary = REPO_ROOT / "results" / "summary.csv"
    with out_summary.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"Wrote {len(per_item_rows)} rows to {out_per_item}")
    print(f"Wrote {len(summary_rows)} rows to {out_summary}")


if __name__ == "__main__":
    main()
