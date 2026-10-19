"""B6: one row per DAO with governance variables, market data and return summary.

Market cap: CryptoCompare pricemultifull MKTCAP at the collection date. A quote is
flagged stale when its LASTUPDATE is more than STALE_DAYS before collection, and a
match is flagged when the supply check fails; flagged DAOs keep their row but get
mcap_usd = NaN with the reason in mcap_issue (so the H1 sample is complete-case).
"""
import numpy as np
import pandas as pd

import config
from src.build import governance

STALE_DAYS = 30
FDV_MAX = 1e11


def size_measures(daos, cs):
    """Alternative size measures from daily prices (no extra API calls).

    supply: on-chain total supply from Tally; for author-accepted matches whose supply
    check failed (multichain W, SEAM with supply 0) CryptoCompare SUPPLY is used.
    fdv_live: mean close in the last sample month x supply, only for tokens with
              trading volume in that month (dead tokens carry stale prices).
    fdv_avg:  mean close over all days with volume > 0 in the sample x supply
              (size over the token's trading life; covers dead tokens).
    """
    snap = pd.read_csv(config.DATA_INTERIM / "cc_market_snapshot.csv")
    px = pd.read_csv(config.DATA_INTERIM / "cc_daily_prices.csv", parse_dates=["date"])
    d = daos[["organization_id", "cc_symbol", "token_supply_raw", "token_decimals", "token_owners_count"]].copy()

    def onchain(r):
        try:
            return int(str(r.token_supply_raw).split(".")[0]) / 10 ** int(r.token_decimals)
        except (TypeError, ValueError):
            return np.nan

    d["supply_onchain"] = d.apply(onchain, axis=1)
    d = d.merge(cs[["organization_id", "supply_check"]], on="organization_id", how="left") \
         .merge(snap[["cc_symbol", "supply"]].rename(columns={"supply": "supply_cc"}), on="cc_symbol", how="left")
    use_cc = (d.supply_check != "ok") & (d.supply_cc > 0)
    d["fdv_issue"] = ""
    d["supply_used"] = np.where(use_cc, d.supply_cc, d.supply_onchain)
    d["supply_source"] = np.where(use_cc, "CryptoCompare", "Tally on-chain")
    d.loc[~(d.supply_used > 0), "supply_used"] = np.nan

    end = pd.Timestamp(config.SAMPLE_END_COLLECT)
    last = px[px.date > end - pd.Timedelta(days=30)].groupby("cc_symbol").agg(
        p_last=("close", "mean"), vol_last=("volume_usd", "sum"))
    traded = px[px.volume_usd > 0].groupby("cc_symbol").agg(p_avg=("close", "mean"), days_traded=("close", "size"))
    d = d.merge(last, on="cc_symbol", how="left").merge(traded, on="cc_symbol", how="left")
    d["fdv_live"] = np.where(d.vol_last > 0, d.p_last * d.supply_used, np.nan)
    d["fdv_avg"] = d.p_avg * d.supply_used
    # no DAO token in CryptoCompare has a market cap above 10 billion USD; FDV above
    # FDV_MAX means price and supply do not belong together (e.g. OOKI: 5.7e15 tokens)
    for c in ["fdv_live", "fdv_avg"]:
        bad = d[c] > FDV_MAX
        d.loc[bad, "fdv_issue"] = f"FDV above {FDV_MAX:.0e} USD: implausible price x supply"
        d.loc[bad, c] = np.nan
    return d[["organization_id", "token_owners_count", "supply_used", "supply_source", "vol_last",
              "days_traded", "fdv_live", "fdv_avg", "fdv_issue"]]


def build():
    daos = pd.read_csv(config.DATA_INTERIM / "universe_daos.csv")
    dels = pd.read_csv(config.DATA_INTERIM / "tally_delegates.csv", dtype={"votes_raw": str})
    props = pd.read_csv(config.DATA_INTERIM / "tally_proposals.csv",
                        dtype={"quorum_raw": str, "for_votes_raw": str, "against_votes_raw": str,
                               "abstain_votes_raw": str})
    snap = pd.read_csv(config.DATA_INTERIM / "cc_market_snapshot.csv", parse_dates=["lastupdate"])
    ver = pd.read_csv(config.DATA_INTERIM / "token_matches_verified.csv")
    rets = pd.read_csv(config.DATA_PROCESSED / "returns_cross_section.csv")

    as_of = pd.Timestamp(config.COLLECTION_DATE, tz="UTC")
    gv = governance.build(daos, dels, props, as_of)

    cs = daos[["organization_id", "dao_slug", "dao_name", "dao_best_rank", "dao_archived", "n_member_orgs",
               "governor_id", "governor_type", "token_chain", "token_address", "token_symbol", "cc_symbol",
               "cc_name", "match_basis"]].merge(gv.drop(columns=["governor_id"]), on="organization_id", how="left")
    cs = cs.merge(snap[["cc_symbol", "mktcap", "price", "volume_24h_usd", "lastupdate"]], on="cc_symbol", how="left")
    cs = cs.merge(ver[["token_address", "supply_check", "supply_ratio_cc_to_tally"]].drop_duplicates("token_address"),
                  on="token_address", how="left")

    issue = pd.Series("", index=cs.index)
    issue[cs.mktcap.isna() | (cs.mktcap <= 0)] = "no market cap in CryptoCompare"
    stale = (as_of - cs.lastupdate).dt.days > STALE_DAYS
    issue[(issue == "") & stale] = f"stale quote (last update more than {STALE_DAYS} days before collection)"
    issue[(issue == "") & (cs.supply_check == "supply_mismatch")] = "supply mismatch between Tally and CryptoCompare"
    cs["mcap_issue"] = issue
    cs["mcap_usd"] = cs.mktcap.where(issue == "")

    cs = cs.merge(rets, on="cc_symbol", how="left")
    cs = cs.merge(size_measures(daos, cs), on="organization_id", how="left")
    cs.to_csv(config.DATA_PROCESSED / "cross_section.csv", index=False)
    return cs
