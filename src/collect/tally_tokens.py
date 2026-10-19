"""C1b: token metadata for every token of the organizations that pass U2-U3.

Uses the batch query tokens(input: {ids: [...]}) so that market-data matching can
run before the expensive per-organization governor, delegate and proposal crawls.
Output: data/interim/tally_tokens.csv (one row per organization x token).
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config  # noqa: E402
from src.utils import http  # noqa: E402

QUERY = """
query Toks($input: TokensInput!) {
  tokens(input: $input) { id type name symbol decimals supply }
}"""
BATCH = 50


def parse_asset_id(asset_id):
    chain, rest = asset_id.split("/", 1)
    std, _, addr = rest.partition(":")
    return chain, std, addr.lower()


def collect(orgs, tag=None):
    tag = tag or config.COLLECTION_TAG
    pairs = [(o.id, o.slug, o.name, o.popularity_rank, o.proposalsCount, t)
             for o in orgs.itertuples() for t in str(o.tokenIds).split(",") if t and t != "nan"]
    ids = sorted({p[-1] for p in pairs})
    meta, errors = {}, []
    for i in range(0, len(ids), BATCH):
        if i % 500 == 0:
            print(f"  tokens {i}/{len(ids)}", flush=True)
        chunk = ids[i:i + BATCH]
        try:
            data = http.tally(f"tokens_{tag}_{i:05d}", QUERY, {"input": {"ids": chunk}})["tokens"]
            for t in data:
                meta[t["id"]] = t
        except Exception as exc:  # retry one by one so a bad id does not drop the batch
            for tid in chunk:
                try:
                    t = http.tally(f"token_{tag}_{tid.replace(':', '_').replace('/', '_')}", QUERY,
                                   {"input": {"ids": [tid]}})["tokens"]
                    if t:
                        meta[tid] = t[0]
                except Exception as exc2:
                    errors.append({"token_id": tid, "error": str(exc2)[:200]})
    rows = []
    for org_id, slug, name, rank, nprop, tid in pairs:
        m = meta.get(tid, {})
        chain, std, addr = parse_asset_id(tid)
        rows.append({"organization_id": org_id, "organization_slug": slug, "organization_name": name,
                     "popularity_rank": rank, "proposals_count": nprop, "token_id": tid,
                     "token_chain": chain, "token_standard": std, "token_address": addr,
                     "token_type": m.get("type"), "token_symbol": m.get("symbol"), "token_name": m.get("name"),
                     "token_decimals": m.get("decimals"), "token_supply_raw": m.get("supply")})
    df = pd.DataFrame(rows)
    df.to_csv(config.DATA_INTERIM / "tally_tokens.csv", index=False)
    pd.DataFrame(errors).to_csv(config.DATA_INTERIM / "tally_tokens_errors.csv", index=False)
    return df, errors
