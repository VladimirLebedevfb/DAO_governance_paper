"""Figures for the SoK paper (matplotlib, serif, 300 dpi).

Figure 2: distributions of governance measures across DAOs.
Figure 3: placebo distributions of the mean CAR[-5,+5] with the observed CAR.
fig_market_distributions: size, returns, delegates, turnout.
fig_h1_scatter: size vs HHI, size vs delegates, partial regression of size on HHI given delegates.
fig_h3_event_path: mean abnormal return by event day and cumulative path, DAO-bootstrap 95% bands.
fig_h4_btc: monthly token returns vs BTC returns.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import config  # noqa: E402

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK2 = "#0b0b0b", "#52514e"

plt.rcParams.update({
    "font.family": "serif", "font.serif": config.FIG_FONT, "font.size": 9,
    "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "axes.axisbelow": True,
    "grid.color": "#e6e5e0", "grid.linewidth": 0.6, "axes.titlesize": 9, "axes.titleweight": "bold",
})


def _hist(ax, x, bins, title, xlabel):
    x = x.dropna()
    ax.hist(x, bins=bins, color=BLUE, edgecolor="white", linewidth=1.0)
    med = x.median()
    ax.axvline(med, color=INK, linewidth=1, linestyle=":")
    right = med > ax.get_xlim()[0] + 0.7 * (ax.get_xlim()[1] - ax.get_xlim()[0])
    ax.annotate(f"median {med:.3g}", xy=(med, ax.get_ylim()[1] * 0.92), xytext=(-4 if right else 4, 0),
                textcoords="offset points", ha="right" if right else "left", fontsize=8, color=INK)
    ax.set_title(f"{title} (N = {len(x)})", loc="left")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("DAOs")
    ax.grid(axis="x", visible=False)


def figure2(cs):
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 5.0))
    _hist(axes[0, 0], cs.hhi_top100, np.linspace(0, 1, 21), "(a) HHI, top-100 delegates", "HHI")
    _hist(axes[0, 1], cs.top10_share, np.linspace(0, 1, 21), "(b) Top-10 delegate share", "share of delegated votes")
    _hist(axes[1, 0], cs.participation, 20, "(c) Participation", "avg voters / delegates")
    q = cs.q_raw.dropna()
    _hist(axes[1, 1], q, np.arange(0.5, q.max() + 1.5, 1), "(d) Q, delegates needed for quorum",
          "number of delegates")
    st = cs.q_status.fillna("")
    n_unreach = int(st.str.startswith("quorum exceeds").sum())
    n_other = int((~st.isin(["reached", ""]) & ~st.str.startswith("quorum exceeds")).sum())
    axes[1, 1].text(0.98, 0.70, f"not shown: {n_unreach} DAOs whose quorum exceeds\nall delegated votes, {n_other} without usable data",
                    transform=axes[1, 1].transAxes, ha="right", fontsize=8, color=INK2)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(config.FIGURES / f"figure2_governance_distributions.{ext}", dpi=config.FIG_DPI)
    plt.close(fig)


def _placebo(ax, draws, observed, title, extra=None):
    ax.hist(draws, bins=40, color=BLUE, edgecolor="white", linewidth=0.6)
    top = ax.get_ylim()[1] * 1.3  # headroom so labels sit above the bars
    ax.set_ylim(0, top)
    p = (draws <= observed).mean()
    ax.axvline(observed, color=ORANGE, linewidth=2)
    p_txt = "p < 0.001" if p < 0.001 else f"p = {p:.3f}"
    ax.annotate(f"observed {observed:.2%}\n{p_txt}", xy=(observed, top * 0.9), xytext=(6, 0),
                textcoords="offset points", ha="left", fontsize=8, color=INK)
    if extra is not None:
        val, label = extra
        ax.axvline(val, color=INK2, linewidth=1, linestyle="--")
        ax.annotate(label, xy=(val, top * 0.9), xytext=(4, 0), textcoords="offset points", fontsize=8, color=INK2)
    ax.set_title(title, loc="left")
    ax.set_xlabel("mean CAR[-5,+5]")
    ax.set_ylabel("placebo draws")
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=1))
    ax.grid(axis="x", visible=False)


def figure3(win):
    pw = np.load(config.DATA_PROCESSED / "placebo_proposal_weighted.npy")
    de = np.load(config.DATA_PROCESSED / "placebo_dao_equal.npy")
    pc = win.groupby(["cc_symbol", "proposal_id"]).abnormal_return.sum()
    obs_pw = win.groupby("event_day").abnormal_return.mean().sum()
    obs_de = pc.groupby(level=0).mean().mean()
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.8))
    _placebo(axes[0], pw, obs_pw, "(a) Proposal-weighted")
    _placebo(axes[1], de, obs_de, "(b) Equal weight per DAO",
             extra=(obs_pw, f"proposal-weighted CAR\n{obs_pw:.2%} (thesis comparison)"))
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(config.FIGURES / f"figure3_placebo.{ext}", dpi=config.FIG_DPI)
    plt.close(fig)


def _save(fig, name):
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(config.FIGURES / f"{name}.{ext}", dpi=config.FIG_DPI)
    plt.close(fig)


def _hist_log(ax, x, title, xlabel, money=False):
    x = x[x > 0].dropna()
    lx = np.log10(x)
    ax.hist(lx, bins=12, color=BLUE, edgecolor="white", linewidth=1.0)
    med = x.median()
    ax.axvline(np.log10(med), color=INK, linewidth=1, linestyle=":")
    lab = f"${med / 1e6:.3g}M" if money else f"{med:,.0f}"
    ax.annotate(f"median {lab}", xy=(np.log10(med), ax.get_ylim()[1] * 0.92), xytext=(4, 0),
                textcoords="offset points", fontsize=8, color=INK)
    ticks = np.arange(np.floor(lx.min()), np.ceil(lx.max()) + 1)
    ax.set_xticks(ticks)
    def short(v):
        for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
            if v >= div:
                return f"{v / div:g}{suf}"
        return f"{v:g}"
    fmt = (lambda t: "$" + short(10 ** t)) if money else (lambda t: short(10 ** t))
    ax.set_xticklabels([fmt(t) for t in ticks])
    ax.set_title(f"{title} (N = {len(x)})", loc="left")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("DAOs")
    ax.grid(axis="x", visible=False)


def fig_market_distributions(cs):
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 5.0))
    _hist_log(axes[0, 0], cs.fdv_live, "(a) FDV, live tokens", "USD, log scale", money=True)
    _hist(axes[0, 1], cs.avg_log_return, 15, "(b) Average monthly log return", "log return")
    _hist_log(axes[1, 0], cs.delegates_count, "(c) Delegates", "number of delegates, log scale")
    _hist(axes[1, 1], cs.turnout_supply, np.linspace(0, 1, 21), "(d) Turnout", "votes cast / token supply")
    _save(fig, "fig_market_distributions")


def _fit_line(ax, x, y, label_pos):
    import statsmodels.api as sm
    r = sm.OLS(y, sm.add_constant(x)).fit(cov_type="HC3")
    xs = np.linspace(x.min(), x.max(), 50)
    ax.plot(xs, r.params.iloc[0] + r.params.iloc[1] * xs, color=ORANGE, linewidth=2)
    p = r.pvalues.iloc[1]
    ax.text(*label_pos, f"slope {r.params.iloc[1]:.2f} (SE {r.bse.iloc[1]:.2f}, "
            + ("p < 0.01)" if p < 0.01 else f"p {p:.2f})"), transform=ax.transAxes, fontsize=8, color=INK2,
            va="bottom")


def fig_h1_scatter(cs):
    d = cs.assign(ln_size=np.log(cs.fdv_avg), ln_hhi=np.log(cs.hhi_top100),
                  ln_del=np.log(cs.delegates_count.where(cs.delegates_count > 0)))
    d = d.dropna(subset=["ln_size", "ln_hhi", "ln_del"])
    import statsmodels.api as sm
    rx = d.ln_hhi - sm.OLS(d.ln_hhi, sm.add_constant(d.ln_del)).fit().fittedvalues
    ry = d.ln_size - sm.OLS(d.ln_size, sm.add_constant(d.ln_del)).fit().fittedvalues
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.6))
    panels = [(d.ln_hhi, d.ln_size, "(a) Size vs HHI", "ln HHI", "ln FDV (life average)"),
              (d.ln_del, d.ln_size, "(b) Size vs delegates", "ln delegates", "ln FDV (life average)"),
              (rx, ry, "(c) Size vs HHI, given delegates", "ln HHI | delegates", "ln FDV | delegates")]
    for ax, (x, y, title, xl, yl) in zip(axes, panels):
        ax.scatter(x, y, s=14, color=BLUE, edgecolor="white", linewidth=0.5)
        _fit_line(ax, x, y, (0.0, 1.02))
        ax.set_title(title, loc="left", pad=16)
        ax.set_xlabel(xl)
        ax.set_ylabel(yl)
    fig.suptitle(f"N = {len(d)} DAOs", x=0.99, ha="right", fontsize=8, color=INK2)
    _save(fig, "fig_h1_scatter")


def fig_h3_event_path(win, daily):
    from src.analysis.h3_robust import own_baselines
    w = win.copy()
    w["date"] = pd.to_datetime(w.date)
    base, _ = own_baselines(w, daily.assign(date=pd.to_datetime(daily.date)))
    m = w.pivot_table(index=["cc_symbol", "proposal_id"], columns="event_day", values="abnormal_return")
    daos = m.index.get_level_values(0).values
    ar = m.values
    ex = ar - np.array([base[s] / ar.shape[1] for s in daos])[:, None]
    rows = {s: np.nonzero(daos == s)[0] for s in np.unique(daos)}
    keys = list(rows)
    rng = np.random.RandomState(config.SEED)
    bs_ar, bs_car, bs_ex = [], [], []
    for _ in range(config.N_BOOT_NEW):
        idx = np.concatenate([rows[k] for k in rng.choice(keys, len(keys), replace=True)])
        bs_ar.append(ar[idx].mean(0))
        bs_car.append(ar[idx].mean(0).cumsum())
        bs_ex.append(ex[idx].mean(0).cumsum())
    days = m.columns.values
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.8))
    ax = axes[0]
    lo, hi = np.percentile(bs_ar, [2.5, 97.5], axis=0)
    ax.axhline(0, color=INK2, linewidth=0.8)
    ax.fill_between(days, lo, hi, color=BLUE, alpha=0.2, linewidth=0)
    ax.plot(days, ar.mean(0), color=BLUE, marker="o", markersize=4, linewidth=2)
    ax.set_title("(a) Mean abnormal return by day", loc="left")
    for ax_ in axes:
        ax_.set_xlabel("day relative to end of voting")
        ax_.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=2 if ax_ is axes[0] else 1))
        ax_.set_xticks(days)
    ax.set_ylabel("abnormal return")
    ax = axes[1]
    ax.axhline(0, color=INK2, linewidth=0.8)
    for series, bs, color, label in [(ar.mean(0).cumsum(), bs_car, BLUE, "raw CAR"),
                                     (ex.mean(0).cumsum(), bs_ex, ORANGE, "CAR over own baseline")]:
        lo, hi = np.percentile(bs, [2.5, 97.5], axis=0)
        ax.fill_between(days, lo, hi, color=color, alpha=0.2, linewidth=0)
        ax.plot(days, series, color=color, linewidth=2, label=f"{label} ({series[-1]:.2%})")
    ax.set_title("(b) Cumulative abnormal return", loc="left")
    ax.set_ylabel("CAR")
    ax.legend(loc="lower left", fontsize=8, frameon=False)
    fig.suptitle(f"{m.shape[0]:,} proposals, {len(keys)} DAOs; bands: 95% bootstrap over DAOs",
                 x=0.99, ha="right", fontsize=8, color=INK2)
    _save(fig, "fig_h3_event_path")


def fig_h4_btc(monthly, cs):
    keep = cs[cs.n_months >= config.MIN_RETURN_MONTHS_NEW].cc_symbol
    d = monthly[monthly.cc_symbol.isin(keep)].dropna(subset=["log_return", "btc_return"])
    import statsmodels.api as sm
    r = sm.OLS(d.log_return, sm.add_constant(d.btc_return)).fit()
    fig, ax = plt.subplots(figsize=(3.6, 3.2))
    ax.scatter(d.btc_return, d.log_return, s=6, color=BLUE, alpha=0.25, linewidth=0)
    xs = np.linspace(d.btc_return.min(), d.btc_return.max(), 50)
    ax.plot(xs, r.params.iloc[0] + r.params.iloc[1] * xs, color=ORANGE, linewidth=2)
    ylim = 2.0
    n_out = int((d.log_return.abs() > ylim).sum())
    ax.set_ylim(-ylim, ylim)
    ax.text(0.03, 0.97, f"beta {r.params.iloc[1]:.2f}, R² {r.rsquared:.2f}\n"
            f"{len(d):,} DAO-months, {d.cc_symbol.nunique()} DAOs\n"
            f"{n_out} points outside the shown range", transform=ax.transAxes, va="top", fontsize=8, color=INK)
    ax.set_xlabel("BTC monthly log return")
    ax.set_ylabel("token monthly log return")
    _save(fig, "fig_h4_btc")


def run():
    cs = pd.read_csv(config.DATA_PROCESSED / "cross_section.csv")
    win = pd.read_csv(config.DATA_PROCESSED / "event_windows.csv")
    figure2(cs)
    figure3(win)
    fig_market_distributions(cs)
    fig_h1_scatter(cs)
    fig_h3_event_path(pd.read_csv(config.DATA_PROCESSED / "event_windows.csv"),
                      pd.read_csv(config.DATA_PROCESSED / "daily_returns.csv"))
    fig_h4_btc(pd.read_csv(config.DATA_PROCESSED / "monthly_returns.csv"), cs)
