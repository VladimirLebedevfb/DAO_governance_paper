"""B2: sample universe and funnel for the new pipeline.

Unit of observation: a DAO = a governance token contract (chain, address) on a
mainnet chain. Organizations that share the token (e.g. Compound Alpha and
Compound Bravo) are merged into one DAO: its name is the member organization with
the most proposals, its events are the proposals of all member organizations.

Rules (the author delegated the universe choice, 2026-10-05):
  U1  all Tally organizations (sortBy popular), collected 2026-10
  U2  >= 1 proposal at organization level
  U3  not a test / mock / staging / deprecated organization (name or slug pattern)
  U3b governance token on a mainnet chain (testnet tokens have no market price)
  U4  fungible governance token (ERC20 / ERC20AAVE)
  U5  organizations sharing a token are merged into one DAO (logged, not dropped)
  U6  token ticker matched to CryptoCompare (ticker + name; see src/build/matching.py)
  U6b one contract per CryptoCompare ticker: when several DAOs' tokens map to the
      same ticker, the most popular DAO keeps it (copies, forks, bridged test tokens)
  U7  has a governor that uses the DAO token (after the governor crawl)
  U8  supply check passes (after the market snapshot; see matching.verify_supply)
Archived organizations are kept (dropping them would add survivorship bias) and flagged.
Every exclusion is written to reports/sample_funnel.csv with rule and reason.
"""
import re

import pandas as pd

import config

TEST_PATTERN = re.compile(r"(?:^|[-_ ])(?:test|mock|staging|deprecated|sandbox|demo|dryrun|goerli|sepolia|rinkeby|mumbai)|wrong", re.I)
FUNNEL = config.REPORTS / "sample_funnel.csv"
SUMMARY = config.TABLES / "sample_funnel_summary.csv"


def _row(rule, org_id, slug, sym, reason, status="excluded"):
    return {"rule": rule, "status": status, "organization_id": org_id, "slug": slug,
            "token_symbol": sym, "reason": reason}


def candidates():
    """U1-U6b, before the governor crawl."""
    orgs = pd.read_csv(config.DATA_INTERIM / "tally_organizations.csv").rename(
        columns={"id": "organization_id", "slug": "organization_slug", "name": "organization_name"})
    toks = pd.read_csv(config.DATA_INTERIM / "tally_tokens.csv")
    matches = pd.read_csv(config.DATA_INTERIM / "token_matches.csv")
    rows, n = [], [("U1 all organizations", len(orgs))]

    o = orgs[orgs.proposalsCount > 0]
    rows += [_row("U2", r.organization_id, r.organization_slug, None, "no proposals")
             for r in orgs[orgs.proposalsCount <= 0].itertuples()]
    n.append(("U2 with proposals", len(o)))
    test = o.organization_slug.astype(str).str.contains(TEST_PATTERN) | \
        o.organization_name.astype(str).str.contains(TEST_PATTERN)
    rows += [_row("U3", r.organization_id, r.organization_slug, None,
                  "test / mock / staging / deprecated organization (name pattern)") for r in o[test].itertuples()]
    o = o[~test]
    n.append(("U3 not test organizations", len(o)))

    t = toks[toks.organization_id.isin(o.organization_id)].copy()
    t_main = t[~t.token_chain.isin(config.TESTNET_CHAINS)]
    gone = o[~o.organization_id.isin(t_main.organization_id)]
    rows += [_row("U3b", r.organization_id, r.organization_slug, None, "governance token only on a testnet chain")
             for r in gone.itertuples()]
    o = o[o.organization_id.isin(t_main.organization_id)]
    n.append(("U3b token on a mainnet chain", len(o)))

    t_f = t_main[t_main.token_type.isin(["ERC20", "ERC20AAVE"])]
    gone = o[~o.organization_id.isin(t_f.organization_id)]
    rows += [_row("U4", r.organization_id, r.organization_slug, None, "no fungible ERC20 governance token")
             for r in gone.itertuples()]
    o = o[o.organization_id.isin(t_f.organization_id)]
    t_f = t_f[t_f.organization_id.isin(o.organization_id)]
    n.append(("U4 fungible token", len(o)))

    # U5: one DAO per token contract; members merged
    t_f = t_f.sort_values(["proposals_count", "popularity_rank"], ascending=[False, True])
    keepers = t_f.drop_duplicates(["token_chain", "token_address"]).copy()
    members = (t_f.groupby(["token_chain", "token_address"])
               .agg(member_org_ids=("organization_id", lambda s: ",".join(str(v) for v in s)),
                    member_slugs=("organization_slug", lambda s: ",".join(str(v) for v in s)),
                    n_member_orgs=("organization_id", "size"),
                    dao_best_rank=("popularity_rank", "min"),
                    dao_proposals_count=("proposals_count", "sum")).reset_index())
    keepers = keepers.merge(members, on=["token_chain", "token_address"])
    merged = t_f[~t_f.index.isin(keepers.index)]
    keeper_slug = keepers.set_index(["token_chain", "token_address"]).organization_slug
    rows += [_row("U5", r.organization_id, r.organization_slug, r.token_symbol,
                  f"same token as DAO {keeper_slug[(r.token_chain, r.token_address)]}; merged into it", "merged")
             for r in merged.itertuples()]
    n.append(("U5 DAOs (distinct mainnet token contracts)", len(keepers)))

    # U6: market data match
    keepers = keepers.merge(matches[["token_chain", "token_address", "match_status", "cc_symbol", "cc_name",
                                     "use_market_data"]], on=["token_chain", "token_address"], how="left")
    ok = keepers.use_market_data.fillna(False).astype(bool)
    reason = {"no_ticker": "ticker not listed in CryptoCompare",
              "not_trading": "CryptoCompare lists the ticker as not trading",
              "name_mismatch": "CryptoCompare ticker belongs to a different project (name mismatch)"}
    rows += [_row("U6", r.organization_id, r.organization_slug, r.token_symbol,
                  reason.get(r.match_status, str(r.match_status)) +
                  (f" (CryptoCompare {r.cc_symbol} = {r.cc_name})" if isinstance(r.cc_name, str) else ""))
             for r in keepers[~ok].itertuples()]
    cand = keepers[ok]
    n.append(("U6 ticker matched to CryptoCompare", len(cand)))

    # U6b: one contract per ticker (ties: more proposals, then Ethereum mainnet)
    cand = cand.assign(_eth=(cand.token_chain != "eip155:1")) \
        .sort_values(["dao_best_rank", "dao_proposals_count", "_eth"], ascending=[True, False, True]).drop(columns="_eth")
    dup = cand.duplicated("cc_symbol")
    first = cand[~dup].set_index("cc_symbol").organization_slug
    rows += [_row("U6b", r.organization_id, r.organization_slug, r.token_symbol,
                  f"ticker {r.cc_symbol} already used by the token of more popular DAO {first[r.cc_symbol]} "
                  f"(different contract: copy, fork or bridged token)") for r in cand[dup].itertuples()]
    cand = cand[~dup]
    n.append(("U6b one contract per ticker", len(cand)))

    pd.DataFrame(rows).to_csv(FUNNEL, index=False)
    pd.DataFrame(n, columns=["step", "n"]).to_csv(SUMMARY, index=False)
    cand.to_csv(config.DATA_INTERIM / "universe_candidates.csv", index=False)
    return cand


def candidate_member_orgs():
    cand = pd.read_csv(config.DATA_INTERIM / "universe_candidates.csv")
    return sorted({int(x) for v in cand.member_org_ids.astype(str) for x in v.split(",")})


def finalize():
    """U7 and governor selection, after the governor crawl of all member organizations."""
    cand = pd.read_csv(config.DATA_INTERIM / "universe_candidates.csv")
    gov = pd.read_csv(config.DATA_INTERIM / "tally_governors.csv")
    orgs = pd.read_csv(config.DATA_INTERIM / "tally_organizations.csv")
    funnel = pd.read_csv(FUNNEL)
    summary = pd.read_csv(SUMMARY)

    dao_cols = ["token_chain", "token_address", "organization_id", "organization_slug", "organization_name",
                "popularity_rank", "dao_best_rank", "dao_proposals_count", "member_org_ids", "member_slugs",
                "n_member_orgs", "token_symbol", "token_name", "cc_symbol", "cc_name", "match_status"]
    d = cand[dao_cols].rename(columns={"organization_id": "dao_org_id", "organization_slug": "dao_slug",
                                       "organization_name": "dao_name"})
    g = gov.drop(columns=["token_symbol", "token_name"], errors="ignore").merge(d, on=["token_chain", "token_address"])
    g = g[[str(o) in str(m).split(",") for o, m in zip(g.organization_id, g.member_org_ids)]].copy()
    g["dv"] = g.delegates_votes_raw.map(lambda x: float(x) if pd.notna(x) else 0.0)
    main = g.sort_values(["dao_org_id", "is_primary", "dv"], ascending=[True, False, False]) \
        .drop_duplicates("dao_org_id").copy()

    missing = cand[~cand.organization_id.isin(main.dao_org_id)]
    new_rows = [_row("U7", r.organization_id, r.organization_slug, r.token_symbol, "no governor uses the DAO token")
                for r in missing.itertuples()]
    archived = dict(zip(orgs.id, orgs.isArchived))
    main["dao_archived"] = main.dao_org_id.map(archived)
    main = main.rename(columns={"organization_id": "governor_org_id"})
    main["organization_id"] = main.dao_org_id  # analysis key

    prop_govs = g[["dao_org_id", "organization_id", "governor_id", "token_address", "cc_symbol"]] \
        .rename(columns={"organization_id": "governor_org_id"})
    prop_govs["organization_id"] = prop_govs.dao_org_id

    funnel = pd.concat([funnel, pd.DataFrame(new_rows)], ignore_index=True)
    funnel.to_csv(FUNNEL, index=False)
    summary = summary[~summary.step.str.startswith("U7")]
    summary = pd.concat([summary, pd.DataFrame([{"step": "U7 governor with the DAO token", "n": len(main)}])])
    summary.to_csv(SUMMARY, index=False)
    main.to_csv(config.DATA_INTERIM / "universe_daos.csv", index=False)
    prop_govs.to_csv(config.DATA_INTERIM / "universe_proposal_governors.csv", index=False)
    return main, prop_govs


def market_check():
    """U8: keep DAOs whose ticker match passes the supply check, or that the author
    accepted in config_decisions/token_match_decisions.csv (with a written reason)."""
    src = config.DATA_INTERIM / "universe_daos_pre_u8.csv"
    if not src.exists():
        pd.read_csv(config.DATA_INTERIM / "universe_daos.csv").to_csv(src, index=False)
    daos = pd.read_csv(src)
    ver = pd.read_csv(config.DATA_INTERIM / "token_matches_verified.csv")
    dec_path = config.ROOT / "config_decisions" / "token_match_decisions.csv"
    dec = pd.read_csv(dec_path) if dec_path.exists() else pd.DataFrame(columns=["token_address", "decision", "reason"])
    funnel = pd.read_csv(FUNNEL)
    summary = pd.read_csv(SUMMARY)

    v = ver.drop_duplicates(["token_chain", "token_address"])[
        ["token_chain", "token_address", "supply_check", "supply_ratio_cc_to_tally"]]
    d = daos.merge(v, on=["token_chain", "token_address"], how="left")
    accepted_by_author = d.token_address.isin(dec[dec.decision == "accept"].token_address)
    keep = d.supply_check.eq("ok") | accepted_by_author
    d["match_basis"] = "supply check passed"
    d.loc[accepted_by_author & ~d.supply_check.eq("ok"), "match_basis"] = "accepted by author (see token_match_decisions.csv)"

    rows = [_row("U8", r.dao_org_id, r.dao_slug, r.token_symbol,
                 f"ticker {r.cc_symbol} in CryptoCompare is {r.cc_name}, a different token: "
                 f"{r.supply_check} (CryptoCompare / Tally supply ratio {r.supply_ratio_cc_to_tally:.3g})")
            for r in d[~keep].itertuples()]
    funnel = pd.concat([funnel[funnel.rule != "U8"], pd.DataFrame(rows)], ignore_index=True)
    funnel.to_csv(FUNNEL, index=False)
    summary = summary[~summary.step.str.startswith("U8")]
    summary = pd.concat([summary, pd.DataFrame([{"step": "U8 match verified (supply or author)", "n": int(keep.sum())}])])
    summary.to_csv(SUMMARY, index=False)

    final = d[keep]
    final.to_csv(config.DATA_INTERIM / "universe_daos.csv", index=False)
    pg = pd.read_csv(config.DATA_INTERIM / "universe_proposal_governors.csv")
    pg[pg.dao_org_id.isin(final.dao_org_id)].to_csv(config.DATA_INTERIM / "universe_proposal_governors_final.csv", index=False)
    return final


def select_governors():
    """Governor used for delegates and quorum, chosen after the proposal crawl.

    Among governors of the DAO token (member organizations), excluding test governors:
    primary first, then largest delegatesVotesCount, then the most recent concluded
    proposal, then most proposals. Ties on the first two keys are common (all governors of
    one token report the same delegated votes), so the activity keys decide; before this
    rule the choice among ties was arbitrary (Compound picked its deprecated Alpha governor,
    Optimism a governor named "test"). Every change is logged.
    """
    from src.build.governance import CONCLUDED
    daos = pd.read_csv(config.DATA_INTERIM / "universe_daos.csv")
    gov = pd.read_csv(config.DATA_INTERIM / "tally_governors.csv")
    props = pd.read_csv(config.DATA_INTERIM / "tally_proposals.csv", usecols=["governor_id", "status", "end_ts"])
    props["end_dt"] = pd.to_datetime(props.end_ts, utc=True, errors="coerce")
    as_of = pd.Timestamp(config.COLLECTION_DATE, tz="UTC")
    last = props[props.status.isin(CONCLUDED) & (props.end_dt <= as_of)].groupby("governor_id").end_dt.max()

    dao_cols = [c for c in daos.columns if c not in gov.columns or c in ("token_chain", "token_address", "token_symbol", "token_name")]
    keep_cols = ["dao_org_id"] + [c for c in dao_cols if c not in ("dao_org_id",)]
    g = gov.drop(columns=["token_symbol", "token_name"], errors="ignore").merge(
        daos[keep_cols], on=["token_chain", "token_address"])
    g = g[[str(o) in str(m).split(",") for o, m in zip(g.organization_id, g.member_org_ids)]].copy()
    g = g[~g.governor_name.astype(str).str.contains(TEST_PATTERN)]
    g["dv"] = g.delegates_votes_raw.map(lambda x: float(x) if pd.notna(x) else 0.0)
    g["last_concluded"] = g.governor_id.map(last)
    g = g.sort_values(["dao_org_id", "is_primary", "dv", "last_concluded", "proposals_total"],
                      ascending=[True, False, False, False, False], na_position="last")
    new = g.drop_duplicates("dao_org_id").rename(columns={"organization_id": "governor_org_id"})
    new["organization_id"] = new.dao_org_id

    old = daos.set_index("dao_org_id")
    log = []
    for r in new.itertuples():
        before = old.loc[r.dao_org_id]
        if before.governor_id != r.governor_id:
            log.append({"dao_slug": r.dao_slug, "old_governor": f"{before.governor_name} ({before.governor_id})",
                        "new_governor": f"{r.governor_name} ({r.governor_id})",
                        "new_last_concluded": r.last_concluded, "new_proposals_total": r.proposals_total})
    pd.DataFrame(log, columns=["dao_slug", "old_governor", "new_governor", "new_last_concluded",
                               "new_proposals_total"]).to_csv(config.REPORTS / "governor_selection_changes.csv", index=False)
    new = new[[c for c in daos.columns if c in new.columns]]
    new.to_csv(config.DATA_INTERIM / "universe_daos.csv", index=False)
    return new, log
