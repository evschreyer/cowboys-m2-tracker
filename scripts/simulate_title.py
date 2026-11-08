"""Simulate the rest of the 2026-27 M2 season through the national championship.

Each run:
  1. draws every team's "true" strength (shared-scale estimate +/- its uncertainty)
  2. plays every remaining M2-vs-M2 game through Feb 14 (home edge, game spread, OT -> one-goal win)
  3. computes final ACHA M2 regional rankings with the official formula (numpy version of engine.solve)
  4. Regionals (2026-27 format, Manual Part Five Art. V): top 2 per region go straight to Nationals;
     seeds 3-16 play a re-seeded single-elimination bracket; the two Day-3 winners advance
  5. Nationals: 4 per region re-ordered by final rank; pools per the manual's 2027 table (round robin,
     2 pts win / 1 tie, 10-min OT that can end tied); pool winners -> semis re-seeded by national
     rank (1v4, 2v3) -> final
Simplifications: league auto-bids, good-standing rulings and the Nationals host bye are not modeled;
teams scheduled for fewer than 16 M2 games are dropped from the postseason.
Also compares this OSU team with past M2 national champions on the shared scale.
Usage: python3 scripts/simulate_title.py [--sims 3000]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scripts")]

from build_case_study import short  # noqa: E402
from engine.allgames import MEN_SEASONS  # noqa: E402
from engine.engine import games_from_feed, load_feed, m2_name, plausible_final, solve  # noqa: E402
from engine.xdiv import FITTED, build_chain  # noqa: E402

SEASONS = list(MEN_SEASONS)
CUR = SEASONS[-1]
OSU = "Oklahoma State University"
REGIONS = ["Northeast", "Southeast", "Central", "West"]
FINAL_DAY = "2027-02-14"
MIN_M2 = 16
# Manual 2026-27, Part Five Art. V §1C (pool composition by region seed)
POOLS = {"A": [("Northeast", 1), ("Central", 2), ("Southeast", 3), ("West", 4)],
         "B": [("Central", 1), ("Northeast", 2), ("West", 3), ("Southeast", 4)],
         "C": [("Southeast", 1), ("West", 2), ("Northeast", 3), ("Central", 4)],
         "D": [("West", 1), ("Southeast", 2), ("Central", 3), ("Northeast", 4)]}
CHAMPIONS = {"2021-22": "University of Mary", "2022-23": "University of Massachusetts-Amherst",
             "2023-24": "Indiana University", "2024-25": "Lindenwood University",
             "2025-26": "Florida Gulf Coast University"}  # HockeyTech Nationals Final Four seasons 14, 27, 40, 58, 67


def jload(rel):
    with open(os.path.join(ROOT, rel)) as f:
        return json.load(f)


class FastM2:
    """ACHA M2 rating (GD cap 7, GP-weighted mean 7) by least squares; matches engine.solve when connected."""

    def __init__(self, teams):
        self.teams = teams
        self.ix = {t: i for i, t in enumerate(teams)}

    def solve(self, games):  # games: list of (home, away, hg, ag, ot)
        n = len(self.teams)
        L = np.zeros((n, n)); b = np.zeros(n); gp = np.zeros(n)
        w = np.zeros(n); l = np.zeros(n); otl = np.zeros(n)
        for h, a, hg, ag, ot in games:
            i, j = self.ix[h], self.ix[a]
            d = max(-7, min(7, hg - ag))
            L[i, i] += 1; L[j, j] += 1; L[i, j] -= 1; L[j, i] -= 1
            b[i] += d; b[j] -= d; gp[i] += 1; gp[j] += 1
            if hg > ag:
                w[i] += 1; l[j] += 1; otl[j] += ot
            elif ag > hg:
                w[j] += 1; l[i] += 1; otl[i] += ot
        A = np.vstack([L, gp]); rhs = np.concatenate([b, [7.0 * gp.sum()]])
        R = np.linalg.lstsq(A, rhs, rcond=None)[0]
        with np.errstate(divide="ignore", invalid="ignore"):
            otadj = np.where(gp > 0, 0.5 * otl / np.maximum(gp, 1), 0)
            awp = np.where(w + l > 0, 0.8 * w / np.maximum(w + l, 1), 0)
        return R + otadj + awp, gp


def play(rng, s_home, s_away, home_edge, sigma, allow_tie=False):
    """Return (home_goals, away_goals, ot) with a capped integer margin."""
    m = s_home - s_away + home_edge + sigma * rng.gauss(0, 1)
    d = int(round(m))
    if d == 0:
        if allow_tie and rng.random() < 0.5:
            return 0, 0, True
        d = 1 if m >= 0 else -1
        return (1, 0, True) if d > 0 else (0, 1, True)
    return (d, 0, False) if d > 0 else (0, -d, False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=3000)
    args = ap.parse_args()
    rng = random.Random(2027)

    cfg = jload(f"data/season_{CUR}.json")
    regions = jload(f"data/regions_{CUR}.json")["regions"]
    ov = jload(f"data/overrides_{CUR}.json")
    snap = jload("data/snapshots/latest.json")
    penalty = {t["team"]: t.get("penalty", 0) or 0 for t in snap["teams"]}
    ngs = set(ov.get("not_good_standing", []))
    feed = load_feed(os.path.join(ROOT, f"data/feeds/season{cfg['hockeytech']['season_id']}.json"))
    played, _ = games_from_feed(feed, FINAL_DAY, ov)
    played_ids = {g.id for g in played}
    today = dt.date.today().isoformat()
    remaining = []
    for g in feed:
        h, a = m2_name(g["home_team_name"]), m2_name(g["visiting_team_name"])
        if not h or not a or "TBD" in (h, a) or str(g["id"]) in played_ids or g["date_played"] > FINAL_DAY:
            continue
        if g["game_status"] in ("Postponed", "Cancelled", "Canceled") or "Forfeit" in g["game_status"]:
            continue
        if g["game_status"].startswith("Final") and plausible_final(g):
            continue
        remaining.append((h, a))
    teams = sorted({t for g in played for t in (g.home, g.away)} | {t for p in remaining for t in p} | set(regions))
    fast = FastM2(teams)

    # sanity: fast solver == engine on games played so far (where the schedule graph is connected per team)
    eng = solve(played)
    base_rows = [(g.home, g.away, g.hg, g.ag, g.ot) for g in played]
    fr, _ = fast.solve(base_rows)
    # postseason eligibility (scheduled M2 games through Feb 14)
    sched = Counter()
    for g in played:
        sched[g.home] += 1; sched[g.away] += 1
    for h, a in remaining:
        sched[h] += 1; sched[a] += 1
    eligible = {t for t in teams if sched[t] >= MIN_M2 and t not in ngs}

    # strengths and uncertainty from the cross-division model
    chain = build_chain(FITTED)
    m = chain[CUR]
    S = m.final(); gp = m.gp_before("2999-01-01")
    key = lambda t: "M2 " + t
    s_hat = {t: S.get(key(t), m.priors.get(key(t), m.div_prior.get(2, 0.0))) for t in teams}
    s_sd = {t: FITTED.sigma / math.sqrt(gp.get(key(t), 0) + FITTED.k) for t in teams}

    stats = defaultdict(Counter)
    region_rank = defaultdict(Counter)
    for _ in range(args.sims):
        true = {t: s_hat[t] + s_sd[t] * rng.gauss(0, 1) for t in teams}
        sim = list(base_rows)
        for h, a in remaining:
            hg, ag, ot = play(rng, true[h], true[a], FITTED.home_edge, FITTED.sigma)
            sim.append((h, a, hg, ag, ot))
        final, gps = fast.solve(sim)
        rating = {t: final[fast.ix[t]] - penalty.get(t, 0) for t in teams}
        by_region = {r: sorted([t for t in teams if regions.get(t) == r and t in eligible and gps[fast.ix[t]] >= 3],
                               key=lambda t: -rating[t]) for r in REGIONS}
        nats = {}
        for r, order in by_region.items():
            for i, t in enumerate(order[:20]):
                region_rank[t][i + 1] += 1
            for t in order[:2]:
                stats[t]["auto_bid"] += 1
            field = order[2:16]                       # seeds 3..16
            seed = {t: i + 3 for i, t in enumerate(field)}
            for t in field:
                stats[t]["regionals"] += 1
            day1 = [(field[i], field[len(field) - 1 - (i - 2)]) for i in range(2, 8)] if len(field) == 14 else []
            winners = []
            for a, b in day1:
                hg, ag, _ = play(rng, true[a], true[b], 0.0, FITTED.sigma)
                winners.append(a if hg > ag else b)
            alive = sorted(field[:2] + winners, key=lambda t: seed[t])      # 8 teams
            pairs = [(alive[0], alive[-1]), (alive[1], alive[-2]), (alive[2], alive[-3]), (alive[3], alive[-4])]
            r2 = []
            for a, b in pairs:
                hg, ag, _ = play(rng, true[a], true[b], 0.0, FITTED.sigma)
                r2.append(a if hg > ag else b)
            r2.sort(key=lambda t: seed[t])
            adv = []
            for a, b in ((r2[0], r2[3]), (r2[1], r2[2])):
                hg, ag, _ = play(rng, true[a], true[b], 0.0, FITTED.sigma)
                adv.append(a if hg > ag else b)
            for t in adv:
                stats[t]["regional_title"] += 1
            four = sorted(order[:2] + adv, key=lambda t: -rating[t])
            for i, t in enumerate(four):
                nats[(r, i + 1)] = t
                stats[t]["nationals"] += 1
        # pools
        pool_winners = []
        for _, members in POOLS.items():
            ts = [nats[k] for k in members]
            pts = Counter(); wins = Counter(); gd = Counter(); h2h = {}
            for i in range(4):
                for j in range(i + 1, 4):
                    a, b = ts[i], ts[j]
                    hg, ag, _ = play(rng, true[a], true[b], 0.0, FITTED.sigma, allow_tie=True)
                    if hg > ag:
                        pts[a] += 2; wins[a] += 1; h2h[(a, b)] = 1; h2h[(b, a)] = -1
                    elif ag > hg:
                        pts[b] += 2; wins[b] += 1; h2h[(a, b)] = -1; h2h[(b, a)] = 1
                    else:
                        pts[a] += 1; pts[b] += 1; h2h[(a, b)] = h2h[(b, a)] = 0
                    gd[a] += hg - ag; gd[b] += ag - hg
            best = max(pts.values() if pts else [0])
            tied = [t for t in ts if pts[t] == best]
            if len(tied) == 2:
                a, b = tied
                tied.sort(key=lambda t: (-h2h.get((t, b if t == a else a), 0), -wins[t], -gd[t], rng.random()))
            else:
                tied.sort(key=lambda t: (-wins[t], -gd[t], rng.random()))
            pool_winners.append(tied[0])
        for t in pool_winners:
            stats[t]["semis"] += 1
        sf = sorted(pool_winners, key=lambda t: -rating[t])
        finalists = []
        for a, b in ((sf[0], sf[3]), (sf[1], sf[2])):
            hg, ag, _ = play(rng, true[a], true[b], 0.0, FITTED.sigma)
            finalists.append(a if hg > ag else b)
        for t in finalists:
            stats[t]["final"] += 1
        hg, ag, _ = play(rng, true[finalists[0]], true[finalists[1]], 0.0, FITTED.sigma)
        stats[finalists[0] if hg > ag else finalists[1]]["champion"] += 1

    N = args.sims
    def row(t):
        st = stats[t]
        return dict(team=short("M2 " + t), region=regions.get(t), strength=round(s_hat[t], 2),
                    auto_bid=st["auto_bid"] / N, regionals=st["regionals"] / N, regional_title=st["regional_title"] / N,
                    nationals=st["nationals"] / N, semis=st["semis"] / N, final=st["final"] / N, champion=st["champion"] / N,
                    eligible=t in eligible, scheduled_m2=sched[t])
    contenders = sorted([t for t in teams if stats[t]["nationals"]], key=lambda t: -stats[t]["champion"])[:16]
    west = sorted([t for t in teams if regions.get(t) == "West" and stats[t]["nationals"] + stats[t]["regionals"]],
                  key=lambda t: (-stats[t]["nationals"], -stats[t]["auto_bid"]))[:12]
    osu_ranks = {k: v / N for k, v in sorted(region_rank[OSU].items())}

    # past champions on the shared scale (end of regular season)
    champs = []
    for s, t in CHAMPIONS.items():
        ms = chain[s]; f = ms.final(); g2 = ms.gp_before("2999-01-01")
        m1 = sorted([v + FITTED.gap_12 for k, v in f.items() if k.startswith("M1") and g2[k] >= 5], reverse=True)
        m2 = sorted([(v, k) for k, v in f.items() if k.startswith("M2") and g2[k] >= 5], reverse=True)
        v = f.get("M2 " + t)
        champs.append(dict(season=s, team=short("M2 " + t), strength=round(v, 2) if v is not None else None,
                           m2_rank=next((i + 1 for i, (_, k) in enumerate(m2) if k == "M2 " + t), None),
                           m1_equiv=sum(x > v for x in m1) + 1 if v is not None else None, anchored=s != SEASONS[0]))
    m1now = sorted([v + FITTED.gap_12 for k, v in S.items() if k.startswith("M1") and gp[k] >= 5], reverse=True)
    osu_now = dict(season=CUR, team="Oklahoma State", strength=round(s_hat[OSU], 2), m2_rank=1,
                   m1_equiv=sum(x > s_hat[OSU] for x in m1now) + 1, anchored=True, to_date=True)

    out = dict(generated_at=dt.datetime.now().isoformat(timespec="minutes"), sims=N, remaining_m2_games=len(remaining),
               osu=row(OSU), osu_west_rank=osu_ranks, contenders=[row(t) for t in contenders], west=[row(t) for t in west],
               champions=champs, osu_vs_champions=osu_now,
               solver_check=round(float(max(abs(fr[fast.ix[t]] - (eng[t].total + eng[t].otadj + eng[t].awp)) for t in eng)), 4),
               notes=["League auto-bids, good-standing rulings and the Nationals host bye are not modeled.",
                      f"Teams scheduled for fewer than {MIN_M2} M2 games through {FINAL_DAY} are excluded from the postseason."])
    path = os.path.join(ROOT, "data/title_odds.json")
    old = json.load(open(path)) if os.path.exists(path) else {}
    if {k: v for k, v in old.items() if k != "generated_at"} != json.loads(json.dumps({k: v for k, v in out.items() if k != "generated_at"})):
        with open(path, "w") as f:
            json.dump(out, f, indent=1)
    o = out["osu"]
    print(f"{N} sims, {len(remaining)} remaining M2 games; solver check max diff {out['solver_check']}")
    print(f"OSU: top-2 West {o['auto_bid']:.1%}, nationals {o['nationals']:.1%}, semis {o['semis']:.1%}, final {o['final']:.1%}, title {o['champion']:.1%}")
    print("title odds:", [(r["team"], r["region"], f"{r['champion']:.1%}") for r in out["contenders"][:8]])
    print("champions:", [(c["season"], c["team"], c["strength"], c["m2_rank"], c["m1_equiv"]) for c in champs], "| OSU now", osu_now)


if __name__ == "__main__":
    main()
