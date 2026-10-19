"""H3 robustness: overlapping windows, own-baseline excess CAR, clustered inference.

Samples
  proposals      every proposal with a complete window (thesis unit)
  event dates    one event per (DAO, end date): proposals ending the same day share a window
  non-overlap    event dates of a DAO at least 11 days apart (greedy, earliest first),
                 so no two windows of the same DAO overlap
Excess CAR = event CAR - the DAO's own baseline, the mean CAR of all 11-day windows
that contain no event day. This removes the weighting problem of comparing
proposal-weighted event CARs with DAO- or day-weighted baselines.
Inference: SE clustered by DAO; two-way by DAO and calendar month (common shocks);
DAO-level t-test (each DAO one observation); placebo with matching weights.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

import config
from src.analysis.common import save

L = config.EVENT_WINDOW[1] - config.EVENT_WINDOW[0] + 1


def _mean_test(y, dao, month):
    X = np.ones((len(y), 1))
    out = {"n_events": len(y), "n_daos": dao.nunique(), "mean": y.mean()}
    r1 = sm.OLS(y.values, X).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(dao)[0]})
    g2 = np.column_stack([pd.factorize(dao)[0], pd.factorize(month)[0]])
    r2 = sm.OLS(y.values, X).fit(cov_type="cluster", cov_kwds={"groups": g2})
    out.update({"se_cluster_dao": r1.bse[0], "p_cluster_dao": r1.pvalues[0],
                "se_cluster_dao_month": r2.bse[0], "p_cluster_dao_month": r2.pvalues[0]})
    per_dao = y.groupby(dao.values).mean()
    t, p = stats.ttest_1samp(per_dao, 0)
    out.update({"dao_level_mean": per_dao.mean(), "dao_level_t": t, "dao_level_p": p})
    return out


def own_baselines(win, daily):
    """Per DAO: CARs of all 11-day windows of consecutive days without any event day.
    Returns (baseline = mean clean-window CAR, clean-window CARs used by the placebo)."""
    daily = daily[daily.cc_symbol.isin(win.cc_symbol.unique())].dropna(subset=["excess_return"])
    ev_days = set(zip(win.cc_symbol, win.date))
    base, centers = {}, {}
    for s, g in daily.sort_values("date").groupby("cc_symbol"):
        g = g.set_index("date").asfreq("D")
        ex = g.excess_return.values
        clean = np.array([(s, d) not in ev_days for d in g.index]) & ~np.isnan(ex)
        ok = pd.Series(clean.astype(int)).rolling(L).sum().values == L
        sums = pd.Series(np.nan_to_num(ex)).rolling(L).sum().values
        base[s] = sums[ok].mean() if ok.any() else np.nan
        centers[s] = sums[ok]
    return base, centers


def run():
    win = pd.read_csv(config.DATA_PROCESSED / "event_windows.csv", parse_dates=["event_date", "date"])
    daily = pd.read_csv(config.DATA_PROCESSED / "daily_returns.csv", parse_dates=["date"])
    base, centers = own_baselines(win, daily)

    prop = win.groupby(["cc_symbol", "proposal_id", "event_date"]).abnormal_return.sum().rename("car").reset_index()
    dates = prop.groupby(["cc_symbol", "event_date"]).agg(car=("car", "first"), n_props=("car", "size")).reset_index()
    keep = []
    for s, g in dates.sort_values("event_date").groupby("cc_symbol"):
        last = None
        for r in g.itertuples():
            if last is None or (r.event_date - last).days >= L:
                keep.append(r.Index)
                last = r.event_date
    nonov = dates.loc[keep]

    rows, rng = [], np.random.RandomState(config.SEED)
    for name, df in [("proposals", prop), ("event dates", dates), ("non-overlapping event dates", nonov)]:
        df = df.assign(baseline=df.cc_symbol.map(base))
        df["excess_car"] = df.car - df.baseline
        month = df.event_date.dt.to_period("M").astype(str)
        for measure in ["car", "excess_car"]:
            rows.append({"sample": name, "measure": measure, **_mean_test(df[measure], df.cc_symbol, month)})
        # placebo: same number of windows per DAO drawn from its clean windows
        k = df.cc_symbol.value_counts()
        obs_w, obs_d = df.car.mean(), df.groupby("cc_symbol").car.mean().mean()
        pw, pd_ = [], []
        for _ in range(config.N_PLACEBO_NEW):
            per = {s: rng.choice(centers[s], n, replace=n > len(centers[s])) for s, n in k.items() if len(centers[s])}
            pw.append(np.concatenate(list(per.values())).mean())
            pd_.append(np.mean([v.mean() for v in per.values()]))
        pw, pd_ = np.array(pw), np.array(pd_)
        rows.append({"sample": name, "measure": "placebo event-weighted", "n_events": len(df),
                     "n_daos": df.cc_symbol.nunique(), "mean": obs_w, "placebo_mean": pw.mean(),
                     "placebo_p_one_sided": (pw <= obs_w).mean()})
        rows.append({"sample": name, "measure": "placebo DAO-equal", "n_events": len(df),
                     "n_daos": df.cc_symbol.nunique(), "mean": obs_d, "placebo_mean": pd_.mean(),
                     "placebo_p_one_sided": (pd_ <= obs_d).mean()})
    out = pd.DataFrame(rows)
    save(out, "new_h3_robust.csv")
    return out


if __name__ == "__main__":
    print(run().round(4).to_string(index=False))
