"""B1: match Tally governance tokens to CryptoCompare.

The CryptoCompare coin list no longer exposes contract addresses (checked
2026-10-05), so matching is by exact ticker and then verified by name:
  matched_verified        ticker and name agree
  name_mismatch           ticker exists in CryptoCompare but the project name differs
                          (e.g. LEND = old Aave/ETHLend, not Lendefi DAO); needs a decision
  not_trading             CryptoCompare lists the ticker as not trading
  no_ticker               ticker not in CryptoCompare
  not_erc20               token is not a fungible ERC20 (NFT voting etc.)
Decisions on name mismatches live in config/token_match_decisions.csv
(token_address, cc_symbol, decision, reason), written by the author, never by code.
"""
import re

import pandas as pd

import config

STOP = {"token", "tokens", "dao", "governance", "protocol", "finance", "network", "the", "coin",
        "community", "foundation", "labs", "v2", "v3", "old", "new"}


def _norm(s):
    words = re.findall(r"[a-z0-9]+", str(s or "").lower())
    return [w for w in words if w not in STOP]


def name_agrees(tally_names, cc_name):
    cc = _norm(cc_name)
    if not cc:
        return False
    cc_join = "".join(cc)
    for n in tally_names:
        t = _norm(n)
        if not t:
            continue
        t_join = "".join(t)
        if t_join == cc_join or t_join in cc_join or cc_join in t_join or set(t) & set(cc):
            return True
    return False


def build(tokens=None, coins=None):
    """tokens: organization x token table from src/collect/tally_tokens.py."""
    tokens = tokens if tokens is not None else pd.read_csv(config.DATA_INTERIM / "tally_tokens.csv")
    coins = coins if coins is not None else pd.read_csv(config.DATA_INTERIM / "cc_coinlist.csv")
    coins["sym_u"] = coins.cc_symbol.astype(str).str.upper()
    cc = coins.drop_duplicates("sym_u").set_index("sym_u")

    toks = (tokens.dropna(subset=["token_address"])
            .groupby(["token_chain", "token_address"], as_index=False)
            .agg(token_symbol=("token_symbol", "first"), token_name=("token_name", "first"),
                 token_type=("token_type", "first"),
                 organizations=("organization_slug", lambda s: "|".join(sorted({str(v) for v in s.dropna()}))),
                 organization_names=("organization_name", lambda s: "|".join(sorted({str(v) for v in s.dropna()}))),
                 best_rank=("popularity_rank", "min"), proposals_total=("proposals_count", "sum")))

    rows = []
    for t in toks.itertuples():
        sym = "" if pd.isna(t.token_symbol) else str(t.token_symbol).upper()
        rec = {"cc_symbol": None, "cc_name": None, "cc_is_trading": None}
        if t.token_type not in ("ERC20", "ERC20AAVE"):
            status = "not_erc20"
        elif sym not in cc.index:
            status = "no_ticker"
        else:
            c = cc.loc[sym]
            rec = {"cc_symbol": c.cc_symbol, "cc_name": c.cc_name, "cc_is_trading": c.cc_is_trading}
            names = [t.token_name] + str(t.organization_names).split("|")
            if not bool(c.cc_is_trading):
                status = "not_trading"
            elif name_agrees(names, c.cc_name):
                status = "matched_verified"
            else:
                status = "name_mismatch"
        rows.append({**t._asdict(), **rec, "match_status": status})
    out = pd.DataFrame(rows).drop(columns=["Index"])

    dec_path = config.ROOT / "config_decisions" / "token_match_decisions.csv"
    if dec_path.exists():
        dec = pd.read_csv(dec_path)
        out = out.merge(dec[["token_address", "decision", "reason"]], on="token_address", how="left")
    else:
        out["decision"], out["reason"] = None, None
    out["use_market_data"] = (out.match_status == "matched_verified") | (out.decision == "accept")
    out = out.sort_values(["use_market_data", "proposals_total"], ascending=[False, False])
    out.to_csv(config.DATA_INTERIM / "token_matches.csv", index=False)
    return out


if __name__ == "__main__":
    m = build()
    print(m.match_status.value_counts().to_string())


def verify_supply(matches=None, snapshot=None, tokens=None, lo=0.5, hi=2.0):
    """Second check after pricemultifull: Tally total supply vs CryptoCompare SUPPLY.

    A ticker and name can agree by accident (e.g. two unrelated tokens called GAS);
    the on-chain supply of the Tally token rarely does. Ratios outside [lo, hi] are
    flagged supply_mismatch and need an author decision; missing CryptoCompare
    supply is flagged supply_unknown (not an exclusion by itself).
    """
    matches = matches if matches is not None else pd.read_csv(config.DATA_INTERIM / "token_matches.csv")
    snapshot = snapshot if snapshot is not None else pd.read_csv(config.DATA_INTERIM / "cc_market_snapshot.csv")
    tokens = tokens if tokens is not None else pd.read_csv(config.DATA_INTERIM / "tally_tokens.csv")
    meta = tokens.drop_duplicates(["token_chain", "token_address"])[
        ["token_chain", "token_address", "token_decimals", "token_supply_raw"]]
    m = matches.merge(meta, on=["token_chain", "token_address"], how="left").merge(
        snapshot[["cc_symbol", "supply", "circulating_supply", "mktcap", "price", "volume_24h_usd", "lastupdate"]],
        on="cc_symbol", how="left")

    def tally_supply(r):
        try:
            return int(str(r.token_supply_raw).split(".")[0]) / 10 ** int(r.token_decimals)
        except (TypeError, ValueError):
            return float("nan")

    m["tally_supply"] = m.apply(tally_supply, axis=1)
    m["supply_ratio_cc_to_tally"] = m.supply / m.tally_supply
    m["supply_check"] = "ok"
    m.loc[m.supply.isna() | (m.supply <= 0) | m.tally_supply.isna(), "supply_check"] = "supply_unknown"
    bad = (m.supply_check == "ok") & ((m.supply_ratio_cc_to_tally < lo) | (m.supply_ratio_cc_to_tally > hi))
    m.loc[bad, "supply_check"] = "supply_mismatch"
    m.to_csv(config.DATA_INTERIM / "token_matches_verified.csv", index=False)
    return m
