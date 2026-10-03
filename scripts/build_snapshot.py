"""Fetch the HockeyTech feed and build a dated rankings snapshot for the dashboard.

Usage: python3 scripts/build_snapshot.py [--no-fetch] [--through YYYY-MM-DD]
Writes data/snapshots/<date>.json and data/snapshots/latest.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.engine import (FINAL_STATUSES, FORFEIT_STATUSES, components, forfeit_penalties, games_from_feed,  # noqa: E402
                           load_feed, m2_name, rank, solve, to_dict)

SEASON = "2026-27"
# Projection model, calibrated on 2024-25 -> 2025-26 (see research/FINDINGS.md section 5)
MODEL = dict(prior_slope=0.733, ridge_k=3, new_team_k=1, home_edge=0.24, game_sd=2.6, new_team_prior=6.5)


def jload(rel):
    with open(os.path.join(ROOT, rel)) as f:
        return json.load(f)


def fetch_feed(cfg: dict, dest: str) -> None:
    url = cfg["hockeytech"]["url"].format(**cfg["hockeytech"])
    req = urllib.request.Request(url, headers={"User-Agent": "osu-m2-rankings/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    json.loads(data)  # validate before overwriting
    with open(dest, "wb") as f:
        f.write(data)


def priors() -> dict[str, float]:
    """Last season's final ACHA ratings, regressed toward average (see data/priors_2026-27.json "source")."""
    return jload(f"data/priors_{SEASON}.json")["priors"]


def game_state(status: str) -> str:
    if status in FINAL_STATUSES:
        return "final"
    if status in FORFEIT_STATUSES:
        return "forfeit"
    if status in ("Postponed", "Suspended", "Cancelled", "Canceled"):
        return "postponed"
    return "scheduled"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--through", help="only count games on/before this date (default: all completed)")
    args = ap.parse_args()

    cfg = jload(f"data/season_{SEASON}.json")
    regions = jload(f"data/regions_{SEASON}.json")["regions"]
    ov = jload(f"data/overrides_{SEASON}.json")
    feed_path = os.path.join(ROOT, f"data/feeds/season{cfg['hockeytech']['season_id']}.json")
    if not args.no_fetch:
        fetch_feed(cfg, feed_path)
    feed = load_feed(feed_path)
    now = dt.datetime.now()
    through = args.through or "9999-12-31"

    games, forfeits = games_from_feed(feed, through, ov)
    teams = solve(games)
    # every team in the region map appears, even before its first game
    pen = forfeit_penalties(forfeits)
    pen.update(ov.get("penalties", {}))
    ranked = rank(teams, regions, pen, set(ov.get("not_good_standing", [])))

    # Previous snapshot (for movement)
    snap_dir = os.path.join(ROOT, "data/snapshots")
    os.makedirs(snap_dir, exist_ok=True)
    prev = None
    olds = sorted(p for p in glob.glob(os.path.join(snap_dir, "20*.json")) if os.path.basename(p)[:10] < now.strftime("%Y-%m-%d"))
    if olds:
        with open(olds[-1]) as f:
            prev = json.load(f)
    prev_rank = {t["team"]: t["rank"] for t in prev["teams"]} if prev else {}

    alias = ov.get("aliases", {})
    # Exactly the games the engine counted (overrides applied), so the browser engine reproduces it.
    counted = [dict(id=g.id, date=g.date, home=g.home, away=g.away, hg=g.hg, ag=g.ag, ot=g.ot, so=g.so, tie=g.tie)
               for g in sorted(games, key=lambda g: g.date)]
    upcoming = []  # remaining M2-vs-M2 games through the final ranking date (what-if / projections)
    final_through = cfg["ranking_periods"][-1]["through"]
    focus = cfg["focus_team"]
    focus_all = []  # every ACHA game for the focus team (M2 and cross-division)
    counted_ids = {g.id for g in games}
    for g in feed:
        h, a = m2_name(g["home_team_name"]), m2_name(g["visiting_team_name"])
        st = game_state(g["game_status"])
        if st == "scheduled" and g["date_played"] < now.strftime("%Y-%m-%d"):
            st = "unreported"  # date has passed but no final score in the feed yet
        if (h and a and "TBD" not in (h, a) and st in ("scheduled", "postponed", "unreported")
                and g["date_played"] <= final_through and g["id"] not in counted_ids):
            h, a = alias.get(h, h), alias.get(a, a)
            upcoming.append(dict(id=g["id"], date=g["date_played"], home=h, away=a, state=st))
        names = (g["home_team_name"], g["visiting_team_name"])
        if f"MD2 {focus}" in names:
            home = names[0] == f"MD2 {focus}"
            opp = names[1] if home else names[0]
            gf, ga = (g["home_goal_count"], g["visiting_goal_count"]) if home else (g["visiting_goal_count"], g["home_goal_count"])
            focus_all.append(dict(id=g["id"], date=g["date_played"], opponent=opp, home=home, gf=int(gf), ga=int(ga),
                                  state=st, status=g["game_status"], m2=opp.startswith("MD2 "),
                                  acha=opp[:3] in ("MD1", "MD2", "MD3"), counted=g["id"] in counted_ids))

    elig = cfg["eligibility"]
    f_m2 = [x for x in focus_all if x["m2"] and x["date"] <= elig["by"]]
    f_acha = [x for x in focus_all if x["acha"] and x["date"] <= elig["by"]]
    eligibility = dict(
        m2_played=sum(x["state"] == "final" for x in f_m2),
        m2_scheduled=sum(x["state"] == "scheduled" for x in f_m2),
        m2_postponed=sum(x["state"] == "postponed" for x in f_m2),
        m2_unreported=sum(x["state"] == "unreported" for x in f_m2),
        acha_played=sum(x["state"] == "final" for x in f_acha),
        acha_scheduled=sum(x["state"] == "scheduled" for x in f_acha),
        **elig)

    comp = components(teams)
    team_rows = []
    for reg, lst in ranked.items():
        for r in lst:
            d = to_dict(r)
            d["prev_rank"] = prev_rank.get(r.team)
            d["group"] = comp[r.team]
            d["linked_to_focus"] = comp[r.team] == comp.get(focus)
            team_rows.append(d)
    played = {r["team"] for r in team_rows}
    for t, reg in regions.items():  # teams with no M2 games yet
        if t not in played:
            team_rows.append(dict(team=t, region=reg, gp=0, rank=None, status="no_games"))

    snap = dict(
        season=SEASON, generated_at=now.isoformat(timespec="minutes"), through=args.through,
        last_game_date=max((g.date for g in games), default=None),
        engine=dict(cap=7, start=7.0, ot_adj=0.5, awp_weight=0.8), model=MODEL, priors=priors(),
        config=cfg, teams=team_rows, games=counted, upcoming=sorted(upcoming, key=lambda x: x['date']), focus_games=focus_all, eligibility=eligibility,
        forfeits=forfeits, suggested_penalties=forfeit_penalties(forfeits),
        overrides_notes=ov.get("notes", []),
        counts=dict(groups=len(set(comp.values())), m2_games_counted=len(games), m2_games_upcoming=len(upcoming), teams=len(team_rows)))
    snap["data_hash"] = hashlib.sha256(json.dumps([snap["games"], snap["upcoming"], snap["teams"], snap["focus_games"]],
                                                  sort_keys=True).encode()).hexdigest()[:16]
    out = os.path.join(snap_dir, f"{now:%Y-%m-%d}.json")
    for p in (out, os.path.join(snap_dir, "latest.json")):
        with open(p, "w") as f:
            json.dump(snap, f, separators=(",", ":"))
    fr = next(r for r in team_rows if r["team"] == focus)
    print(f"snapshot {out}: {len(games)} M2 games counted, {len(team_rows)} teams")
    print(f"{focus}: {fr.get('region')} #{fr.get('rank')} final {fr.get('final', 0):.3f} "
          f"({fr.get('w')}-{fr.get('l')}, GmPerf {fr.get('gmperf', 0):.2f}, Sched {fr.get('sched', 0):.2f})")
    print("eligibility:", eligibility)


if __name__ == "__main__":
    main()
