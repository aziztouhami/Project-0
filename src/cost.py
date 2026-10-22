"""Cost and latency report for one results/raw/<name>.csv (from run.py).

Two modes:

  API mode -- cost is driven by token usage and the provider's published
  per-token prices:
      python src/cost.py --raw results/raw/cheap.csv --mode api \
          --price-in 0.10 --price-out 0.50

  Local mode -- cost is driven by wall-clock latency and the hourly cost of
  the machine running the model:
      python src/cost.py --raw results/raw/open.csv --mode local \
          --hardware-cost-per-hour 0.50

This script only reads the raw run.py output, so it has no access to
data/items.jsonl and therefore cannot report accuracy -- that's score.py's
job. Run both and combine their output for a full per-model report.
"""
import argparse
import csv
import statistics
from pathlib import Path

REQUESTS_PER_HOUR_SECONDS = 3600


def load_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def percentiles(latencies_ms):
    """p50 and p95, via statistics.quantiles (linear interpolation, inclusive)."""
    sorted_latencies = sorted(latencies_ms)
    cut_points = statistics.quantiles(sorted_latencies, n=100, method="inclusive")
    return cut_points[49], cut_points[94]


def report_api(rows, price_in_per_1m, price_out_per_1m):
    total_prompt_tokens = sum(to_float(r.get("prompt_tokens")) for r in rows)
    total_completion_tokens = sum(to_float(r.get("completion_tokens")) for r in rows)

    total_cost = (
        total_prompt_tokens / 1_000_000 * price_in_per_1m
        + total_completion_tokens / 1_000_000 * price_out_per_1m
    )
    cost_per_request = total_cost / len(rows)
    cost_per_1k = cost_per_request * 1000
    cost_per_1k_at_100x = cost_per_1k * 100

    lines = [
        f"Cost per 1k requests: ${cost_per_1k:.2f}",
        f"Cost per 1k requests at 100x traffic: ${cost_per_1k_at_100x:.2f} "
        f"(same unit cost, just more of them)",
    ]
    return lines


def report_local(rows, hardware_cost_per_hour):
    avg_latency_seconds = statistics.mean(to_float(r.get("latency_ms")) for r in rows) / 1000
    requests_per_hour = REQUESTS_PER_HOUR_SECONDS / avg_latency_seconds
    cost_per_1k = (hardware_cost_per_hour / requests_per_hour) * 1000

    return [f"Cost per 1k requests: ${cost_per_1k:.2f}"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True)
    parser.add_argument("--mode", required=True, choices=["api", "local"])
    parser.add_argument("--price-in", type=float, help="dollars per 1M input tokens (api mode)")
    parser.add_argument("--price-out", type=float, help="dollars per 1M output tokens (api mode)")
    parser.add_argument(
        "--hardware-cost-per-hour", type=float, help="dollars per hour (local mode)"
    )
    args = parser.parse_args()

    if args.mode == "api" and (args.price_in is None or args.price_out is None):
        parser.error("--mode api requires --price-in and --price-out")
    if args.mode == "local" and args.hardware_cost_per_hour is None:
        parser.error("--mode local requires --hardware-cost-per-hour")

    rows = load_rows(args.raw)
    if not rows:
        raise ValueError(f"no rows found in {args.raw}")

    latencies_ms = [to_float(r.get("latency_ms")) for r in rows]
    p50, p95 = percentiles(latencies_ms)

    if args.mode == "api":
        cost_lines = report_api(rows, args.price_in, args.price_out)
    else:
        cost_lines = report_local(rows, args.hardware_cost_per_hour)

    model = rows[0].get("model", "")

    print(f"Model: {model}")
    print(f"Latency p50: {p50:.0f}ms   p95: {p95:.0f}ms")
    for line in cost_lines:
        print(line)


if __name__ == "__main__":
    main()
