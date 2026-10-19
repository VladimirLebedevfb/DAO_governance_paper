"""C6: delegates of selected governors, sorted by voting power (descending).

Collected beyond the thesis top-100 so that concentration measures can be checked
against coverage: pages of 20 until the cumulative votes reach
DELEGATE_COVERAGE_STOP of the governor's delegatesVotesCount, the votes drop to
zero, or DELEGATE_MAX delegates are collected.
Output: data/interim/tally_delegates.csv
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config  # noqa: E402
from src.utils import http  # noqa: E402

QUERY = """
query Dels($input: DelegatesInput!) {
  delegates(input: $input) {
    nodes { ... on Delegate { id votesCount delegatorsCount account { address name ens type } } }
    pageInfo { lastCursor }
  }
}"""


def collect(governors, tag=None):
    """governors: DataFrame with governor_id, organization_id, delegates_votes_raw."""
    tag = tag or config.COLLECTION_TAG
    rows, errors = [], []
    for i, g in enumerate(governors.itertuples(), 1):
        total = int(g.delegates_votes_raw) if pd.notna(g.delegates_votes_raw) else 0
        cum, cursor, n = 0, None, 0
        safe_id = g.governor_id.replace(":", "_")
        for page in range(config.DELEGATE_MAX // 20):
            inp = {"filters": {"governorId": g.governor_id}, "sort": {"sortBy": "votes", "isDescending": True},
                   "page": {"limit": 20}}
            if cursor:
                inp["page"]["afterCursor"] = cursor
            try:
                data = http.tally(f"dels_{tag}_{safe_id}_p{page:03d}", QUERY, {"input": inp})["delegates"]
            except Exception as exc:
                errors.append({"governor_id": g.governor_id, "page": page, "error": str(exc)[:300]})
                break
            stop = False
            for d in data["nodes"]:
                v = int(d["votesCount"])
                n += 1
                cum += v
                acc = d.get("account") or {}
                rows.append({"organization_id": g.organization_id, "governor_id": g.governor_id,
                             "rank": n, "delegate_id": d["id"], "address": (acc.get("address") or "").lower(),
                             "name": acc.get("name"), "account_type": acc.get("type"),
                             "votes_raw": str(v), "delegators_count": d.get("delegatorsCount")})
                if v == 0:
                    stop = True
            cursor = data["pageInfo"].get("lastCursor")
            if stop or not data["nodes"] or not cursor or (total > 0 and cum >= config.DELEGATE_COVERAGE_STOP * total):
                break
        if i % 10 == 0:
            print(f"  {i}/{len(governors)} governors, {len(rows)} delegate rows", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(config.DATA_INTERIM / "tally_delegates.csv", index=False)
    pd.DataFrame(errors).to_csv(config.DATA_INTERIM / "tally_delegates_errors.csv", index=False)
    return df, errors
