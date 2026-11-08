"""Build data for the "OSU at Ohio" case study page (data/case_study_ohio.json).

Everything is computed from the HockeyTech feed + cached box scores:
  - M1 rank of the M1 team AT GAME TIME for every M1-vs-M2 game since 2021-22
    (our reconstruction of ACHA's M1 computer ranking from games before that date; teams with
    fewer than 5 M1 games use the previous season's final rank)
  - M2 win rates by M1 tier with bootstrap 95% intervals
  - pre-game win probabilities from the calibrated cross-division model (engine/xdiv.py)
  - leaderboard of M2 wins over top-10 M1 teams, biggest upsets first
  - the Ohio series: box scores vs each team's season averages, goaltending counterfactual
Usage: python3 scripts/build_case_study.py [--refresh]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import random
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.allgames import MEN_SEASONS, XGame, games, load_feed  # noqa: E402
from engine.gamestats import compact, fetch_summary  # noqa: E402
from engine.m1rank import m1_games, ranking  # noqa: E402
from engine.xdiv import FITTED, build_chain  # noqa: E402

SEASONS = list(MEN_SEASONS)
OSU, OHIO = "M2 Oklahoma State University", "M1 Ohio University"
SERIES = ["31985", "31986"]
TIERS = [("Top 5", 1, 5), ("6-10", 6, 10), ("11-25", 11, 25), ("26+", 26, 999)]
MIN_M1_GP = 5


def short(t: str) -> str:
    n = t[3:] if t[:2] in ("M1", "M2", "M3") else t
    for a, b in (("University of ", ""), (" University", ""), ("The ", ""), (" College", "")):
        n = n.replace(a, b)
    return n


def m1_rank_at_game_time(all_games: dict[str, list]) -> dict[str, dict]:
    """game id -> {rank, source} for the M1 team in each M1-M2 game."""
    out, prev_final = {}, {}
    for s in SEASONS:
        G = all_games[s]
        m1 = [g for g in G if g.hdiv == 1 and g.adiv == 1]
        cross = [g for g in G if {g.hdiv, g.adiv} == {1, 2}]
        cache = {}
        for g in cross:
            if g.date not in cache:
                rows = ranking(m1_games([x for x in m1 if x.date < g.date])) if any(x.date < g.date for x in m1) else []
                cache[g.date] = {r.team: r for r in rows}
            team = (g.home if g.hdiv == 1 else g.away)[3:]
            r = cache[g.date].get(team)
            if r and r.gp >= MIN_M1_GP:
                out[g.id] = dict(rank=r.rank, source="current")
            elif team in prev_final:
                out[g.id] = dict(rank=prev_final[team], source="last season final")
            else:
                out[g.id] = dict(rank=None, source="unranked")
        prev_final = {r.team: r.rank for r in ranking(m1_games(m1))}
    return out


def bootstrap_ci(ys: list[float], n: int = 4000, seed: int = 7) -> tuple[float, float]:
    rng = random.Random(seed)
    k = len(ys)
    means = sorted(sum(rng.choice(ys) for _ in range(k)) / k for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n)]


def team_season_profile(team: str, season_games: list, stats: dict, exclude: set[str]) -> dict:
    """Per-game averages from box scores (shots only where tracked)."""
    gf = ga = ga_t = sf = sa = ppg = ppo = ppga = ppoa = n = ns = 0
    for g in season_games:
        if team not in (g.home, g.away) or g.id in exclude or g.id not in stats:
            continue
        st = stats[g.id]
        me, opp = (st["home"], st["away"]) if g.home == team else (st["away"], st["home"])
        n += 1
        gf += me["goals"] or 0; ga += opp["goals"] or 0
        ppg += me["ppg"] or 0; ppo += me["ppo"] or 0; ppga += opp["ppg"] or 0; ppoa += opp["ppo"] or 0
        if st["shots_ok"]:
            ns += 1; sf += me["shots"]; sa += opp["shots"]; ga_t += opp["goals"] or 0
    return dict(games=n, gf=gf / n, ga=ga / n, shots_for=sf / ns if ns else None, shots_against=sa / ns if ns else None,
                shot_share=sf / (sf + sa) if ns else None, save_pct=1 - ga_t / sa if sa else None,
                pp_pct=ppg / ppo if ppo else None, pk_pct=1 - ppga / ppoa if ppoa else None, shot_games=ns)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download the current season feed first")
    args = ap.parse_args()

    all_games = {s: games(s, refresh=args.refresh and s == SEASONS[-1]) for s in SEASONS}
    chain = build_chain(FITTED)
    ranks = m1_rank_at_game_time(all_games)

    # ---- every M1-vs-M2 game with rank-at-game-time and pre-game model probability
    rows = []
    for s in SEASONS:
        m = chain[s]
        for g in all_games[s]:
            if {g.hdiv, g.adiv} != {1, 2}:
                continue
            m2_home = g.hdiv == 2
            m2, m1 = (g.home, g.away) if m2_home else (g.away, g.home)
            m2g, m1g = (g.hg, g.ag) if m2_home else (g.ag, g.hg)
            pr = m.predict(g)
            p_m2 = pr["p_home"] if m2_home else 1 - pr["p_home"]
            res = "W" if m2g > m1g else "L" if m2g < m1g else "T"
            rk = ranks.get(g.id, {})
            rows.append(dict(id=g.id, season=s, date=g.date, m2=short(m2), m1=short(m1), m2_home=m2_home,
                             m2_goals=m2g, m1_goals=m1g, ot=g.ot, result=res, m1_rank=rk.get("rank"),
                             margin_m2=round(pr["margin"] if m2_home else -pr["margin"], 3),
                             strength_gap=round((pr["s_home"] - pr["s_away"]) * (1 if m2_home else -1), 3),
                             rank_source=rk.get("source"), p_m2=round(p_m2, 4),
                             surprise_bits=round(-math.log2(p_m2), 3) if res == "W" else None,
                             osu=OSU in (g.home, g.away), ohio_series=g.id in SERIES))

    # ---- tiers (exclude the Ohio series itself so the base rate is "before this weekend")
    base_rows = [r for r in rows if not r["ohio_series"]]
    tiers = []
    for name, lo, hi in TIERS:
        rr = [r for r in base_rows if r["m1_rank"] and lo <= r["m1_rank"] <= hi]
        ys = [1.0 if r["result"] == "W" else 0.5 if r["result"] == "T" else 0.0 for r in rr]
        w = sum(r["result"] == "W" for r in rr); l = sum(r["result"] == "L" for r in rr); t = len(rr) - w - l
        lo_ci, hi_ci = bootstrap_ci(ys) if ys else (None, None)
        tiers.append(dict(tier=name, n=len(rr), w=w, l=l, t=t, win_rate=w / len(rr) if rr else None,
                          ci=[lo_ci, hi_ci], mean_model_p=sum(r["p_m2"] for r in rr) / len(rr) if rr else None))
    overall = [r for r in base_rows]
    overall_rate = sum(r["result"] == "W" for r in overall) / len(overall)

    # ---- leaderboard: M2 wins over a top-10 M1 team (at game time), lowest pre-game probability first
    board = sorted([r for r in rows if r["result"] == "W" and r["m1_rank"] and r["m1_rank"] <= 10],
                   key=lambda r: r["p_m2"])
    for i, r in enumerate(board):
        r["upset_rank"] = i + 1

    # ---- OSU vs M1 this season
    cur = SEASONS[-1]
    osu_m1 = [r for r in rows if r["osu"] and r["season"] == cur]
    p_all = math.prod((r["p_m2"] for r in osu_m1 if r["result"] == "W")) if osu_m1 and all(r["result"] == "W" for r in osu_m1) else None

    # ---- the series: box scores vs season averages
    stats = json.load(open(os.path.join(ROOT, f"data/game_stats/{cur}.json")))
    G = all_games[cur]
    series = []
    for gid in SERIES:
        g = next((x for x in G if x.id == gid), None)
        r = next((x for x in rows if x["id"] == gid), None)
        if not g:  # not final yet: pre-game odds from everything played so far
            raw = next(x for x in load_feed(cur) if str(x["id"]) == gid)
            home_osu = raw["home_team_name"].endswith("Oklahoma State University")
            pending = XGame(gid, cur, raw["date_played"], OSU if home_osu else OHIO, OHIO if home_osu else OSU,
                            2 if home_osu else 1, 1 if home_osu else 2, 0, 0, False, False)
            pr = chain[cur].predict(pending)
            series.append(dict(id=gid, final=False, date=raw["date_played"], status=raw["game_status"],
                               p_osu=round(pr["p_home"] if home_osu else 1 - pr["p_home"], 4)))
            continue
        if gid not in stats:
            stats[gid] = compact(fetch_summary(gid))
            with open(os.path.join(ROOT, f"data/game_stats/{cur}.json"), "w") as f:
                json.dump(dict(sorted(stats.items())), f, separators=(",", ":"))
        st = stats[gid]
        osu_side, ohio_side = (st["away"], st["home"]) if g.away == OSU else (st["home"], st["away"])
        series.append(dict(id=gid, final=True, date=g.date, osu=osu_side, ohio=ohio_side, periods=st["periods"],
                           osu_home=g.home == OSU, venue=st.get("venue"), attendance=st.get("attendance"),
                           p_osu=r["p_m2"] if r else None, result=r["result"] if r else None, m1_rank=r["m1_rank"] if r else None))
    excl = set(SERIES)
    prof = dict(osu=team_season_profile(OSU, G, stats, excl), ohio=team_season_profile(OHIO, G, stats, excl))
    for s_ in series:
        if s_.get("final") and prof["osu"]["save_pct"] is not None and s_["ohio"]["shots"]:
            s_["expected_ga_at_season_sv"] = round(s_["ohio"]["shots"] * (1 - prof["osu"]["save_pct"]), 2)
            s_["expected_gf_at_ohio_sv"] = round(s_["osu"]["shots"] * (1 - prof["ohio"]["save_pct"]), 2) if prof["ohio"]["save_pct"] else None

    # ---- where OSU stands now
    m = chain[cur]
    s_now = m.final()
    gp = m.gp_before("2999-01-01")
    m1_adj = sorted([(v + FITTED.gap_12, t) for t, v in s_now.items() if t.startswith("M1") and gp[t] >= 3], reverse=True)
    osu_pos = sum(v > s_now[OSU] for v, _ in m1_adj) + 1
    guest = ranking(m1_games(G, extra=[g for g in G if OSU in (g.home, g.away) and {g.hdiv, g.adiv} == {1, 2}]))
    guest_row = next(r for r in guest if r.team == OSU[3:])
    official_ohio = 3  # ACHA M1 Computer Ranking #5 (thru 11/1/26), data/official/m1/2026-27

    out = dict(
        generated_at=dt.datetime.now().isoformat(timespec="minutes"),
        model=dict(params=FITTED.__dict__, calibration=json.load(open(os.path.join(ROOT, "data/xdiv_model.json")))),
        base_rate=dict(tiers=tiers, overall_m2_win_rate=overall_rate, n=len(overall),
                       seasons=f"{SEASONS[0]} to {cur}", min_m1_gp=MIN_M1_GP),
        leaderboard=board, osu_vs_m1=osu_m1, p_osu_perfect_vs_m1=p_all, series=series, profiles=prof,
        standing=dict(osu_strength=s_now[OSU], m1_scale_rank=osu_pos, m1_teams=len(m1_adj),
                      m1_top=[dict(team=short(t), strength=round(v, 2)) for v, t in m1_adj[:10]],
                      guest_rank=guest_row.rank, guest_teams=len(guest), guest_record=[guest_row.w, guest_row.l, guest_row.t],
                      ohio_official_rank=official_ohio),
        all_m1_m2_games=len(rows),
    )
    path = os.path.join(ROOT, "data/case_study_ohio.json")
    old = json.load(open(path)) if os.path.exists(path) else {}
    if {k: v for k, v in old.items() if k != "generated_at"} == json.loads(json.dumps({k: v for k, v in out.items() if k != "generated_at"})):
        print("case study unchanged; keeping existing file")
    else:
        with open(path, "w") as f:
            json.dump(out, f, indent=1)
    print(f"{len(rows)} M1-M2 games; overall M2 win rate {overall_rate:.1%}")
    for t in tiers:
        print(f"  vs M1 {t['tier']:6s} n={t['n']:3d} {t['w']}-{t['l']}-{t['t']} win {t['win_rate']:.1%} "
              f"CI {t['ci'][0]:.1%}-{t['ci'][1]:.1%}  model avg {t['mean_model_p']:.1%}")
    print("Top upsets (M2 over top-10 M1):")
    for r in board[:8]:
        print(f"  #{r['upset_rank']} {r['date']} {r['m2']} {r['m2_goals']}-{r['m1_goals']} {'vs' if r['m2_home'] else 'at'} "
              f"#{r['m1_rank']} {r['m1']}  P={r['p_m2']:.0%}")
    print("Series:", [(s_.get("id"), s_.get("result"), s_.get("p_osu")) for s_ in series])
    print(f"OSU: M1-scale #{osu_pos}/{len(m1_adj)}, guest #{guest_row.rank}; P(perfect vs M1) {p_all}")


if __name__ == "__main__":
    main()
