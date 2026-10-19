"""New pipeline: build + analysis from cached data (no network access).

    .venv/bin/python -m src.collect.run_collect    # once, needs .env and network
    .venv/bin/python run_all.py                    # any time, offline

"""
import os
import time

os.environ["PIPELINE_OFFLINE"] = "1"

import pandas as pd  # noqa: E402

import config  # noqa: E402
from src.analysis import figures, h1_h2_cross_section, h3_h4_returns, h3_robust, paper_numbers  # noqa: E402
from src.build import cross_section, events, returns  # noqa: E402


def main():
    t0 = time.time()
    prices = pd.read_csv(config.DATA_INTERIM / "cc_daily_prices.csv")
    daily, monthly, _ = returns.build(prices)
    print(f"[ok] returns: {daily.cc_symbol.nunique()} tokens, {len(monthly)} token-months")
    cs = cross_section.build()
    print(f"[ok] cross-section: {len(cs)} DAOs")
    daos = pd.read_csv(config.DATA_INTERIM / "universe_daos.csv")
    props = pd.read_csv(config.DATA_INTERIM / "tally_proposals.csv")
    win, allp = events.build(props, daos, daily)
    print(f"[ok] events: {win.proposal_id.nunique() if len(win) else 0} proposals in the event sample")
    h1_h2_cross_section.run()
    print("[ok] H1, H2")
    h3_h4_returns.run()
    h3_robust.run()
    print("[ok] H3 (incl. robustness), H4")
    figures.run()
    print(f"[ok] figures in {config.FIGURES}")
    print(f"[ok] {paper_numbers.run()} macros in reports/paper_numbers.tex")
    print(f"done in {time.time() - t0:.0f}s; tables in {config.TABLES}")


if __name__ == "__main__":
    main()
