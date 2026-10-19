"""H3 (event study) and H4 (market factor) on fresh data.

H3 follows the thesis tests: per-day mean abnormal returns with t-tests, CAR,
baseline, placebo, event vs non-event days, day dummies (base day -5, HC3), ADF.
Because the observed CAR averages over proposals, placebo and baseline are
reported both in the thesis weighting (DAO-equal / pooled) and in the same
weighting as the observed CAR (proposal-weighted). Neither is labelled "main"
until the author decides.
H4: pooled OLS of monthly token returns on BTC returns, HC3 and DAO-clustered SE.
"""
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.tsa.stattools import adfuller

import config
from src.analysis.common import ols, save, tidy

warnings.filterwarnings("ignore", category=FutureWarning)


def h3(win, daily, monthly):
    lo, hi = config.EVENT_WINDOW
    per = []
    for k, g in win.groupby("event_day"):
        t, p = stats.ttest_1samp(g.abnormal_return, 0)
        per.append({"event_day": k, "mean": g.abnormal_return.mean(), "t": t, "p": p, "n": len(g)})
    per = pd.DataFrame(per)
    car = per["mean"].sum()
    save(per, "new_h3_per_day.csv")

    pc = win.groupby(["cc_symbol", "proposal_id"]).abnormal_return.sum()
    n_ev = win.groupby("cc_symbol").proposal_id.nunique()

    # event vs non-event days (unique DAO-days inside any window vs all other days)
    d = daily.dropna(subset=["excess_return"]).copy()
    d["date"] = pd.to_datetime(d.date)
    d = d[d.cc_symbol.isin(n_ev.index)]
    ev_keys = set(zip(win.cc_symbol, pd.to_datetime(win.date)))
    d["is_event_day"] = [(s, t) in ev_keys for s, t in zip(d.cc_symbol, d.date)]
    a, b = d[d.is_event_day].excess_return, d[~d.is_event_day].excess_return
    t_ev, p_ev = stats.ttest_ind(a, b)

    # baselines
    m_ex = monthly[monthly.cc_symbol.isin(n_ev.index)].excess_return.mean()
    per_dao_ne = d[~d.is_event_day].groupby("cc_symbol").excess_return.mean()
    base_rows = [
        {"variant": "thesis: mean monthly excess / 30 x 11", "value": m_ex / 30 * 11},
        {"variant": "pooled non-event daily excess x 11", "value": b.mean() * 11},
        {"variant": "proposal-weighted: per-DAO non-event mean x 11", "value":
            (per_dao_ne.reindex(n_ev.index) * n_ev).sum() / n_ev.sum() * 11},
    ]

    # placebo: random non-event centre days per DAO, number of draws = events of that DAO
    rng = np.random.RandomState(config.SEED)
    series = {s: (g.sort_values("date").excess_return.values, g.sort_values("date").is_event_day.values)
              for s, g in d.groupby("cc_symbol")}
    dao_eq, prop_w = [], []
    for _ in range(config.N_PLACEBO_NEW):
        dao_c, all_c = [], []
        for s in sorted(series):
            ex, ise = series[s]
            k = int(n_ev.get(s, 0))
            cand = np.arange(len(ex))[~ise]
            cand = cand[(cand >= -lo) & (cand < len(ex) - hi)]
            if k == 0 or len(cand) == 0:
                continue
            pick = rng.choice(cand, k, replace=k > len(cand))
            cars = [ex[i + lo:i + hi + 1].sum() for i in pick]
            dao_c.append(np.mean(cars))
            all_c.extend(cars)
        dao_eq.append(np.mean(dao_c))
        prop_w.append(np.mean(all_c))
    dao_eq, prop_w = np.array(dao_eq), np.array(prop_w)
    np.save(config.DATA_PROCESSED / "placebo_dao_equal.npy", dao_eq)
    np.save(config.DATA_PROCESSED / "placebo_proposal_weighted.npy", prop_w)
    obs_dao_eq = pc.groupby(level=0).mean().mean()

    summary = pd.DataFrame([
        {"item": "DAOs", "value": win.cc_symbol.nunique()},
        {"item": "proposals (events)", "value": win.proposal_id.nunique()},
        {"item": "unique event dates", "value": win.drop_duplicates(["cc_symbol", "event_date"]).shape[0]},
        {"item": "window rows", "value": len(win)},
        {"item": "date range", "value": f"{pd.to_datetime(win.event_date).min().date()} to {pd.to_datetime(win.event_date).max().date()}"},
        {"item": "CAR[-5,+5] (proposal-weighted)", "value": car},
        {"item": "CAR[-5,+5] (DAO-equal)", "value": obs_dao_eq},
        {"item": "share negative proposal CAR", "value": (pc < 0).mean()},
        {"item": "mean / median proposal CAR", "value": f"{pc.mean():.4f} / {pc.median():.4f}"},
        *[{"item": f"baseline: {r['variant']}", "value": r["value"]} for r in base_rows],
        {"item": "placebo DAO-equal: mean", "value": dao_eq.mean()},
        {"item": "placebo DAO-equal: p vs DAO-equal CAR", "value": (dao_eq <= obs_dao_eq).mean()},
        {"item": "placebo DAO-equal: p vs proposal-weighted CAR (thesis comparison)", "value": (dao_eq <= car).mean()},
        {"item": "placebo proposal-weighted: mean", "value": prop_w.mean()},
        {"item": "placebo proposal-weighted: p vs proposal-weighted CAR", "value": (prop_w <= car).mean()},
        {"item": "placebo reps", "value": config.N_PLACEBO_NEW},
        {"item": "event-day mean (unique DAO-days) / N", "value": f"{a.mean():.5f} / {len(a)}"},
        {"item": "non-event mean / N", "value": f"{b.mean():.5f} / {len(b)}"},
        {"item": "event vs non-event t / p", "value": f"{t_ev:.3f} / {p_ev:.3f}"},
        {"item": "pooled ADF (daily excess, event DAOs)", "value":
            adfuller(d.sort_values(['cc_symbol', 'date']).excess_return.values, autolag="AIC")[0]},
    ])
    save(summary, "new_h3_summary.csv")

    dd = win.assign(day=win.event_day.astype(int))
    res = smf.ols(f"abnormal_return ~ C(day, Treatment(reference={lo}))", data=dd).fit(cov_type="HC3")
    save(pd.DataFrame({"term": res.params.index, "coef": res.params.values, "se": res.bse.values,
                       "p": res.pvalues.values}), "new_h3_day_dummies.csv")
    return summary


def _wild_cluster_p(y, X, groups, j, reps, seed):
    """Restricted wild cluster bootstrap-t (Rademacher weights) for H0: beta_j = 0.
    Reliable with few clusters, unlike the analytic cluster SE (Cameron, Gelbach, Miller 2008)."""
    import statsmodels.api as sm
    g = pd.factorize(groups)[0]
    full = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": g}, use_t=True)
    t_obs = full.tvalues.iloc[j]
    Xr = X.drop(columns=X.columns[j])
    r = sm.OLS(y, Xr).fit()
    rng = np.random.RandomState(seed)
    G = g.max() + 1
    t_star = np.empty(reps)
    for b in range(reps):
        w = rng.choice([-1.0, 1.0], G)[g]
        yb = r.fittedvalues + r.resid * w
        t_star[b] = sm.OLS(yb, X).fit(cov_type="cluster", cov_kwds={"groups": g}).tvalues.iloc[j]
    return (np.abs(t_star) >= abs(t_obs)).mean()


def h4(monthly, cs):
    """Nested models on a common sample (BTC; + governance; + size) so that R2 is comparable.
    Governance is time-invariant, so inference rests on the number of DAOs (clusters):
    cluster SE with t(G-1) critical values and wild cluster bootstrap p-values."""
    import statsmodels.api as sm
    g = cs[["cc_symbol", "hhi_top100", "participation", "q_ratio", "delegates_count", "fdv_live"]].copy()
    g["ln_hhi"] = np.log(g.hhi_top100)
    g["ln_part"] = np.log(g.participation.where(g.participation > 0))
    g["ln_qratio"] = np.log(g.q_ratio.where(g.q_ratio > 0))
    g["ln_delegates"] = np.log(g.delegates_count.where(g.delegates_count > 0))
    g["ln_fdv_live"] = np.log(g.fdv_live.where(g.fdv_live > 0))
    d = monthly.merge(g, on="cc_symbol", how="inner").dropna(subset=["log_return", "btc_return"])

    out = []
    full = ols(d.log_return, d[["btc_return"]], "cluster", groups=d.cc_symbol)
    out.append(tidy(full, "M0 BTC only, all DAOs", spec="all", se_type="cluster DAO", n_daos=d.cc_symbol.nunique()))
    specs = {"scale-free": (["ln_hhi", "ln_delegates"], "ln_fdv_live"),
             "thesis-like": (["ln_hhi", "ln_part", "ln_qratio"], "ln_fdv_live")}
    for name, (gov, size) in specs.items():
        s_ = d.dropna(subset=gov + [size]).copy()
        G = s_.cc_symbol.nunique()
        for m, cols in [("M1 BTC", ["btc_return"]), ("M2 BTC + governance", ["btc_return"] + gov),
                        ("M3 BTC + governance + size", ["btc_return"] + gov + [size])]:
            X = sm.add_constant(s_[cols])
            res = sm.OLS(s_.log_return, X).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(s_.cc_symbol)[0]},
                                                 use_t=True)
            t = tidy(res, m, spec=name, se_type="cluster DAO, t(G-1)", n_daos=G)
            t["p_wild_cluster"] = np.nan
            for j, term in enumerate(X.columns):
                if term in gov + [size]:
                    t.loc[t.term == term, "p_wild_cluster"] = _wild_cluster_p(
                        s_.log_return, X, s_.cc_symbol, j, config.N_WILD_BOOT, config.SEED)
            out.append(t)
    save(pd.concat(out), "new_h4_panel.csv")
    rho, p = stats.spearmanr(d.log_return, d.btc_return)
    save(pd.DataFrame([{"rho": rho, "p": p, "n": len(d)}]), "new_h4_spearman.csv")


def run():
    win = pd.read_csv(config.DATA_PROCESSED / "event_windows.csv")
    daily = pd.read_csv(config.DATA_PROCESSED / "daily_returns.csv")
    monthly = pd.read_csv(config.DATA_PROCESSED / "monthly_returns.csv")
    cs = pd.read_csv(config.DATA_PROCESSED / "cross_section.csv")
    h3(win, daily, monthly)
    monthly = monthly[monthly.cc_symbol.isin(cs[cs.n_months >= config.MIN_RETURN_MONTHS_NEW].cc_symbol)]
    h4(monthly, cs)
