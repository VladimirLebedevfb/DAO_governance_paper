"""B4: daily and monthly log returns from cached CryptoCompare histoday data.

Daily: r_t = ln(close_t / close_{t-1}) on consecutive calendar days (CryptoCompare
daily bars cover every day). Monthly: month-end close, log return between
consecutive month ends (the first month of each token has no return).
Excess return = token log return - BTC log return of the same day / month.
"""
import numpy as np
import pandas as pd

import config


def build(prices):
    """prices: date, close, volume_usd, cc_symbol (BTC included)."""
    p = prices.copy()
    p["date"] = pd.to_datetime(p["date"])
    p = p[(p.date >= config.SAMPLE_START) & (p.date <= config.SAMPLE_END_COLLECT)]
    p = p.sort_values(["cc_symbol", "date"])

    p["gap_days"] = p.groupby("cc_symbol").date.diff().dt.days
    p["log_return"] = np.log(p.close / p.groupby("cc_symbol").close.shift(1))
    p.loc[p.gap_days != 1, "log_return"] = np.nan  # no returns across missing days
    btc = p[p.cc_symbol == config.BENCHMARK][["date", "log_return"]].rename(columns={"log_return": "btc_return"})
    daily = p[p.cc_symbol != config.BENCHMARK].merge(btc, on="date", how="left")
    daily["excess_return"] = daily.log_return - daily.btc_return

    p["year_month"] = p.date.dt.to_period("M").astype(str)
    eom = p.groupby(["cc_symbol", "year_month"]).agg(close_eom=("close", "last"), last_day=("date", "max"),
                                                     n_days=("close", "size")).reset_index()
    eom["log_return"] = np.log(eom.close_eom / eom.groupby("cc_symbol").close_eom.shift(1))
    mb = eom[eom.cc_symbol == config.BENCHMARK][["year_month", "log_return"]].rename(columns={"log_return": "btc_return"})
    monthly = eom[eom.cc_symbol != config.BENCHMARK].merge(mb, on="year_month", how="left")
    monthly["excess_return"] = monthly.log_return - monthly.btc_return
    monthly = monthly.dropna(subset=["log_return"])

    cs = monthly.groupby("cc_symbol").agg(
        avg_log_return=("log_return", "mean"), avg_excess_return=("excess_return", "mean"),
        n_months=("log_return", "size"), first_month=("year_month", "min"),
        last_month=("year_month", "max")).reset_index()

    daily.to_csv(config.DATA_PROCESSED / "daily_returns.csv", index=False)
    monthly.to_csv(config.DATA_PROCESSED / "monthly_returns.csv", index=False)
    cs.to_csv(config.DATA_PROCESSED / "returns_cross_section.csv", index=False)
    return daily, monthly, cs
