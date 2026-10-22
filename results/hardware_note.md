# Hardware note — local model run (phi4-mini via Ollama)

## Machine

- **CPU**: Intel Core i7-10750H @ 2.60GHz, 6 cores / 12 logical processors
- **RAM**: 11.8 GB
- **GPU**: Intel UHD Graphics (integrated only — no discrete GPU, no CUDA/ROCm
  acceleration available to Ollama)
- **OS**: Windows 11 Professional, build 10.0.26200
- **Inference engine**: Ollama (local server, `http://localhost:11434`), CPU-only

This is a mid-range 2020-era laptop, not dedicated inference hardware. All 50
requests for the local model ran on CPU; there was no GPU offload.

## Why this constrained the model choice

Three open-weights models were already pulled in Ollama on this machine
(`ollama list`): `gemma4:12b` (7.6 GB), `qwen3:8b` (5.2 GB), and
`phi4-mini:latest` (2.5 GB). With only 11.8 GB of RAM and no GPU, the two
larger models were tested briefly:

- `qwen3:8b` took over 180 seconds for a single item (test stopped before
  completion) — at that rate a 50-item run would take multiple hours, with
  real risk of thermal throttling or a stalled run.
- `phi4-mini` completed single items in 10-38 seconds, making a full 50-item
  run tractable in well under 20 minutes.

`gemma4:12b` was not run at all given the above — at roughly 1.5x the
parameter count of `qwen3:8b` on the same CPU-only hardware, it was expected
to be at least as slow, and the RAM headroom (7.6 GB model + context, against
11.8 GB total, with the OS and other processes also resident) left little
margin before swapping.

`phi4-mini` was chosen as the only one of the three that could realistically
complete a full, honest 50-item run on this machine in reasonable time.

## What this means for the results

The local model's latency and throughput numbers in `results/summary.csv`
(p50 13,224ms, p95 25,070ms, 7.84 tokens/sec) reflect this specific
CPU-only, no-GPU laptop — not a representative "typical" local-inference
rig. A machine with a GPU (or even a newer CPU with better single-thread
performance and more memory bandwidth) would very plausibly run the same
model many times faster. Any cost-per-request or latency conclusion drawn
for the local leg is a statement about *this machine running phi4-mini*,
not about local inference in general.

## Cost assumptions used for the local model (see main report, Section E)

- Hardware: estimated retail price for a comparable i7-10750H laptop, **$1200**,
  amortized over a **3-year** useful life at an assumed **8 hours/day** of
  use (3 × 365 × 8 = 8,760 hours) → **$0.137/hour** amortized hardware cost.
- Electricity: assumed **70W** average system draw under sustained CPU
  inference load, at an assumed **$0.15/kWh** (a representative, not
  location-specific, residential rate) → **$0.0105/hour**.
- Combined **hardware cost per hour ≈ $0.15/hour**, the figure passed to
  `src/cost.py --mode local --hardware-cost-per-hour 0.15`.
- These are stated estimates, not measured values (no watt-meter was used,
  and the laptop's actual purchase price/age is not on record) — treat the
  resulting local cost-per-request as order-of-magnitude, not precise.
