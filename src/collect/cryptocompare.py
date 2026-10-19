"""C3-C5: CryptoCompare coin list, current market data, daily price history.

The key allows 100 calls per month, so every function here is budget-aware:
plan() reports the calls a step needs before anything is spent, cached
responses are never requested again, and histoday makes a second (older)
call for a token only when the first one does not reach SAMPLE_START.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config  # noqa: E402
from src.utils import http  # noqa: E402

FSYMS_MAX_CHARS = 290  # pricemultifull accepts ~300 characters of fsyms


def remaining_budget():
    return config.CC_MONTHLY_BUDGET - http.cc_calls_this_month()


# ---------------------------------------------------------------- C3 coin list
def coinlist():
    """Full coin list with SmartContractAddress / BuiltOn (1 call, cached)."""
    data = http.cryptocompare("coinlist", "/data/all/coinlist", {})
    rows = []
    for sym, c in (data.get("Data") or {}).items():
        rows.append({
            "cc_symbol": c.get("Symbol") or sym, "cc_id": c.get("Id"), "cc_name": c.get("CoinName"),
            "cc_fullname": c.get("FullName"), "cc_contract": (c.get("SmartContractAddress") or "").strip().lower(),
            "cc_built_on": c.get("BuiltOn"), "cc_platform_type": c.get("PlatformType"),
            "cc_is_trading": c.get("IsTrading"), "cc_launch_date": c.get("AssetLaunchDate"),
        })
    df = pd.DataFrame(rows)
    df.to_csv(config.DATA_INTERIM / "cc_coinlist.csv", index=False)
    return df


# ---------------------------------------------------------------- C4 current market data
def _chunks(symbols):
    chunk, length = [], 0
    for s in symbols:
        if chunk and length + len(s) + 1 > FSYMS_MAX_CHARS:
            yield chunk
            chunk, length = [], 0
        chunk.append(s)
        length += len(s) + 1
    if chunk:
        yield chunk


def pricemultifull(symbols):
    symbols = sorted(set(symbols))
    rows = []
    for i, chunk in enumerate(_chunks(symbols)):
        data = http.cryptocompare(f"pricemultifull_{config.COLLECTION_TAG}_{i:02d}_{chunk[0]}",
                                  "/data/pricemultifull", {"fsyms": ",".join(chunk), "tsyms": "USD"})
        for sym, d in (data.get("RAW") or {}).items():
            u = d.get("USD") or {}
            rows.append({"cc_symbol": sym, "price": u.get("PRICE"), "mktcap": u.get("MKTCAP"),
                         "circulating_supply": u.get("CIRCULATINGSUPPLY"), "supply": u.get("SUPPLY"),
                         "volume_24h_usd": u.get("VOLUME24HOURTO"), "lastupdate": u.get("LASTUPDATE"),
                         "market": u.get("LASTMARKET")})
    df = pd.DataFrame(rows)
    if len(df):
        df["lastupdate"] = pd.to_datetime(df["lastupdate"], unit="s", utc=True)
    df.to_csv(config.DATA_INTERIM / "cc_market_snapshot.csv", index=False)
    return df


# ---------------------------------------------------------------- C5 daily history
def _ts(day):
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())


def histoday(symbol):
    """Daily USD close from SAMPLE_START to SAMPLE_END_COLLECT (1 or 2 calls)."""
    start, end = _ts(config.SAMPLE_START), _ts(config.SAMPLE_END_COLLECT)
    frames, to_ts = [], end
    for part in range(2):
        data = http.cryptocompare(f"histoday_{config.COLLECTION_TAG}_{symbol}_{part}", "/data/v2/histoday",
                                  {"fsym": symbol, "tsym": "USD", "limit": 2000, "toTs": to_ts})
        pts = pd.DataFrame((data.get("Data") or {}).get("Data") or [])
        if pts.empty:
            break
        frames.append(pts)
        first = pts["time"].min()
        # stop when the window already reaches the sample start or the token did not trade earlier
        if first <= start or (pts.sort_values("time").iloc[0]["close"] == 0):
            break
        to_ts = int(first) - 86400
    if not frames:
        return pd.DataFrame(columns=["date", "close", "volume_usd", "cc_symbol"])
    df = pd.concat(frames).drop_duplicates("time").sort_values("time")
    df = df[(df.time >= start) & (df.time <= end)]
    df["date"] = pd.to_datetime(df["time"], unit="s").dt.date
    df = df[df["close"] > 0]
    out = df[["date", "close", "volumeto"]].rename(columns={"volumeto": "volume_usd"})
    out["cc_symbol"] = symbol
    return out


def plan(symbols, histories_needed_two=0):
    n_pmf = len(list(_chunks(sorted(set(symbols)))))
    need = n_pmf + len(symbols) + histories_needed_two
    return {"pricemultifull_calls": n_pmf, "histoday_calls_min": len(symbols),
            "total_min": need, "remaining_budget": remaining_budget()}
