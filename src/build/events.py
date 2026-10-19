"""B5: event panel for H3.

Event = end of the voting period of a proposal (UTC date of end_ts), restricted to
proposals whose vote concluded (canceled, draft, pending and active proposals are
not events). Window [-5, +5] calendar days; abnormal return = token - BTC daily log
return. Only windows with all 11 abnormal returns are used. Every proposal that
does not make it into the event sample is kept in events_all.csv with its reason.
"""
import pandas as pd

import config

EVENT_STATUSES = {"executed", "defeated", "succeeded", "queued", "expired", "pendingexecution",
                  "callexecuted", "crosschainexecuted"}


def build(proposals, daos, daily):
    lo, hi = config.EVENT_WINDOW
    p = proposals.merge(daos[["organization_id", "cc_symbol"]], on="organization_id", how="inner")
    p["event_date"] = pd.to_datetime(p.end_ts, utc=True, errors="coerce").dt.tz_localize(None).dt.normalize()

    p["drop_reason"] = ""
    p.loc[~p.status.isin(EVENT_STATUSES), "drop_reason"] = "vote not concluded (status " + p.status + ")"
    p.loc[(p.drop_reason == "") & p.event_date.isna(), "drop_reason"] = "no end timestamp"
    out_of_range = (p.event_date < pd.Timestamp(config.SAMPLE_START) + pd.Timedelta(days=-lo)) | \
                   (p.event_date > pd.Timestamp(config.SAMPLE_END_COLLECT) - pd.Timedelta(days=hi))
    p.loc[(p.drop_reason == "") & out_of_range, "drop_reason"] = "window outside sample period"

    d = daily[["cc_symbol", "date", "excess_return"]].dropna().copy()
    d["date"] = pd.to_datetime(d.date)
    ev = p[p.drop_reason == ""][["organization_id", "cc_symbol", "proposal_id", "event_date"]]
    grid = ev.merge(pd.DataFrame({"event_day": range(lo, hi + 1)}), how="cross")
    grid["date"] = grid.event_date + pd.to_timedelta(grid.event_day, unit="D")
    grid = grid.merge(d, on=["cc_symbol", "date"], how="left").rename(columns={"excess_return": "abnormal_return"})
    complete = grid.groupby("proposal_id").abnormal_return.transform("count") == (hi - lo + 1)
    p.loc[p.proposal_id.isin(grid[~complete].proposal_id), "drop_reason"] = "incomplete price data in [-5,+5] window"
    rows = grid[complete].to_dict("records")
    win = pd.DataFrame(rows)
    p["in_event_sample"] = p.drop_reason == ""
    p.drop(columns=["description"], errors="ignore").to_csv(config.DATA_PROCESSED / "events_all.csv", index=False)
    win.to_csv(config.DATA_PROCESSED / "event_windows.csv", index=False)
    return win, p
