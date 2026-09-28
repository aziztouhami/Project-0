"""Score a results/raw/<name>.csv (from run.py) against data/items.jsonl.

No leniency beyond what's specified below: malformed JSON is a parse_error,
not something we clean up and retry. A model's raw output is graded as-is.

Usage:
    python src/score.py --raw results/raw/top.csv --items data/items.jsonl \
        --out results/scored/top_scored.csv
"""
import argparse
import csv
import json
from pathlib import Path

CAREER_POINTS_TOLERANCE = 0.5
WIN_PERCENTAGE_TOLERANCE = 0.1
PODIUM_PERCENTAGE_TOLERANCE = 0.1

SCORED_FIELDNAMES = [
    "id",
    "driver",
    "correct",
    "fail_reason",
    "latency_ms",
    "raw_output",
    "expected_json",
]


def load_items(path):
    items = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                item = json.loads(line)
                items[item["id"]] = item
    return items


def exceeds_tolerance(actual, expected_value, tolerance):
    """abs(a - b) with float noise rounded away, so an exact-boundary
    difference (e.g. 24.1 vs 24.0) isn't misjudged just because 24.1 can't be
    represented exactly in binary floating point."""
    diff = round(abs(float(actual) - float(expected_value)), 6)
    return diff > tolerance


def field_mismatches(parsed, expected):
    mismatches = []

    nationality = parsed.get("nationality")
    if not (
        isinstance(nationality, str)
        and nationality.strip().lower() == expected["nationality"].strip().lower()
    ):
        mismatches.append("nationality")

    try:
        if int(parsed.get("debut_year")) != int(expected["debut_year"]):
            mismatches.append("debut_year")
    except (TypeError, ValueError):
        mismatches.append("debut_year")

    try:
        if exceeds_tolerance(
            parsed.get("career_points"), expected["career_points"], CAREER_POINTS_TOLERANCE
        ):
            mismatches.append("career_points")
    except (TypeError, ValueError):
        mismatches.append("career_points")

    era = parsed.get("era")
    if not (
        isinstance(era, str) and era.strip().lower() == expected["era"].strip().lower()
    ):
        mismatches.append("era")

    try:
        if exceeds_tolerance(
            parsed.get("win_percentage"), expected["win_percentage"], WIN_PERCENTAGE_TOLERANCE
        ):
            mismatches.append("win_percentage")
    except (TypeError, ValueError):
        mismatches.append("win_percentage")

    try:
        if exceeds_tolerance(
            parsed.get("podium_percentage"),
            expected["podium_percentage"],
            PODIUM_PERCENTAGE_TOLERANCE,
        ):
            mismatches.append("podium_percentage")
    except (TypeError, ValueError):
        mismatches.append("podium_percentage")

    return mismatches


def score_row(row, expected):
    """Return (correct: bool, fail_reason: str)."""
    error = (row.get("error") or "").strip()
    raw_output = row.get("raw_output") or ""

    if error:
        return False, f"error: {error}"
    if not raw_output:
        return False, "error: empty raw_output"

    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        return False, "parse_error"

    if not isinstance(parsed, dict):
        return False, "parse_error"

    mismatches = field_mismatches(parsed, expected)
    if mismatches:
        return False, f"field_mismatch: {', '.join(mismatches)}"

    return True, ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True)
    parser.add_argument("--items", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    items = load_items(args.items)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    correct_count = 0

    with open(args.raw, newline="", encoding="utf-8") as f_in, out_path.open(
        "w", newline="", encoding="utf-8"
    ) as f_out:
        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(f_out, fieldnames=SCORED_FIELDNAMES)
        writer.writeheader()

        for row in reader:
            total += 1
            item_id = row["id"]
            item = items.get(item_id)
            if item is None:
                raise ValueError(f"id {item_id!r} from {args.raw} not found in {args.items}")

            correct, fail_reason = score_row(row, item["expected"])
            if correct:
                correct_count += 1

            writer.writerow(
                {
                    "id": item_id,
                    "driver": row.get("driver", item["driver"]),
                    "correct": correct,
                    "fail_reason": fail_reason,
                    "latency_ms": row.get("latency_ms", ""),
                    "raw_output": row.get("raw_output", ""),
                    "expected_json": json.dumps(item["expected"]),
                }
            )

    pct = (correct_count / total * 100) if total else 0.0
    print(f"{correct_count}/{total} correct ({pct:.1f}%)")


if __name__ == "__main__":
    main()
