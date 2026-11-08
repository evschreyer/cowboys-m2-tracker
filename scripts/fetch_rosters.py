"""Roster construction, step 1: the ACHA roster layer (free HockeyTech feed only).

For every men's season since 2021-22 this pulls:
  * every M1/M2/M3 team roster (name, birthdate, hometown, size, position, ...)
  * league-wide skater and goalie stats (games played = usage weights; one row per player-team)

and writes data/cache/rosters/roster_db.json (gitignored; internal-first per the plan):
  players  {pid: bio}                      identity merged across duplicate HockeyTech ids (name + birthdate)
  stints   [{season, pid, team, div, gp, ...}]  one per player-team-season (roster or stats)
  profile  [{season, pid, team, ...}]      ACHA-internal pedigree for M1/M2 player-seasons:
           seasons/games in ACHA before this season, M1 seasons/games before, prior programs,
           transfer flag, age on Sept 1, height, home region.

Usage: python3 scripts/fetch_rosters.py [--refresh-current] [--seasons 2025-26,2026-27]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from engine.allgames import MEN_SEASONS, key, parse_team  # noqa: E402

CACHE = os.path.join(ROOT, "data/cache/rosters")
K = "key=e6867b36742a0c9d&client_code=acha&fmt=json&lang=en"
MK = "https://lscluster.hockeytech.com/feed/index.php?feed=modulekit&" + K
SV = ("https://lscluster.hockeytech.com/feed/index.php?feed=statviewfeed&key=e6867b36742a0c9d&client_code=acha"
      "&site_id=2&league_id=1&lang=en")
UA = {"User-Agent": "osu-m2-rankings/1.0"}
POSITIONS = {"F", "D", "G", "C", "LW", "RW", "W"}

US_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC "
                "ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())
CA_PROV = set("AB BC MB NB NL NS NT NU ON PE QC SK YT".split())
# traditional US hockey states (by youth/junior participation); everything else in the US = non-traditional
HOCKEY_STATES = set("MN MI MA WI NY IL PA CT NH VT ME RI ND NJ AK OH".split())


def get(url: str, tries: int = 3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                t = r.read().decode().strip()
            if t.startswith("(") and t.endswith(")"):
                t = t[1:-1]
            return json.loads(t)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 + 3 * i)


def cached(path: str, url: str, refresh: bool):
    if not refresh and os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    d = get(url)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(d, f)
    return d


def flat_people(x):
    for i in x if isinstance(x, list) else [x]:
        if isinstance(i, list):
            yield from flat_people(i)
        elif isinstance(i, dict) and i.get("person_id") and (i.get("position") or "") in POSITIONS:
            yield i


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def height_in(h: str) -> int | None:
    m = re.match(r"\s*(\d)\s*['\-]\s*(\d{1,2})", h or "")
    if not m:
        return None
    v = int(m.group(1)) * 12 + int(m.group(2))
    return v if 60 <= v <= 82 else None


def home_region(prov: str, cntry: str, placeholder: bool = False) -> str:
    """Region from province/state, falling back to country. `placeholder`: the team entered its own campus
    city (same city for 4+ roster players), so only a non-US country field is trusted."""
    p = (prov or "").strip().upper()
    c = (cntry or "").lower()
    if placeholder or (p in US_STATES and c and "united states" not in c):
        if "canada" in c:
            return "Canada"
        if c and "united states" not in c and c not in ("usa", "us"):
            return "International"
        if placeholder:
            return "Unknown"
    if p in CA_PROV:
        return "Canada"
    if p in US_STATES:
        return "US hockey state" if p in HOCKEY_STATES else "US non-traditional"
    if "canada" in c:
        return "Canada"
    if c and "united states" not in c and c not in ("usa", "us"):
        return "International"
    return "Unknown"


def fetch_season(season: str, sid: int, refresh: bool, pool: ThreadPoolExecutor):
    d = os.path.join(CACHE, str(sid))
    teams = cached(os.path.join(d, "teams.json"), f"{MK}&view=teamsbyseason&season_id={sid}", refresh)
    teams = teams["SiteKit"]["Teamsbyseason"]
    men = []
    for t in teams:
        div, school = parse_team(t["name"])
        if div:
            men.append((t["id"], div, school))

    def roster(t):
        tid = t[0]
        r = cached(os.path.join(d, f"roster_{tid}.json"), f"{MK}&view=roster&team_id={tid}&season_id={sid}", refresh)
        return t, list(flat_people(r["SiteKit"].get("Roster") or []))

    rosters = list(pool.map(roster, men))

    def stats(pos):
        rows, first = [], 0
        while True:
            p = os.path.join(d, f"stats_{pos}_{first}.json")
            u = (SV + f"&view=players&season={sid}&team=all&position={pos}&rookies=0&statsType=standard"
                 f"&rosterstatus=undefined&division=-1&conference=-1&sort=points&limit=5000&first={first}")
            page = cached(p, u, refresh)
            data = page[0]["sections"][0]["data"] if page else []
            rows += data
            if len(data) < 5000:
                return rows
            first += 5000

    sk, gk = pool.map(stats, ("skaters", "goalies"))
    return men, rosters, list(sk), list(gk)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-current", action="store_true", help="re-download the current season")
    ap.add_argument("--seasons", default=",".join(MEN_SEASONS))
    a = ap.parse_args()
    seasons = [s for s in MEN_SEASONS if s in a.seasons.split(",")]
    cur = list(MEN_SEASONS)[-1]

    raw_bio: dict[str, dict] = {}
    stints: dict[tuple, dict] = {}
    t0 = time.time()
    with ThreadPoolExecutor(6) as pool:
        for s in seasons:
            sid = MEN_SEASONS[s]
            men, rosters, sk, gk = fetch_season(s, sid, a.refresh_current and s == cur, pool)
            team_by_id = {tid: (div, school) for tid, div, school in men}
            n_players = 0
            for (tid, div, school), people in rosters:
                for p in people:
                    pid = str(p.get("player_id") or p.get("id"))
                    n_players += 1
                    raw_bio.setdefault(pid, {})
                    bio = raw_bio[pid]
                    # keep the most complete bio seen (later seasons overwrite blanks only)
                    for f in ("first_name", "last_name", "birthdate", "hometown", "homeprov", "homecntry",
                              "height", "weight", "position", "shoots", "catches"):
                        v = (p.get(f) or "").strip()
                        if v and not bio.get(f):
                            bio[f] = v
                    st = stints.setdefault((s, pid, tid), dict(season=s, pid=pid, team_id=tid, div=div,
                                                                team=key(div, school), gp=0, on_roster=True))
                    st["on_roster"] = True
                    st["pos"] = p.get("position")
                    st["home"] = ((p.get("hometown") or "").strip().lower(), (p.get("homeprov") or "").strip().upper(),
                                  (p.get("homecntry") or "").strip())
                    st["jersey"] = p.get("tp_jersey_number") or p.get("jersey_number")
            for rows, goalie in ((sk, False), (gk, True)):
                for r in rows:
                    row, prop = r["row"], r.get("prop", {})
                    tid = str(prop.get("team_name", {}).get("teamLink") or "")
                    if tid not in team_by_id:
                        continue
                    div, school = team_by_id[tid]
                    pid = str(row["player_id"])
                    raw_bio.setdefault(pid, {}).setdefault("first_name", row.get("name", ""))
                    st = stints.setdefault((s, pid, tid), dict(season=s, pid=pid, team_id=tid, div=div,
                                                                team=key(div, school), gp=0, on_roster=False))
                    gp = int(row.get("games_played") or 0)
                    if goalie:
                        st.update(pos="G", ggp=gp, gmin=int(row.get("minutes_played") or 0),
                                  ga=int(row.get("goals_against") or 0), sv=int(row.get("saves") or 0))
                        st["gp"] = max(st["gp"], gp)
                    else:
                        st.update(gp=max(st["gp"], gp), g=int(row.get("goals") or 0), a=int(row.get("assists") or 0),
                                  pim=int(row.get("penalty_minutes") or 0))
                        st.setdefault("pos", row.get("position"))
            print(f"{s}: {len(men)} teams, {n_players} roster spots, {len(sk)} skater + {len(gk)} goalie stat rows "
                  f"({time.time() - t0:.0f}s)", flush=True)

    # ---- merge duplicate HockeyTech ids for the same person (same normalized name + birthdate)
    canon: dict[str, str] = {}
    by_identity: dict[tuple, str] = {}
    for pid in sorted(raw_bio, key=int):
        b = raw_bio[pid]
        nm = norm_name(b.get("first_name", "") + b.get("last_name", ""))
        bd = b.get("birthdate", "")
        if nm and bd and bd > "1950":
            ident = (nm, bd)
            if ident in by_identity:
                canon[pid] = by_identity[ident]
                continue
            by_identity[ident] = pid
        canon[pid] = pid
    players = {}
    for pid, b in raw_bio.items():
        c = canon[pid]
        tgt = players.setdefault(c, {"ids": []})
        tgt["ids"].append(pid)
        for f, v in b.items():
            if v and not tgt.get(f):
                tgt[f] = v
    for pid, b in players.items():
        b["name"] = (f"{b.get('first_name', '')} {b.get('last_name', '')}").strip()
        b["height_in"] = height_in(b.get("height", ""))
        try:
            b["weight_lb"] = int(b.get("weight") or 0) or None
        except ValueError:
            b["weight_lb"] = None
        if b["weight_lb"] and not 120 <= b["weight_lb"] <= 300:
            b["weight_lb"] = None
        b["region"] = home_region(b.get("homeprov", ""), b.get("homecntry", ""))  # unadjusted fallback
    st_list = []
    merged: dict[tuple, dict] = {}
    for (s, pid, tid), st in stints.items():
        c = canon.get(pid, pid)
        k2 = (s, c, tid)
        if k2 in merged:
            m = merged[k2]
            m["gp"] = max(m["gp"], st["gp"])
            m["on_roster"] = m["on_roster"] or st["on_roster"]
            for f in ("g", "a", "pim", "ggp", "gmin", "ga", "sv"):
                if f in st:
                    m[f] = m.get(f, 0) + st[f]
            continue
        st = dict(st, pid=c)
        merged[k2] = st
        st_list.append(st)

    # ---- placeholder hometowns: a city/state shared by 4+ players on one team-season = the campus default
    city_count = defaultdict(int)
    for st in st_list:
        h = st.get("home")
        if h and h[0]:
            city_count[(st["season"], st["team"], h[0], h[1])] += 1

    # ---- ACHA-internal pedigree for each M1/M2 player-season
    order = {s: i for i, s in enumerate(MEN_SEASONS)}
    by_player = defaultdict(list)
    for st in st_list:
        by_player[st["pid"]].append(st)
    profile = []
    for pid, sts in by_player.items():
        sts.sort(key=lambda x: (order[x["season"]], -x["gp"]))
        b = players.get(pid, {})
        for st in sts:
            if st["div"] not in (1, 2) or st["season"] not in seasons:
                continue
            prior = [x for x in sts if order[x["season"]] < order[st["season"]]]
            played_prior = [x for x in prior if x["gp"] > 0 or x["on_roster"]]
            prior_programs = sorted({x["team"] for x in played_prior})
            same_school_prior = [x for x in played_prior if x["team"].split(" ", 1)[1] == st["team"].split(" ", 1)[1]]
            other_prior = [x for x in played_prior if x["team"].split(" ", 1)[1] != st["team"].split(" ", 1)[1]]
            m1_prior = [x for x in played_prior if x["div"] == 1]
            age = None
            if b.get("birthdate", "") > "1950":
                try:
                    bd = dt.date.fromisoformat(b["birthdate"][:10])
                    sept1 = dt.date(int(st["season"][:4]), 9, 1)
                    age = round((sept1 - bd).days / 365.25, 2)
                    if not 16 <= age <= 35:
                        age = None
                except ValueError:
                    pass
            profile.append(dict(
                season=st["season"], pid=pid, team=st["team"], div=st["div"], pos=st.get("pos") or b.get("position"),
                gp=st["gp"], ggp=st.get("ggp"), g=st.get("g"), a=st.get("a"), on_roster=st["on_roster"],
                acha_seasons_before=len({x["season"] for x in played_prior}),
                acha_gp_before=sum(x["gp"] for x in prior),
                m1_seasons_before=len({x["season"] for x in m1_prior if x["gp"] > 0}),
                m1_gp_before=sum(x["gp"] for x in m1_prior),
                prior_programs=prior_programs,
                transfer_in=bool(other_prior) and not any(order[x["season"]] == order[st["season"]] - 1 for x in same_school_prior),
                prior_other_programs=sorted({x["team"] for x in other_prior}),
                same_season_other_teams=sorted({x["team"] for x in sts if x["season"] == st["season"] and x is not st and (x["gp"] > 0)}),
                age=age, height_in=b.get("height_in"), weight_lb=b.get("weight_lb"),
                region=home_region(h[1], h[2], city_count[(st["season"], st["team"], h[0], h[1])] >= 4) if (h := st.get("home")) else b.get("region"),
                hometown=f"{h[0].title()}, {h[1]}" if h and h[0] else None,
            ))

    out = dict(built=dt.datetime.now().isoformat(timespec="seconds"), seasons=seasons,
               players=players, stints=st_list, profile=profile,
               notes=["2021-22 is the first season loaded, so 'before' counts for 2021-22/2022-23 are truncated."])
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, "roster_db.json"), "w") as f:
        json.dump(out, f)
    dup = sum(len(p["ids"]) > 1 for p in players.values())
    print(f"players {len(players)} (merged {dup} duplicate ids), stints {len(st_list)}, M1/M2 player-seasons {len(profile)}"
          f" -> data/cache/rosters/roster_db.json ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
