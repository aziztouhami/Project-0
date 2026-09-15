"""One-off script: build data/items.jsonl from f1_drivers_database.csv.

Run once, then commit data/items.jsonl. Do not re-run casually — the random
seed makes distractor selection deterministic, but the output is a frozen
fixture and should only be regenerated intentionally.
"""
import csv
import json
import random
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "f1_drivers_database.csv"
OUT_PATH = REPO_ROOT / "data" / "items.jsonl"

DISTRACTOR_SEED = 42
MIN_WORDS = 100
MAX_WORDS = 150


def era_for_debut_year(debut_year: int) -> str:
    if 1950 <= debut_year <= 1969:
        return "Golden Era"
    if 1970 <= debut_year <= 1989:
        return "Grand Prix Era"
    if 1990 <= debut_year <= 2006:
        return "Modern Era"
    if 2007 <= debut_year <= 2021:
        return "Turbo-Hybrid Era"
    if debut_year >= 2022:
        return "Current Era"
    raise ValueError(f"debut_year {debut_year} does not fall into a known era")


def pluralize(count_str: str, singular: str, plural: str) -> str:
    return singular if count_str == "1" else plural


def join_teams(teams_field: str) -> str:
    teams = [t.strip() for t in teams_field.split(",") if t.strip()]
    if len(teams) == 1:
        return teams[0]
    if len(teams) == 2:
        return f"{teams[0]} and {teams[1]}"
    return ", ".join(teams[:-1]) + f", and {teams[-1]}"


def build_bio(row: dict, distractor_row: dict) -> str:
    name = row["Driver Name"]
    nationality = row["Nationality"]
    debut_year = row["F1 Debut Year"]
    teams = join_teams(row["Teams (Career)"])
    notable_fact = row["Notable Fact"].strip()
    if not notable_fact.endswith((".", "!", "?")):
        notable_fact += "."
    race_wins = row["Race Wins"]
    starts = row["Grand Prix Starts"]
    career_points = row["Career Points"]
    career_span = row["Career Span"]
    podiums = row["Podiums"]
    poles = row["Pole Positions"]
    fastest_laps = row["Fastest Laps"]
    championships = row["World Championships"]

    distractor_name = distractor_row["Driver Name"]
    distractor_career_points = distractor_row["Career Points"]

    last_name = name.split()[-1]
    championships_clause = (
        f"has not yet won a World Championship"
        if championships == "0"
        else f"won {championships} World Championship"
        + ("s" if championships != "1" else "")
    )

    # "New Zealander" is a noun demonym (unlike "British", "Italian", etc.),
    # so it needs its own phrasing to avoid "a New Zealander driver".
    if nationality == "New Zealander":
        opening = f"{name} is a New Zealander who made his Formula 1 debut in "
    else:
        article = "an" if nationality[0] in "AEIOU" else "a"
        opening = (
            f"{name} is {article} {nationality} driver who made his Formula "
            f"1 debut in "
        )

    sentences = [
        opening
        + f"{debut_year}, going on to race for {teams} across a career "
        f"spanning {career_span}.",
        notable_fact,
        f"Across {starts} Grand Prix starts, {last_name} took "
        f"{race_wins} {pluralize(race_wins, 'race win', 'race wins')} and "
        f"scored {career_points} career championship points.",
        f"Over that span he also picked up {podiums} "
        f"{pluralize(podiums, 'podium finish', 'podium finishes')}, "
        f"{poles} {pluralize(poles, 'pole position', 'pole positions')}, "
        f"and {fastest_laps} "
        f"{pluralize(fastest_laps, 'fastest lap', 'fastest laps')}, and he "
        f"{championships_clause}.",
        f"He is often compared to {distractor_name}, whose career total "
        f"sits at {distractor_career_points} championship points.",
    ]

    padding_candidates = [
        f"His time in Formula 1 is remembered as part of a career that left "
        f"a lasting mark on the sport.",
        f"That record stands as one of the defining features of his time on "
        f"the grid.",
        f"Fans and historians of the sport still point to that stretch of "
        f"his career as a high point.",
    ]

    bio = " ".join(sentences)
    i = 0
    while len(bio.split()) < MIN_WORDS and i < len(padding_candidates):
        sentences.insert(-1, padding_candidates[i])
        bio = " ".join(sentences)
        i += 1

    word_count = len(bio.split())
    if not (MIN_WORDS <= word_count <= MAX_WORDS):
        raise ValueError(
            f"bio_text for {name} is {word_count} words (must be "
            f"{MIN_WORDS}-{MAX_WORDS})"
        )

    return bio


def main():
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if len(rows) != 50:
        raise ValueError(f"expected 50 driver rows, found {len(rows)}")

    items = []
    for idx, row in enumerate(rows):
        rng = random.Random(DISTRACTOR_SEED + idx)
        own_points = row["Career Points"]
        other_indices = [
            i
            for i in range(len(rows))
            if i != idx and rows[i]["Career Points"] != own_points
        ]
        distractor_idx = rng.choice(other_indices)
        distractor_row = rows[distractor_idx]

        debut_year = int(row["F1 Debut Year"])
        bio_text = build_bio(row, distractor_row)

        item = {
            "id": f"d{idx + 1:02d}",
            "driver": row["Driver Name"],
            "bio_text": bio_text,
            "expected": {
                "nationality": row["Nationality"],
                "debut_year": debut_year,
                "career_points": float(row["Career Points"]),
                "era": era_for_debut_year(debut_year),
                "win_percentage": round(float(row["Win Percentage"]), 1),
            },
        }
        items.append(item)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8", newline="\n") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Wrote {len(items)} items to {OUT_PATH}")


if __name__ == "__main__":
    main()
