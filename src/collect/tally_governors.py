"""C2: all governors (including inactive) of every organization with >= 1 proposal.

Output: data/interim/tally_governors.csv, one row per governor with its token.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config  # noqa: E402
from src.utils import http  # noqa: E402

QUERY = """
query Govs($input: GovernorsInput!) {
  governors(input: $input) {
    nodes { ... on Governor {
      id chainId name slug type kind isPrimary isIndexing isBehind quorum
      delegatesCount delegatesVotesCount tokenOwnersCount
      proposalStats { total active failed passed }
      parameters { quorumVotes quorumNumerator quorumDenominator votingDelay votingPeriod
                   proposalThreshold clockMode countingMode }
      token { id type name symbol supply decimals }
      contracts { governor { address type } tokens { address type } }
    } }
    pageInfo { lastCursor }
  }
}"""


QUERY_NO_STATS = QUERY.replace("proposalStats { total active failed passed }", "")


def parse_asset_id(asset_id):
    """'eip155:1/erc20:0xAbc' -> ('eip155:1', 'erc20', '0xabc')."""
    if not asset_id or "/" not in asset_id:
        return None, None, None
    chain, rest = asset_id.split("/", 1)
    std, _, addr = rest.partition(":")
    return chain, std, addr.lower()


def collect(orgs=None, tag=None):
    tag = tag or config.COLLECTION_TAG
    if orgs is None:
        orgs = pd.read_csv(config.DATA_INTERIM / "tally_organizations.csv")
    todo = orgs[orgs.proposalsCount > 0]
    rows, errors = [], []
    for i, o in enumerate(todo.itertuples(), 1):
        cursor = None
        for page in range(20):
            inp = {"filters": {"organizationId": str(o.id), "includeInactive": True},
                   "page": {"limit": 20}}
            if cursor:
                inp["page"]["afterCursor"] = cursor
            try:
                data = http.tally(f"govs_{tag}_{o.id}_p{page}", QUERY, {"input": inp})["governors"]
            except Exception as exc:
                # some chains no longer serve proposalStats ("chain id not supported"): retry without it
                try:
                    data = http.tally(f"govs_nostats_{tag}_{o.id}_p{page}", QUERY_NO_STATS, {"input": inp})["governors"]
                    errors.append({"organization_id": o.id, "slug": o.slug,
                                   "error": "proposalStats unavailable, collected without it"})
                except Exception as exc2:  # logged, not silently dropped
                    errors.append({"organization_id": o.id, "slug": o.slug, "error": str(exc2)[:300]})
                    break
            for g in data["nodes"]:
                tok = g.get("token") or {}
                chain, std, addr = parse_asset_id(tok.get("id"))
                par = g.get("parameters") or {}
                ps = g.get("proposalStats") or {}
                rows.append({
                    "organization_id": o.id, "organization_slug": o.slug, "organization_name": o.name,
                    "popularity_rank": o.popularity_rank,
                    "governor_id": g["id"], "governor_chain": g["chainId"], "governor_name": g["name"],
                    "governor_type": g["type"], "governor_kind": g["kind"], "is_primary": g["isPrimary"],
                    "is_indexing": g["isIndexing"], "is_behind": g["isBehind"],
                    "quorum_raw": g.get("quorum"),
                    "quorum_votes_param": par.get("quorumVotes"),
                    "quorum_numerator": par.get("quorumNumerator"),
                    "quorum_denominator": par.get("quorumDenominator"),
                    "voting_period": par.get("votingPeriod"), "clock_mode": par.get("clockMode"),
                    "counting_mode": par.get("countingMode"),
                    "proposal_threshold": par.get("proposalThreshold"),
                    "delegates_count": g["delegatesCount"],
                    "delegates_votes_raw": g["delegatesVotesCount"],
                    "token_owners_count": g["tokenOwnersCount"],
                    "proposals_total": ps.get("total"), "proposals_passed": ps.get("passed"),
                    "proposals_failed": ps.get("failed"), "proposals_active": ps.get("active"),
                    "token_id": tok.get("id"), "token_chain": chain, "token_standard": std,
                    "token_address": addr, "token_type": tok.get("type"), "token_symbol": tok.get("symbol"),
                    "token_name": tok.get("name"), "token_decimals": tok.get("decimals"),
                    "token_supply_raw": tok.get("supply"),
                })
            cursor = data["pageInfo"].get("lastCursor")
            if not data["nodes"] or not cursor:
                break
        if i % 50 == 0:
            print(f"  {i}/{len(todo)} organizations, {len(rows)} governors", flush=True)
    gov = pd.DataFrame(rows)
    gov.to_csv(config.DATA_INTERIM / "tally_governors.csv", index=False)
    pd.DataFrame(errors).to_csv(config.DATA_INTERIM / "tally_governors_errors.csv", index=False)
    return gov, errors


if __name__ == "__main__":
    g, e = collect()
    print(len(g), "governors;", g.organization_id.nunique(), "organizations;", len(e), "errors")
