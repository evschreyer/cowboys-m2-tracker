"""Exploration: how statistically exceptional is OSU's 2026-27 season? (research, not a page builder)

Builds a table of every ACHA men's team-season since 2021-22 (all divisions) and compares OSU with it,
both full-season and "through the first N games" (N = OSU's games so far) so a partial season is
compared fairly. Writes research/out/significance_explore.json and prints the headline numbers.
"""
from __future__ import annotations

import json
import math
import os
import statistics
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scripts")]

from engine.allgames import MEN_SEASONS  # noqa: E402
from engine.xdiv import FITTED, build_chain, p_home_win  # noqa: E402

SEASONS = list(MEN_SEASONS)
CUR = SEASONS[-1]
OSU = "M2 Oklahoma State University"


def team_games(ms):
    by = defaultdict(list)
    for g in ms.games:
        for me, opp, gf, ga, home in ((g.home, g.away, g.hg, g.ag, True), (g.away, g.home, g.ag, g.hg, False)):
            by[me].append(dict(g=g, opp=opp, gf=gf, ga=ga, home=home))
    for v in by.values():
        v.sort(key=lambda x: (x["g"].date, x["g"].id))
    return by


def summarize(rows):
    n = len(rows)
    w = sum(r["gf"] > r["ga"] for r in rows); l = sum(r["gf"] < r["ga"] for r in rows)
    gf = sum(r["gf"] for r in rows); ga = sum(r["ga"] for r in rows)
    cgd = sum(max(-7, min(7, r["gf"] - r["ga"])) for r in rows)
    streak = best = 0
    for r in rows:
        streak = streak + 1 if r["gf"] > r["ga"] else 0
        best = max(best, streak)
    shut = sum(r["ga"] == 0 for r in rows)
    return dict(gp=n, w=w, l=l, t=n - w - l, winpct=(w + 0.5 * (n - w - l)) / n, gf=gf / n, ga=ga / n, gd=(gf - ga) / n,
                cgd=cgd / n, best_streak=best, shutouts=shut, one_goal_or_less_losses=sum(0 < r["ga"] - r["gf"] <= 1 for r in rows))


def main():
    chain = build_chain(FITTED)
    osu_rows = None
    table = []
    for s in SEASONS:
        ms = chain[s]
        tg = team_games(ms)
        final = ms.final()
        div_means = {d: statistics.mean(v for t, v in final.items() if t.startswith(f"M{d}") and len(tg.get(t, [])) >= 5) for d in (1, 2, 3)}
        for t, rows in tg.items():
            if len(rows) < 5:
                continue
            full = summarize(rows)
            # performance vs pre-game expectation (capped margin residual), every game
            resid, exp_w, act_w = [], 0.0, 0.0
            for r in rows:
                pr = ms.predict(r["g"])
                m = pr["margin"] if r["home"] else -pr["margin"]
                p = pr["p_home"] if r["home"] else 1 - pr["p_home"]
                resid.append(max(-7, min(7, r["gf"] - r["ga"])) - m)
                exp_w += p; act_w += (r["gf"] > r["ga"]) + 0.5 * (r["gf"] == r["ga"])
            z = sum(resid) / (FITTED.sigma * math.sqrt(len(resid)))
            row = dict(season=s, team=t, div=int(t[1]), strength=final.get(t), rel_div=final.get(t, 0) - div_means[int(t[1])],
                       resid_per_game=sum(resid) / len(resid), resid_z=z, wins_above=act_w - exp_w, **full)
            table.append(row)
            if t == OSU and s == CUR:
                osu_rows = rows
    n_osu = len(osu_rows)

    # through the first N games (N = OSU's games so far): records + strength as of that date
    early = []
    for s in SEASONS:
        ms = chain[s]
        tg = team_games(ms)
        for t, rows in tg.items():
            if len(rows) < n_osu or int(t[1]) != 2:
                continue
            cut = rows[:n_osu]
            after = cut[-1]["g"].date
            # strength using only games through that date (day after the Nth game)
            import datetime as dt
            nxt = (dt.date.fromisoformat(after) + dt.timedelta(days=1)).isoformat()
            st = ms.strengths_before(nxt)
            early.append(dict(season=s, team=t, strength_at_n=st.get(t), **summarize(cut)))

    out = dict(n_osu=n_osu, table=table, early=early)
    os.makedirs(os.path.join(ROOT, "research/out"), exist_ok=True)
    with open(os.path.join(ROOT, "research/out/significance_explore.json"), "w") as f:
        json.dump(out, f, default=float)

    def rank_of(rows, key, team=OSU, season=CUR, reverse=True):
        srt = sorted(rows, key=lambda r: r[key], reverse=reverse)
        i = next(i for i, r in enumerate(srt) if r["team"] == team and r["season"] == season)
        return i + 1, len(srt), srt[:5]

    m2 = [r for r in table if r["div"] == 2]
    allr = table
    print(f"OSU games so far: {n_osu}")
    osu = next(r for r in table if r["team"] == OSU and r["season"] == CUR)
    print("OSU 2026-27:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in osu.items() if k != "team"})
    for key, lab in (("strength", "shared-scale strength"), ("rel_div", "strength above own division avg"), ("cgd", "capped GD/game"),
                     ("gd", "GD/game"), ("ga", "GA/game (low)"), ("winpct", "win %"), ("resid_z", "beating expectations (z)"),
                     ("wins_above", "wins above expectation"), ("best_streak", "longest win streak")):
        rev = key != "ga"
        r, n, top = rank_of(m2, key, reverse=rev)
        r2, n2, top2 = rank_of(allr, key, reverse=rev)
        print(f"  {lab:34s} M2 rank {r}/{n} | all-ACHA rank {r2}/{n2} | M2 top: " +
              ", ".join(f"{x['team'][3:20]} {x['season'][2:]} {x[key]:.2f}" for x in top[:3]))
    print(f"\nThrough first {n_osu} games (M2 team-seasons only):")
    for key, lab in (("strength_at_n", "strength after N games"), ("cgd", "capped GD/game"), ("gd", "GD/game"), ("ga", "GA/game (low)"), ("winpct", "win %")):
        rows = [r for r in early if r.get(key) is not None]
        r, n, top = rank_of(rows, key, reverse=key != "ga")
        print(f"  {lab:26s} rank {r}/{n} | top: " + ", ".join(f"{x['team'][3:20]} {x['season'][2:]} {x[key]:.2f}" for x in top[:4]))


if __name__ == "__main__":
    main()
