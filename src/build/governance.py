"""B3: governance variables per DAO from freshly collected Tally data.

Definitions follow the thesis (Section 4.3):
  * shares use the delegatesVotesCount of the SAME governor whose delegates were
    collected (numerator and denominator from one governor);
  * HHI over the top-100 delegates (thesis) and over all collected delegates;
  * top-1/5/10 shares and coverage;
  * Q = minimum number of top delegates whose votes reach the quorum of the most
    recent concluded proposal (fallback: governor quorum). If the collected
    delegates cannot reach it, Q is censored and stored as missing with
    q_censored_at = number of delegates collected. No imputation anywhere;
  * participation = mean unique voters (for + against + abstain) over the 20 most
    recent concluded proposals / delegatesCount (missing, with a reason, when above 1:
    Tally reports today's delegatesCount while the voters are historical);
    turnout = mean votes cast / total token supply over the same proposals.
"""
import numpy as np
import pandas as pd

import config

N_QUORUM = 5  # quorum = median over the last N concluded proposals without data errors
PASSED = {"executed", "succeeded", "queued", "pendingexecution", "callexecuted", "crosschainexecuted"}
CONCLUDED = {"executed", "defeated", "succeeded", "queued", "expired", "pendingexecution",
             "callexecuted", "crosschainexecuted", "canceled"}


def _int(x):
    try:
        return int(str(x).split(".")[0])
    except (TypeError, ValueError):
        return None


def concentration(dels, total):
    v = np.array([_int(x) for x in dels.sort_values("rank").votes_raw], dtype=object)
    v = np.array([float(x) for x in v])
    if total is None or total <= 0 or len(v) == 0:
        return {}
    s = v / float(total)
    half = np.nonzero(np.cumsum(s) >= 0.5)[0]
    return {
        # Nakamoto coefficient: fewest delegates holding a majority of delegated votes
        "nakamoto": int(half[0] + 1) if len(half) else np.nan,
        "n_delegates_collected": len(v),
        "hhi_top100": float((s[:100] ** 2).sum()),
        "hhi_all_collected": float((s ** 2).sum()),
        "coverage_top100": float(s[:100].sum()),
        "coverage_all_collected": float(s.sum()),
        "top1_share": float(s[:1].sum()), "top5_share": float(s[:5].sum()), "top10_share": float(s[:10].sum()),
    }


def quorum_coalition(dels, quorum):
    if quorum is None or quorum <= 0:
        return {"q_raw": np.nan, "q_censored": np.nan, "q_censored_at": np.nan}
    v = [float(_int(x)) for x in dels.sort_values("rank").votes_raw]
    cum = np.cumsum(v)
    hit = np.nonzero(cum >= float(quorum))[0]
    if len(hit):
        return {"q_raw": int(hit[0] + 1), "q_censored": False, "q_censored_at": np.nan}
    return {"q_raw": np.nan, "q_censored": True, "q_censored_at": len(v)}


def build(selected, delegates, proposals, as_of):
    """selected: one row per DAO with organization_id, governor_id, delegates_count,
    delegates_votes_raw, quorum_raw (governor level), token_decimals."""
    out = []
    as_of = pd.Timestamp(as_of)
    as_of = as_of.tz_localize("UTC") if as_of.tzinfo is None else as_of
    proposals = proposals.copy()
    proposals["end_dt"] = pd.to_datetime(proposals.end_ts, utc=True, errors="coerce")
    for s in selected.itertuples():
        d = delegates[delegates.governor_id == s.governor_id]
        total = _int(s.delegates_votes_raw)
        row = {"organization_id": s.organization_id, "governor_id": s.governor_id,
               "delegates_count": s.delegates_count, "delegates_votes_raw": s.delegates_votes_raw}
        row.update(concentration(d, total))

        p = proposals[(proposals.organization_id == s.organization_id) & (proposals.governor_id == s.governor_id)]
        done = p[p.status.isin(CONCLUDED) & (p.end_dt <= as_of)].sort_values("end_dt", ascending=False).copy()
        done["cast"] = sum(done[f"{t}_votes_raw"].map(lambda x: float(_int(x) or 0)) for t in ["for", "against", "abstain"])
        done["q"] = done.quorum_raw.map(lambda x: float(_int(x) or 0))
        # data error: a passed proposal whose total votes cast are below its quorum cannot have met it
        done["quorum_error"] = done.status.isin(PASSED) & (done.q > 0) & (done.cast < done.q)
        qp = done[(done.q > 0) & ~done.quorum_error].head(N_QUORUM)
        if len(qp):
            q, q_src, q_date = int(np.median(qp.q)), f"median of last {len(qp)} proposals", qp.iloc[0].end_dt
        else:
            q, q_src, q_date = _int(s.quorum_raw), "governor", pd.NaT
        latest = done[done.q > 0]
        row.update({"quorum_latest_raw": latest.iloc[0].q if len(latest) else np.nan,
                    "n_quorum_data_errors": int(done.quorum_error.sum())})
        # dormancy: largest turnout ever seen relative to today's delegated votes (same units)
        row["dormancy_ratio"] = (done.cast.max() / total) if (len(done) and total) else np.nan
        # activity: any concluded proposal of the DAO (all its governors) in the last 12 months
        dao_done = proposals[(proposals.organization_id == s.organization_id) & proposals.status.isin(CONCLUDED)
                             & (proposals.end_dt <= as_of)]
        row["last_concluded"] = dao_done.end_dt.max()
        row["active_12m"] = bool((dao_done.end_dt > as_of - pd.Timedelta(days=365)).any())
        row.update({"quorum_raw": q, "quorum_source": q_src, "quorum_date": q_date,
                    "quorum_share_of_delegated": (q / total) if (q and total) else np.nan})
        row.update(quorum_coalition(d, q))
        # quorum status: separates missing delegation data and unreachable quorums from censoring
        supply_raw = _int(getattr(s, "token_supply_raw", None))
        if not total:
            status = "no delegation data (delegatesVotesCount = 0)"
        elif q and supply_raw and not (1e-6 <= q / supply_raw <= 1):
            status = "implausible quorum units (quorum / supply outside [1e-6, 1])"
        elif q and q > total:
            status = "quorum exceeds all delegated votes (unreachable with current delegation)"
        elif row.get("q_censored") is True:
            status = "not reached by the collected delegates"
        elif pd.notna(row.get("q_raw")):
            status = "reached"
        else:
            status = "no quorum"
        row["q_status"] = status
        row["quorum_share_of_supply"] = (q / supply_raw) if (q and supply_raw) else np.nan
        if status != "reached":
            row["q_raw"] = np.nan
        row["q_ratio"] = row["q_raw"] / s.delegates_count if s.delegates_count else np.nan

        last20 = done[done.status != "canceled"].head(20)
        voters = last20[["for_voters", "against_voters", "abstain_voters"]].fillna(0).sum(axis=1)
        cast = sum(last20[f"{t}_votes_raw"].map(lambda x: float(_int(x) or 0)) for t in ["for", "against", "abstain"])
        supply = _int(getattr(s, "token_supply_raw", None))
        part = (voters.mean() / s.delegates_count) if len(last20) and s.delegates_count else np.nan
        row.update({
            "n_proposals_concluded": len(done), "n_proposals_participation": len(last20),
            "avg_voters": voters.mean() if len(last20) else np.nan,
            "participation_raw": part,
            # delegatesCount is today's value, voters are historical; above 1 the ratio is not
            # interpretable (the delegate base shrank), so it is set missing, not imputed
            "participation": part if part <= 1 else np.nan,
            "participation_issue": "voters exceed current delegates count" if part > 1 else "",
            # votes cast relative to total token supply (time-stable denominator)
            "turnout_supply": (cast.mean() / supply) if len(last20) and supply else np.nan,
        })
        if row["turnout_supply"] > 1:  # votes and supply in different units (e.g. rebasing YAM)
            row["turnout_supply"] = np.nan
            row["turnout_issue"] = "votes cast exceed token supply: vote units differ from token units"
        out.append(row)
    return pd.DataFrame(out)
