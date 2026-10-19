"""H1 (governance vs size) and H2 (governance vs average returns) on fresh data.

Main specification: complete cases, no imputation, logs as in the thesis
(ln HHI top-100, ln participation, ln Q ratio, ln market cap), HC3.
"""
import numpy as np
import pandas as pd
from scipy import stats

import config
from src.analysis.common import ols, pairs_bootstrap, save, tidy

GOV = ["ln_hhi", "ln_part", "ln_qratio"]


def _prep(cs):
    d = cs.copy()
    d["ln_hhi"] = np.log(d.hhi_top100)
    d["ln_part"] = np.log(d.participation.where(d.participation > 0))
    d["ln_qratio"] = np.log(d.q_ratio.where(d.q_ratio > 0))
    d["ln_mcap"] = np.log(d.mcap_usd.where(d.mcap_usd > 0))
    d["ln_fdv_live"] = np.log(d.fdv_live.where(d.fdv_live > 0))
    d["ln_fdv_avg"] = np.log(d.fdv_avg.where(d.fdv_avg > 0))
    d["ln_nakamoto"] = np.log(d.nakamoto)
    d["ln_q_raw"] = np.log(d.q_raw)
    d["ln_turnout"] = np.log(d.turnout_supply.where(d.turnout_supply > 0))
    d["ln_delegates"] = np.log(d.delegates_count.where(d.delegates_count > 0))
    d["ln_holders"] = np.log(d.token_owners_count.where(d.token_owners_count > 0))
    # token age in years at the end of the sample, from the first month with a return
    # (left-censored at January 2021 for older tokens)
    end = pd.Period(config.SAMPLE_END_COLLECT[:7], "M")
    d["age_years"] = d.first_month.map(lambda m: (end - pd.Period(m, "M")).n / 12 if isinstance(m, str) else np.nan)
    d["eth_mainnet"] = (d.token_chain == "eip155:1").astype(float)
    return d


# H1 design agreed with the author (2026-10-06): size = FDV of live tokens (main),
# CryptoCompare market cap and life-average FDV (robustness); governance measures that do
# not divide by the delegate count; delegates / holders as controls. Participation and
# Q ratio are kept for comparison with the thesis but are mechanically tied to size.
SIZES = {"ln_fdv_live": "FDV, live tokens (main)", "ln_mcap": "CryptoCompare market cap",
         "ln_fdv_avg": "FDV, average over trading life"}
SCALE_FREE = ["ln_hhi", "top1_share", "top10_share", "ln_nakamoto", "ln_q_raw", "ln_turnout"]
CONTROLS = ["ln_delegates", "ln_holders"]
PER_DELEGATE = ["ln_part", "ln_qratio"]


def _spearman_ci(x, y, ref_rho=0.25):
    from scipy.stats import norm
    n = len(x)
    rho, p = stats.spearmanr(x, y)
    se = np.sqrt((1 + rho ** 2 / 2) / (n - 3))  # Bonett and Wright (2000)
    lo, hi = np.tanh(np.arctanh(rho) + np.array([-1.96, 1.96]) * se)
    se0 = 1 / np.sqrt(n - 3)
    power = norm.sf(1.96 - np.arctanh(ref_rho) / se0) + norm.cdf(-1.96 - np.arctanh(ref_rho) / se0)
    mde80 = np.tanh((1.96 + 0.8416) * se0)
    return {"n": n, "rho": rho, "p": p, "ci_low": lo, "ci_high": hi,
            "power_at_rho_0.25": power, "min_detectable_rho_80pct": mde80}


def descriptives(d):
    cols = {"hhi_top100": "HHI (top-100)", "hhi_all_collected": "HHI (all collected)",
            "coverage_top100": "Top-100 coverage", "top1_share": "Top-1 share", "top5_share": "Top-5 share",
            "top10_share": "Top-10 share", "participation": "Participation", "turnout_supply": "Turnout (votes cast / token supply)",
            "nakamoto": "Nakamoto coefficient", "q_raw": "Q (min delegates for quorum)", "q_ratio": "Q ratio", "mcap_usd": "Market cap (USD)", "fdv_live": "FDV live tokens (USD)",
            "fdv_avg": "FDV life average (USD)", "token_owners_count": "Token holders",
            "delegates_count": "Delegates",
            "avg_log_return": "Avg monthly log return", "n_months": "Months of returns"}
    rows = []
    for c, label in cols.items():
        s = d[c].dropna()
        rows.append({"variable": label, "n": len(s), "mean": s.mean(), "median": s.median(), "sd": s.std(),
                     "min": s.min(), "max": s.max(), "missing": int(d[c].isna().sum())})
    for st, k in d.q_status.fillna("no governance data").value_counts().items():
        rows.append({"variable": f"Q status: {st}", "n": int(k)})
    return save(pd.DataFrame(rows), "new_descriptives.csv")


def quorum_capture(d):
    rows = []
    for name, s_ in [("all", d), ("active", d[d.active_12m.fillna(False).astype(bool)])]:
        r = s_[s_.q_status == "reached"]
        one = r[r.q_raw == 1]
        rows.append({"sample": name, "n_daos": len(s_), "n_q_reached": len(r), "n_q_equal_1": len(one),
                     "share_q_equal_1": len(one) / len(r) if len(r) else np.nan,
                     "median_quorum_share_of_delegated": r.quorum_share_of_delegated.median(),
                     "median_top1_share": r.top1_share.median(),
                     "n_quorum_unreachable": int(s_.q_status.fillna("").str.startswith("quorum exceeds").sum()),
                     "daos_q_equal_1": ", ".join(one.sort_values("fdv_avg", ascending=False).dao_slug)})
    return save(pd.DataFrame(rows), "new_quorum_capture.csv")


def h1(d):
    for name, s_ in [("all", d), ("active", d[d.active_12m.fillna(False).astype(bool)])]:
        _h1(s_, name)
    for f in ["new_h1_spearman.csv", "new_h1_ols.csv", "new_h1_bootstrap.csv"]:
        parts = [pd.read_csv(config.TABLES / f.replace(".csv", f"_{n}.csv")) for n in ("all", "active")]
        pd.concat(parts).to_csv(config.TABLES / f, index=False)
        for n in ("all", "active"):
            (config.TABLES / f.replace(".csv", f"_{n}.csv")).unlink()


def _h1(d, sample):
    rows = []
    for size, label in SIZES.items():
        for v in SCALE_FREE + CONTROLS + PER_DELEGATE:
            t = d[[v, size]].dropna()
            if len(t) < 5:
                continue
            kind = ("scale-free" if v in SCALE_FREE else "control" if v in CONTROLS
                    else "per-delegate (mechanical)")
            rows.append({"sample": sample, "size": label, "variable": v, "kind": kind, **_spearman_ci(t[v], t[size])})
    save(pd.DataFrame(rows), f"new_h1_spearman_{sample}.csv")

    out = []
    specs = {"M1": ["ln_hhi"], "M2": ["ln_hhi", "ln_delegates"],
             "M3": ["ln_hhi", "ln_turnout", "ln_delegates"],
             "M5 controls": ["ln_hhi", "ln_delegates", "age_years", "eth_mainnet"],
             "M4 thesis spec": ["ln_hhi"] + PER_DELEGATE}
    for size, label in SIZES.items():
        for m, cols in specs.items():
            s_ = d.dropna(subset=cols + [size])
            if len(s_) <= len(cols) + 2:
                continue
            out.append(tidy(ols(s_[size], s_[cols]), m, dep=size, size=label, sample=sample))
    save(pd.concat(out), f"new_h1_ols_{sample}.csv")

    s_ = d.dropna(subset=["ln_hhi", "ln_fdv_live"])
    b = pairs_bootstrap(s_.ln_hhi, s_.ln_fdv_live, config.N_BOOT_NEW, config.SEED)
    np.save(config.DATA_PROCESSED / f"h1_bootstrap_{sample}.npy", b)
    lo, hi = np.percentile(b, [2.5, 97.5])
    save(pd.DataFrame([{"sample": sample, "size": "FDV, live tokens", "n": len(s_), "reps": len(b), "mean": b.mean(),
                        "ci_low_pct": lo, "ci_high_pct": hi, "share_negative": (b < 0).mean(),
                        "p_two_sided": min(1.0, 2 * min((b >= 0).mean(), (b <= 0).mean()))}]),
         f"new_h1_bootstrap_{sample}.csv")


def h2(d):
    out = []
    specs = [["ln_hhi"], ["ln_hhi", "ln_part"], GOV, GOV + ["ln_fdv_live"]]
    base = d[d.n_months >= config.MIN_RETURN_MONTHS_NEW]
    for dep in ["avg_log_return", "avg_excess_return"]:
        for i, cols in enumerate(specs, 1):
            s = base.dropna(subset=cols + [dep])
            out.append(tidy(ols(s[dep], s[cols]), f"M{i}", dep=dep))
    save(pd.concat(out), "new_h2_ols.csv")
    sp = []
    for v in GOV + ["ln_fdv_live"]:
        s = base.dropna(subset=[v, "avg_log_return"])
        rho, p = stats.spearmanr(s[v], s.avg_log_return)
        sp.append({"variable": v, "rho": rho, "p": p, "n": len(s)})
    save(pd.DataFrame(sp), "new_h2_spearman.csv")


def run():
    cs = pd.read_csv(config.DATA_PROCESSED / "cross_section.csv")
    d = _prep(cs)
    descriptives(d)
    quorum_capture(d)
    h1(d)
    h2(d)
    return d
