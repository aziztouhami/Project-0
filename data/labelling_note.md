# Labelling note

## Source of the data

The 50 driver records come from `f1_drivers_database.csv`, a hand-compiled
table of real Formula 1 drivers and their career statistics (nationality,
debut year, teams, wins, podiums, poles, points, etc.). The figures in that
CSV trace back to publicly available F1 statistics, primarily Wikipedia
driver pages and the sport's official records.

## How the task items were generated

`src/build_items.py` reads that CSV and produces `data/items.jsonl`
mechanically — there is no manual labelling step. For each driver it:

- Assembles a 100-150 word biography paragraph from the CSV fields
  (nationality, debut year, teams, notable fact, wins, starts, points,
  podiums, poles, fastest laps, championships).
- Appends one distractor sentence naming a different, randomly chosen driver
  and *that* driver's real career points total (e.g. "He is often compared
  to Stirling Moss, whose career total sits at 186.64 championship points.").
  This is deliberate: it's the same field the model is asked to extract for
  the subject driver, so getting it right requires correctly attributing the
  number to the right person instead of grabbing the first number that looks
  like career points.
- Computes `expected.era` from `debut_year` using the five fixed date ranges
  also given to the model in the prompt, and copies `expected.nationality`,
  `expected.debut_year`, `expected.career_points`, `expected.win_percentage`,
  and `expected.podium_percentage` directly from the corresponding CSV columns
  (win/podium percentage rounded to 1 decimal place). Neither percentage is
  ever stated as a percentage in the bio text itself — only the raw counts
  (wins, podiums, Grand Prix starts) are — so the model has to derive both
  from the same two raw numbers used to compute the ground truth, not just
  copy a number out of the text.

The distractor driver is chosen with `random.Random(42 + row_index)`, so
regenerating the file produces byte-identical output — the dataset is a
frozen fixture, not something recomputed per run.

## How correctness was checked

After generating the file, the following was verified programmatically
before committing:

- Exactly 50 items, ids `d01`-`d50` in order, 50 distinct driver names.
- Every `expected` field matches the source CSV row exactly (nationality,
  debut year, career points, win percentage, podium percentage) and `era` is
  always one of the five valid labels.
- Every bio's word count falls within the required 100-150 word range.
- The driver's own name appears in their bio, and the driver's own last name
  never appears in the distractor clause (no accidental self-reference).
- The distractor sentence always cites "championship points" (the field
  actually being tested), never a field the model isn't asked about.
- The distractor's career-points figure is never numerically equal to the
  subject driver's own career points — this happened once by coincidence
  (Alan Jones and Ronnie Peterson both sit at 206.0 points) and was excluded
  at generation time so the attribution trap can't be defeated by chance.

No entries were hand-edited after generation; any future change to the data
goes through `build_items.py` and gets re-validated the same way.
