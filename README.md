# SMC Estimator

A single-file, zero-dependency web tool that estimates when a New Zealand
Skilled Migrant Category (SMC) residence application is likely to get a
decision, for Chinese-national applicants. It combines a queueing model
with a Monte Carlo simulation over Immigration New Zealand's public
monthly statistics — no build step, no framework, just `index.html`.

**Live site:** [houstonfrog.github.io/smc-estimator](https://houstonfrog.github.io/smc-estimator/), published from this repo's `main` branch.

## Current version

Data covers **September 2026**. The latest SMC counts are 792 accepted,
84 decided (78 approved and 6 declined), and 2,010 on hand.

- Six months of actual accepted/decided counts and month-end on-hand counts
  appear directly after the estimate, before the model explanation.
- Future acceptance is assumed to return toward the February–July 2026
  mean of 201. The excess over that level halves every 3 months by default;
  the tool allows 1–12 months. This is a scenario assumption, not an
  established post-policy trend.
- The September low-capacity state can continue and recover. Normal-month
  capacity is estimated at 240; the September actual of 84 is not treated
  as permanent. Recovery duration uses completed historical episodes,
  excluding the still-unfinished September episode.

All three reports select `SMC Skilled Residence`. The CSVs do not retain
nationality or principal/secondary-applicant filter settings. The data
passes structural and historical consistency checks, but September's
stock-flow reconciliation still has an unexplained difference of 126.
See the [data validation report](data/validation_2026-09.md) for evidence,
source hashes, scope limitations, and assumptions.

## Layout

```
index.html        the tool — open directly in a browser, or via GitHub Pages
data/
  CN/              R1 (decisions) / R7 (accepted) / R8 (on hand), China-filtered
  README.md        download steps + a data-quality pitfall worth reading
  validation_2026-09.md  the September data audit and model assumptions
scripts/
  smc_model_v2.py    the estimation model (queueing + Markov-chain capacity)
  build_web_data.py  monthly update entry point — writes computed params
                      back into index.html, no numbers ever hand-typed
  test_smc_data.py   data validation and scenario regression checks
  test_web_model.js  executes the web model, chart rendering and event checks
```

## Monthly data refresh

```
1. Download the R1/R7/R8 Application Substream CSVs (filtered to China,
   with matching Applicant Type filters), into data/CN/
2. cd scripts && python3 build_web_data.py
3. Open index.html, confirm the "updated to" date changed
4. Commit and push
```

`build_web_data.py` re-derives every parameter from the raw CSVs (via
`smc_model_v2.py`'s `estimate()`/`pitvals()`) and runs self-checks before
writing anything — it aborts rather than publish a partial or
implausible dataset (missing months, a >3x month-over-month jump, a
non-monotonic calibration map, or fewer months than last time).

## Requirements to run the pipeline

Python 3.9+ with `pandas` and `numpy`. The tool itself (`index.html`)
has no dependencies at all.

Regression checks, from the repository root (Node.js 18+ for the web check):

```sh
python3 -m unittest discover -s scripts -p 'test_*.py'
node scripts/test_web_model.js
```
