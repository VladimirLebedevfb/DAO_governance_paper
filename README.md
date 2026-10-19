# DAO governance: data and analysis pipeline

Empirical pipeline for the paper on DAO governance design and economic outcomes.

| Part | What it does | Entry point |
|---|---|---|
| New pipeline | Collects fresh data from Tally (Cactus) and CryptoCompare, builds the sample and governance variables, runs H1-H4 | `src/collect/run_collect.py`, then `run_all.py` |

## Setup

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # fill in TALLY_API_KEY and CRYPTOCOMPARE_API_KEY
```

## Run

```
.venv/bin/python -m src.collect.run_collect      # network; every response cached in data/raw/
.venv/bin/python run_all.py                      # offline; build + analysis
```

Collection steps can be run one by one, e.g. `python -m src.collect.run_collect prices`.
Cached responses are never requested again, so a rerun only fetches what is missing.

### CryptoCompare budget

The current key allows **100 calls per month**. Every call is logged in
`data/raw/cryptocompare/_call_log.csv`; the collector refuses to call beyond the
budget and keeps 5 calls in reserve. Price histories that do not fit are listed in
`data/interim/cc_pending_histories.csv`; rerun the `prices` step after the monthly reset.

## Sample construction (new pipeline)

Unit of observation: a DAO = a governance token contract on a mainnet chain.
Rules U1-U8 are documented in `src/build/universe.py`; every excluded organization
and its reason is in `reports/sample_funnel.csv`, counts in
`reports/tables/sample_funnel_summary.csv`.

Token matching: CryptoCompare no longer publishes contract addresses, so tokens are
matched by ticker, checked by project name, and verified by comparing the on-chain
supply (Tally) with CryptoCompare's supply. Matches that fail and were accepted by
the author are listed with reasons in `config_decisions/token_match_decisions.csv`.
No data value is edited by hand anywhere in the pipeline.

## Layout

```
config.py              paths, sample period, seeds, thresholds
config_decisions/      author decisions with written reasons (token matches)
data/raw/              cached API responses with collection timestamps
data/interim/          collected tables (organizations, tokens, governors, delegates, proposals, prices)
data/processed/        analysis-ready tables
src/collect/           API collectors
src/build/             matching, universe, governance variables, returns, events, cross-section
src/analysis/          H1-H4
reports/               results, funnel, tables, figures, paper_numbers.tex
```
