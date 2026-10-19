"""C7: all proposals of selected governors, with quorum, vote totals, voters,
start and end, lifecycle events and title/description.

Output: data/interim/tally_proposals.csv (one row per proposal; vote types in columns)
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config  # noqa: E402
from src.utils import http  # noqa: E402

QUERY = """
query Props($input: ProposalsInput!) {
  proposals(input: $input) {
    nodes { ... on Proposal {
      id onchainId status quorum createdAt chainId
      governor { id }
      start { ... on Block { number timestamp } ... on BlocklessTimestamp { timestamp } }
      end { ... on Block { number timestamp } ... on BlocklessTimestamp { timestamp } }
      voteStats { type votesCount votersCount percent }
      events { type createdAt }
      metadata { title description }
    } }
    pageInfo { lastCursor }
  }
}"""

QUERY_NO_BLOCKS = QUERY.replace(
    "start { ... on Block { number timestamp } ... on BlocklessTimestamp { timestamp } }", "").replace(
    "end { ... on Block { number timestamp } ... on BlocklessTimestamp { timestamp } }", "")
# when Tally cannot resolve blocks on a chain ("chain id is not supported"), the end of
# voting is taken from the first outcome event (succeeded / defeated / expired / queued)
OUTCOME_EVENTS = ["succeeded", "defeated", "expired", "queued", "executed"]

VOTE_TYPES = ["for", "against", "abstain"]


def collect(governors, tag=None):
    """governors: DataFrame with governor_id, organization_id."""
    tag = tag or config.COLLECTION_TAG
    rows, errors = [], []
    for i, g in enumerate(governors.itertuples(), 1):
        cursor = None
        safe_id = g.governor_id.replace(":", "_")
        for page in range(500):
            inp = {"filters": {"governorId": g.governor_id, "includeArchived": True},
                   "sort": {"sortBy": "id", "isDescending": True}, "page": {"limit": 20}}
            if cursor:
                inp["page"]["afterCursor"] = cursor
            no_blocks = False
            try:
                data = http.tally(f"props_{tag}_{safe_id}_p{page:03d}", QUERY, {"input": inp})["proposals"]
            except Exception as exc:
                try:
                    data = http.tally(f"props_noblocks_{tag}_{safe_id}_p{page:03d}", QUERY_NO_BLOCKS,
                                      {"input": inp})["proposals"]
                    no_blocks = True
                except Exception as exc2:
                    errors.append({"governor_id": g.governor_id, "page": page, "error": str(exc2)[:300]})
                    break
            for p in data["nodes"]:
                vs = {s["type"]: s for s in (p.get("voteStats") or [])}
                ev = {e["type"]: e["createdAt"] for e in (p.get("events") or [])}
                md = p.get("metadata") or {}
                row = {"organization_id": g.organization_id, "governor_id": g.governor_id,
                       "proposal_id": p["id"], "onchain_id": p.get("onchainId"), "status": p["status"],
                       "quorum_raw": p.get("quorum"), "created_at": p.get("createdAt"),
                       "start_ts": (p.get("start") or {}).get("timestamp"),
                       "start_block": (p.get("start") or {}).get("number"),
                       "end_ts": (p.get("end") or {}).get("timestamp"),
                       "end_block": (p.get("end") or {}).get("number"),
                       "title": md.get("title"), "description": md.get("description")}
                for t in VOTE_TYPES:
                    row[f"{t}_votes_raw"] = (vs.get(t) or {}).get("votesCount")
                    row[f"{t}_voters"] = (vs.get(t) or {}).get("votersCount")
                for t in ["queued", "executed", "canceled", "defeated", "succeeded", "expired"]:
                    row[f"event_{t}"] = ev.get(t)
                row["end_ts_source"] = "proposal end"
                if no_blocks:
                    row["end_ts"] = next((ev[t] for t in OUTCOME_EVENTS if ev.get(t)), None)
                    row["end_ts_source"] = "first outcome event (chain blocks not served)"
                rows.append(row)
            cursor = data["pageInfo"].get("lastCursor")
            if not data["nodes"] or not cursor:
                break
        if i % 10 == 0:
            print(f"  {i}/{len(governors)} governors, {len(rows)} proposals", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(config.DATA_INTERIM / "tally_proposals.csv", index=False)
    pd.DataFrame(errors).to_csv(config.DATA_INTERIM / "tally_proposals_errors.csv", index=False)
    return df, errors
