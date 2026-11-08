"""Roster construction step 1: data-quality and first-look summary of data/cache/rosters/roster_db.json."""
from __future__ import annotations

import json
import os
import statistics as stx
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(ROOT, "data/cache/rosters/roster_db.json")))
P, prof = d["players"], d["profile"]
OSU = "M2 Oklahoma State University"

print("== Coverage by season (M1+M2 player-seasons) ==")
by_s = defaultdict(list)
for r in prof:
    by_s[r["season"]].append(r)
for s in d["seasons"]:
    rows = by_s[s]
    if not rows:
        continue
    teams = {r["team"] for r in rows}
    played = [r for r in rows if r["gp"] > 0]
    f = lambda k: sum(r[k] is not None for r in rows) / len(rows)
    print(f"{s}: {len(teams):3d} teams, {len(rows):5d} player-seasons ({len(played)} played), "
          f"birthdate/age {f('age'):.0%}, height {f('height_in'):.0%}, region known "
          f"{sum(r['region'] != 'Unknown' for r in rows) / len(rows):.0%}, stats-only (not on roster) "
          f"{sum(not r['on_roster'] for r in rows)}")

cur = d["seasons"][-1]
rows = [r for r in by_s[cur] if r["gp"] > 0]
print(f"\n== {cur}: ACHA background of players who have played ==")
for div in (1, 2):
    rr = [r for r in rows if r["div"] == div]
    n = len(rr)
    print(f"M{div}: n={n}  new to ACHA {sum(r['acha_seasons_before'] == 0 for r in rr) / n:.0%}  "
          f"transfer-in {sum(r['transfer_in'] for r in rr) / n:.0%}  any prior M1 {sum(r['m1_seasons_before'] > 0 for r in rr) / n:.0%}  "
          f"median age {stx.median(r['age'] for r in rr if r['age']):.1f}  regions {Counter(r['region'] for r in rr).most_common()}")

# M1 -> M2 movers this season
movers = Counter()
for r in rows:
    if r["div"] == 2 and r["m1_seasons_before"] > 0:
        movers[r["team"]] += 1
print("\nM2 teams with the most players who previously played M1:", movers.most_common(12))

print(f"\n== OSU {cur} ==")
for r in sorted([r for r in by_s[cur] if r["team"] == OSU], key=lambda r: -r["gp"]):
    print(f"  {P[r['pid']]['name']:22s} {r['pos']} gp {r['gp']:2d} age {r['age']} ACHA yrs {r['acha_seasons_before']} "
          f"M1 yrs {r['m1_seasons_before']} ({r['m1_gp_before']} gp) {r['region']:18s} prior {r['prior_programs']}")
