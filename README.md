# SMC Estimator

A single-file, zero-dependency web tool that estimates when a New Zealand
Skilled Migrant Category (SMC) residence application is likely to get a
decision, for Chinese-national applicants. It combines a queueing model
with a Monte Carlo simulation over Immigration New Zealand's public
monthly statistics — no build step, no framework, just `index.html`.

**Live site:** published via GitHub Pages from this repo's `main` branch.

## Layout

```
index.html        the tool — open directly in a browser, or via GitHub Pages
data/
  CN/              R1 (decisions) / R7 (accepted) / R8 (on hand), China-filtered
  README.md        download steps + a data-quality pitfall worth reading
scripts/
  smc_model_v2.py    the estimation model (queueing + Markov-chain capacity)
  build_web_data.py  monthly update entry point — writes computed params
                      back into index.html, no numbers ever hand-typed
```

## Monthly data refresh

```
1. Download fresh R1/R7/R8 CSVs from Immigration NZ (filtered to China), into data/CN/
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
