"""Per-game box-score stats from HockeyTech game summaries (shots, special teams, periods, goalies).

Raw summaries are cached in data/cache/summaries/<game_id>.json (git-ignored, re-downloadable).
Compact stats are written to data/game_stats/<season>.json (committed) by scripts/fetch_game_stats.py.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data/cache/summaries")
URL = ("https://lscluster.hockeytech.com/feed/index.php?feed=statviewfeed&view=gameSummary&game_id={gid}"
       "&key=e6867b36742a0c9d&site_id=2&client_code=acha&lang=en&league_id=1")
MIN_SHOTS = 10  # a team total below this (or below its goals) means shots weren't tracked


def fetch_summary(gid: str, pause: float = 0.25) -> dict:
    path = os.path.join(CACHE, f"{gid}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    req = urllib.request.Request(URL.format(gid=gid), headers={"User-Agent": "osu-m2-rankings/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                t = r.read().decode().strip()
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    if t.startswith("("):
        t = t[1:-1]
    d = json.loads(t)
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w") as f:
        json.dump(d, f)
    time.sleep(pause)
    return d


def _side(team: dict) -> dict:
    s = team.get("stats", {})
    goalies = []
    for g in team.get("goalieLog", []) or []:
        gs = g.get("stats", {})
        goalies.append(dict(name=f"{g['info'].get('firstName', '')} {g['info'].get('lastName', '')}".strip(),
                            toi=gs.get("timeOnIce"), sa=gs.get("shotsAgainst"), ga=gs.get("goalsAgainst"),
                            sv=gs.get("saves")))
    return dict(goals=s.get("goals"), shots=s.get("shots"), ppg=s.get("powerPlayGoals"),
                ppo=s.get("powerPlayOpportunities"), pim=s.get("penaltyMinuteCount"), goalies=goalies)


def compact(d: dict) -> dict:
    """Summary JSON -> small dict. shots_ok is False when shots weren't really tracked."""
    h, v = _side(d["homeTeam"]), _side(d["visitingTeam"])
    periods = [dict(label=p.get("info", {}).get("longName"), hg=int(p["stats"].get("homeGoals") or 0),
                    vg=int(p["stats"].get("visitingGoals") or 0), hs=int(p["stats"].get("homeShots") or 0),
                    vs=int(p["stats"].get("visitingShots") or 0)) for p in d.get("periods", [])]
    shots_ok = all((x["shots"] or 0) >= max(MIN_SHOTS, (x["goals"] or 0) + 1) for x in (h, v))
    det = d.get("details", {})
    return dict(id=str(det.get("id")), date=det.get("date"), venue=det.get("venue"),
                attendance=det.get("attendance"), home=h, away=v, periods=periods,
                shootout=bool(d.get("hasShootout")), shots_ok=shots_ok)
