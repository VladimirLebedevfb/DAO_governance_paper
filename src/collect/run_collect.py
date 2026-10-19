"""Collection orchestrator (network). Every step is cached, so rerunning only
fetches what is missing.

    .venv/bin/python -m src.collect.run_collect [step ...]

Steps: orgs, tokens, coinlist, match, candidates, governors, finalize, market,
delegates, proposals, prices. Without arguments all steps run in order.
CryptoCompare spending: market snapshot for all matched tickers, then BTC, then
daily histories in order of proposal count, keeping CC_RESERVE calls unspent.
Tokens that do not fit in this month's budget are listed in
data/interim/cc_pending_histories.csv and fetched on the next run after the reset.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config  # noqa: E402
from src.build import matching, universe  # noqa: E402
from src.collect import cryptocompare as cc  # noqa: E402
from src.collect import tally_delegates, tally_governors, tally_orgs, tally_proposals, tally_tokens  # noqa: E402
from src.utils.http import BudgetError, CachedApiError  # noqa: E402

CC_RESERVE = 5


def step_orgs():
    tally_orgs.collect()


def step_tokens():
    orgs = pd.read_csv(config.DATA_INTERIM / "tally_organizations.csv")
    orgs = orgs[(orgs.proposalsCount > 0) & ~orgs.slug.str.contains(universe.TEST_PATTERN)]
    tally_tokens.collect(orgs)


def step_coinlist():
    cc.coinlist()


def step_match():
    m = matching.build()
    print(m.match_status.value_counts().to_string())


def step_candidates():
    c = universe.candidates()
    print(pd.read_csv(universe.SUMMARY).to_string(index=False))


def step_governors():
    orgs = pd.read_csv(config.DATA_INTERIM / "tally_organizations.csv")
    tally_governors.collect(orgs[orgs.id.isin(universe.candidate_member_orgs())])


def step_finalize():
    main, pg = universe.finalize()
    print(len(main), "DAOs;", len(pg), "governors for proposals")


def step_market():
    daos = pd.read_csv(config.DATA_INTERIM / "universe_daos.csv")
    syms = sorted(set(daos.cc_symbol.dropna()) | {config.BENCHMARK})
    print("plan:", cc.plan(syms))
    cc.pricemultifull(syms)
    matching.verify_supply()
    final = universe.market_check()
    print(len(final), "DAOs after U8")


def step_select():
    _, log = universe.select_governors()
    print(len(log), "DAOs changed governor; see reports/governor_selection_changes.csv")


def step_delegates():
    daos = pd.read_csv(config.DATA_INTERIM / "universe_daos.csv")
    tally_delegates.collect(daos)


def step_proposals():
    pg = pd.read_csv(config.DATA_INTERIM / "universe_proposal_governors_final.csv")
    tally_proposals.collect(pg.drop_duplicates("governor_id"))


def step_prices():
    daos = pd.read_csv(config.DATA_INTERIM / "universe_daos.csv")
    order = [config.BENCHMARK] + list(daos.sort_values("dao_proposals_count", ascending=False).cc_symbol.dropna().unique())
    frames, pending, failed = [], [], []
    for sym in order:
        if cc.remaining_budget() <= CC_RESERVE and not _cached(sym):
            pending.append(sym)
            continue
        try:
            frames.append(cc.histoday(sym))
        except BudgetError:
            pending.append(sym)
        except (CachedApiError, RuntimeError) as exc:
            failed.append({"cc_symbol": sym, "error": str(exc)[:300]})
    prices = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    prices.to_csv(config.DATA_INTERIM / "cc_daily_prices.csv", index=False)
    pd.DataFrame({"cc_symbol": pending}).to_csv(config.DATA_INTERIM / "cc_pending_histories.csv", index=False)
    pd.DataFrame(failed, columns=["cc_symbol", "error"]).to_csv(config.DATA_INTERIM / "cc_failed_histories.csv", index=False)
    print(f"histories: {prices.cc_symbol.nunique() if len(prices) else 0} loaded, {len(pending)} pending, {len(failed)} failed;"
          f" budget left {cc.remaining_budget()}")


def _cached(sym):
    return any((config.DATA_RAW / "cryptocompare").glob(f"histoday_{config.COLLECTION_TAG}_{sym}_0__*.json"))


STEPS = {"orgs": step_orgs, "tokens": step_tokens, "coinlist": step_coinlist, "match": step_match,
         "candidates": step_candidates, "governors": step_governors, "finalize": step_finalize,
         "market": step_market, "proposals": step_proposals, "select": step_select, "delegates": step_delegates,
         "prices": step_prices}

if __name__ == "__main__":
    for name in (sys.argv[1:] or list(STEPS)):
        print(f"== {name}", flush=True)
        STEPS[name]()
