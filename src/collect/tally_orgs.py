"""C1: all Tally (Cactus) organizations, sorted by popularity.

Pages of 20 (API maximum) are cached under data/raw/tally/. The popularity rank
is the position in this list at collection time.
Output: data/interim/tally_organizations.csv
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config  # noqa: E402
from src.utils import http  # noqa: E402

QUERY = """
query Orgs($input: OrganizationsInput!) {
  organizations(input: $input) {
    nodes { ... on Organization {
      id slug name chainIds tokenIds governorIds hasActiveProposals isArchived
      proposalsCount delegatesCount delegatesVotesCount tokenOwnersCount
    } }
    pageInfo { lastCursor }
  }
}"""


def collect(max_pages=5000, tag=None):
    tag = tag or config.COLLECTION_TAG
    rows, cursor = [], None
    for page in range(max_pages):
        inp = {"page": {"limit": 20}, "sort": {"sortBy": "popular", "isDescending": True}}
        if cursor:
            inp["page"]["afterCursor"] = cursor
        data = http.tally(f"orgs_{tag}_p{page:04d}", QUERY, {"input": inp})["organizations"]
        nodes = data["nodes"]
        rows.extend(nodes)
        cursor = data["pageInfo"].get("lastCursor")
        if page % 25 == 0:
            print(f"  page {page}: {len(rows)} orgs", flush=True)
        if not nodes or not cursor:
            break
    df = pd.DataFrame(rows)
    df.insert(0, "popularity_rank", range(1, len(df) + 1))
    for c in ["chainIds", "tokenIds", "governorIds"]:
        df[f"n_{c}"] = df[c].apply(len)
        df[c] = df[c].apply(lambda v: ",".join(v))
    df = df.drop_duplicates("id")
    df.to_csv(config.DATA_INTERIM / "tally_organizations.csv", index=False)
    return df


if __name__ == "__main__":
    d = collect()
    print(len(d), "organizations;", (d.proposalsCount > 0).sum(), "with proposals;",
          (d.isArchived).sum(), "archived")
