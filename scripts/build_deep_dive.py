"""Deep-dive data for the Ohio sweep analysis page (data/ohio_deep_dive.json).

Sections: series/road rarity, Ohio at home, M2 team-seasons vs M1 (record, wins above expectation),
strongest M2 team-seasons on the shared scale, OSU's strength trajectory, weekend goal decomposition,
comeback base rate, M1-ranking counterfactual, remaining M1 schedule and record chase.
Usage: python3 scripts/build_deep_dive.py
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import math
import os
import statistics
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scripts")]

from build_case_study import m1_rank_at_game_time, short  # noqa: E402
from engine.allgames import MEN_SEASONS, XGame, games, load_feed, parse_team  # noqa: E402
from engine.m1rank import m1_games, ranking  # noqa: E402
from engine.xdiv import FITTED, build_chain, p_home_win  # noqa: E402

SEASONS = list(MEN_SEASONS)
CUR = SEASONS[-1]
OSU, OHIO = "M2 Oklahoma State University", "M1 Ohio University"
SERIES = ("31985", "31986")
WEEKEND = ("2026-11-06", "2026-11-07")


def result(m2g, m1g):
    return "W" if m2g > m1g else "L" if m2g < m1g else "T"


def poisson_binomial(ps):
    dist = [1.0]
    for p in ps:
        nd = [0.0] * (len(dist) + 1)
        for k, v in enumerate(dist):
            nd[k] += v * (1 - p)
            nd[k + 1] += v * p
        dist = nd
    return dist


def main():
    allg = {s: games(s) for s in SEASONS}
    chain = build_chain(FITTED)
    ranks = m1_rank_at_game_time(allg)
    m = chain[CUR]
    out = dict(generated_at=dt.datetime.now().isoformat(timespec="minutes"))

    # ---------- every M1-M2 game with rank at game time + pre-game p
    cross = []
    for s in SEASONS:
        for g in allg[s]:
            if {g.hdiv, g.adiv} != {1, 2}:
                continue
            m2h = g.hdiv == 2
            m2, m1 = (g.home, g.away) if m2h else (g.away, g.home)
            m2g, m1g = (g.hg, g.ag) if m2h else (g.ag, g.hg)
            p = chain[s].predict(g)["p_home"]
            cross.append(dict(season=s, id=g.id, date=g.date, m2=m2, m1=m1, m2_home=m2h, m2g=m2g, m1g=m1g,
                              rank=(ranks.get(g.id) or {}).get("rank"), p=p if m2h else 1 - p, res=result(m2g, m1g)))

    # ---------- series (same matchup within 2 days)
    by = defaultdict(list)
    for c in cross:
        by[(c["season"], c["m2"], c["m1"])].append(c)
    series = []
    for v in by.values():
        v.sort(key=lambda c: c["date"])
        cur = [v[0]]
        for c in v[1:]:
            if (dt.date.fromisoformat(c["date"]) - dt.date.fromisoformat(cur[-1]["date"])).days <= 2:
                cur.append(c)
            else:
                series.append(cur); cur = [c]
        series.append(cur)
    multi = [x for x in series if len(x) >= 2]
    srows = []
    for lab, hi in (("Top 5", 5), ("Top 10", 10), ("Top 25", 25)):
        xs = [x for x in multi if any(c["rank"] and c["rank"] <= hi for c in x)]
        sweeps = [x for x in xs if all(c["res"] == "W" for c in x)]
        srows.append(dict(tier=lab, series=len(xs), m2_won_a_game=sum(any(c["res"] == "W" for c in x) for x in xs),
                          sweeps=[dict(date=x[0]["date"], m2=short(x[0]["m2"]), m1=short(x[0]["m1"]),
                                       m1_rank=min(c["rank"] for c in x if c["rank"]), road=not x[0]["m2_home"],
                                       scores=[f"{c['m2g']}-{c['m1g']}" for c in x]) for x in sweeps]))
    road_top5 = [c for c in cross if c["rank"] and c["rank"] <= 5 and c["res"] == "W" and not c["m2_home"]]
    wins_top5 = [c for c in cross if c["rank"] and c["rank"] <= 5 and c["res"] == "W"]
    out["rarity"] = dict(series=srows, multi_series=len(multi),
                         top5_wins=[dict(date=c["date"], m2=short(c["m2"]), m1=short(c["m1"]), rank=c["rank"],
                                         road=not c["m2_home"], score=f"{c['m2g']}-{c['m1g']}", p=round(c["p"], 3)) for c in wins_top5],
                         road_top5_wins=len(road_top5))

    # ---------- Ohio at home
    home = []
    for s in SEASONS:
        hg = [g for g in allg[s] if g.home == OHIO and g.date not in WEEKEND]
        wk = [g for g in allg[s] if g.home == OHIO and g.date in WEEKEND]
        w = sum(g.hg > g.ag for g in hg); l = sum(g.hg < g.ag for g in hg); t = len(hg) - w - l
        home.append(dict(season=s, w=w, l=l, t=t, weekend_losses=sum(g.hg < g.ag for g in wk)))
    sweeps_at_ohio = []
    hgames = sorted([g for s in SEASONS for g in allg[s] if g.home == OHIO], key=lambda g: g.date)
    for a, b in zip(hgames, hgames[1:]):
        if a.away == b.away and a.hg < a.ag and b.hg < b.ag and (dt.date.fromisoformat(b.date) - dt.date.fromisoformat(a.date)).days <= 2:
            sweeps_at_ohio.append(dict(date=a.date, team=short(a.away), div=int(a.away[1]), scores=[f"{a.ag}-{a.hg}", f"{b.ag}-{b.hg}"]))
    ohio_vs_m2 = [g for s in SEASONS for g in allg[s] if OHIO in (g.home, g.away) and (g.away if g.home == OHIO else g.home).startswith("M2")]
    out["ohio"] = dict(home=home, home_sweeps=sweeps_at_ohio, games_vs_m2=len(ohio_vs_m2),
                       gf_by_game=[dict(date=g.date, opp=short(g.away if g.home == OHIO else g.home),
                                        gf=g.hg if g.home == OHIO else g.ag, ga=g.ag if g.home == OHIO else g.hg)
                                   for g in sorted(allg[CUR], key=lambda g: g.date) if OHIO in (g.home, g.away)])

    # ---------- M2 team-seasons vs M1
    ts = defaultdict(lambda: dict(w=0, l=0, t=0, exp=0.0))
    for c in cross:
        r = ts[(c["season"], c["m2"])]
        r[{"W": "w", "L": "l", "T": "t"}[c["res"]]] += 1
        r["exp"] += c["p"]
    team_seasons = [dict(season=s, team=short(t), w=v["w"], l=v["l"], t=v["t"], games=v["w"] + v["l"] + v["t"],
                         expected=round(v["exp"], 2), above=round(v["w"] + 0.5 * v["t"] - v["exp"], 2), osu=t == OSU)
                    for (s, t), v in ts.items()]
    out["team_seasons"] = dict(
        by_above=sorted(team_seasons, key=lambda r: -r["above"])[:10],
        by_wins=sorted(team_seasons, key=lambda r: (-r["w"], r["l"]))[:6],
        unbeaten=[r for r in team_seasons if r["l"] == 0 and r["w"] >= 3],
        osu_last_two=[r for r in team_seasons if r["osu"] and r["season"] in SEASONS[-2:]],
        n=len(team_seasons))

    # ---------- strongest M2 team-seasons on the shared scale (anchored seasons only)
    best = []
    for s in SEASONS[1:]:
        ms = chain[s]; f = ms.final(); gp = ms.gp_before("2999-01-01")
        m1 = sorted([v + FITTED.gap_12 for t, v in f.items() if t.startswith("M1") and gp[t] >= 5], reverse=True)
        m2 = sorted([(v, t) for t, v in f.items() if t.startswith("M2") and gp[t] >= 5], reverse=True)
        mean2 = statistics.mean(v for v, _ in m2)
        v, t = m2[0]
        best.append(dict(season=s, team=short(t), strength=round(v, 2), m1_equiv=sum(x > v for x in m1) + 1, m1_teams=len(m1),
                         above_m2_avg=round(v - mean2, 2), lead_over_2nd=round(v - m2[1][0], 2), second=short(m2[1][1]),
                         to_date=s == CUR))
    out["best_m2"] = best

    # ---------- OSU trajectory (weekly)
    start = dt.date(2026, 9, 13)
    pts = []
    d = start
    today = dt.date.today()
    stops = []
    while d <= today + dt.timedelta(days=1):
        stops.append(d.isoformat()); d += dt.timedelta(days=7)
    stops = sorted(set(stops) | {WEEKEND[0]} | ({(today + dt.timedelta(days=1)).isoformat()}))
    for ds in stops:
        st = m.strengths_before(ds); gp = m.gp_before(ds)
        m1 = sorted([v + FITTED.gap_12 for t, v in st.items() if t.startswith("M1")], reverse=True)
        o = st[OSU]
        pts.append(dict(date=ds, osu=round(o, 3), gp=gp[OSU], m1_equiv=sum(x > o for x in m1) + 1,
                        m1_1=round(m1[0], 3), m1_10=round(m1[9], 3), m1_25=round(m1[24], 3)))
    out["trajectory"] = pts

    # ---------- weekend odds: OSU vs comparison teams + OSU's season-long win distribution vs M1
    pre = m.strengths_before(WEEKEND[0])
    gp0 = m.gp_before(WEEKEND[0])
    m2s = sorted([(v, t) for t, v in pre.items() if t.startswith("M2") and gp0[t] >= 5], reverse=True)
    def sweep_p(s_team):
        p1 = p_home_win(pre[OHIO] - s_team + FITTED.home_edge + FITTED.gap_12, FITTED.sigma)
        return 1 - p1, (1 - p1) ** 2
    comps = [("Oklahoma State", pre[OSU]), (f"#2 M2 team ({short(m2s[1][1])})", m2s[1][0]),
             ("#10 M2 team", m2s[9][0]), ("Average M2 team", statistics.mean(v for v, _ in m2s))]
    osu_games = [c for c in cross if c["m2"] == OSU and c["season"] == CUR]
    dist = poisson_binomial([c["p"] for c in osu_games])
    out["odds"] = dict(
        weekend=[dict(id=c["id"], date=c["date"], p=round(c["p"], 4), score=f"{c['m2g']}-{c['m1g']}") for c in osu_games if c["id"] in SERIES],
        comparison=[dict(team=n, p_game=round(sweep_p(v)[0], 4), p_sweep=round(sweep_p(v)[1], 5)) for n, v in comps],
        season_games=[dict(date=c["date"], opp=short(c["m1"]), home=c["m2_home"], p=round(c["p"], 4), res=c["res"],
                           score=f"{c['m2g']}-{c['m1g']}") for c in osu_games],
        win_distribution=[round(x, 5) for x in dist], expected_wins=round(sum(c["p"] for c in osu_games), 2))

    # ---------- weekend decomposition
    stats = json.load(open(os.path.join(ROOT, f"data/game_stats/{CUR}.json")))
    cs = json.load(open(os.path.join(ROOT, "data/case_study_ohio.json")))
    mc = json.load(open(os.path.join(ROOT, "data/m1_compare.json")))
    P = cs["profiles"]
    agg = defaultdict(int)
    for gid in SERIES:
        x = stats[gid]
        o, h = (x["away"], x["home"]) if x["away"]["goals"] is not None else (x["away"], x["home"])
        agg["osu_shots"] += o["shots"]; agg["ohio_shots"] += h["shots"]; agg["osu_goals"] += o["goals"]; agg["ohio_goals"] += h["goals"]
        agg["ohio_ppg"] += h["ppg"]; agg["ohio_ppo"] += h["ppo"]; agg["osu_ppg"] += o["ppg"]; agg["osu_ppo"] += o["ppo"]
    margins = []
    for gid in SERIES:
        g = next(x for x in allg[CUR] if x.id == gid)
        pr = m.predict(g)
        margins.append(-pr["margin"] if g.home == OHIO else pr["margin"])
    model_margin = sum(margins)
    xgf = agg["osu_shots"] * (1 - P["ohio"]["save_pct"])
    xga = agg["ohio_shots"] * (1 - P["osu"]["save_pct"])
    actual = agg["osu_goals"] - agg["ohio_goals"]
    out["decomposition"] = dict(
        model_margin=round(model_margin, 2), shot_expected=round(xgf - xga, 2), shot_volume=round((xgf - xga) - model_margin, 2),
        goaltending=round(xga - agg["ohio_goals"], 2), finishing=round(agg["osu_goals"] - xgf, 2), actual=actual,
        totals=dict(agg), osu_season_sv=P["osu"]["save_pct"], ohio_season_sv=P["ohio"]["save_pct"],
        ohio_pp_season=P["ohio"]["pp_pct"], ohio_pp_expected=round(agg["ohio_ppo"] * P["ohio"]["pp_pct"], 2),
        m1_avg_sv=mc["stats"]["m1_all"]["save_pct"], gsaa_vs_m1_avg=round(agg["ohio_shots"] * (1 - mc["stats"]["m1_all"]["save_pct"]) - agg["ohio_goals"], 2))

    # goalie vs M1
    kub = []
    for g in allg[CUR]:
        if OSU not in (g.home, g.away) or g.id not in stats:
            continue
        side = "home" if g.home == OSU else "away"
        for gl in stats[g.id][side]["goalies"]:
            if gl["sa"]:
                kub.append(dict(date=g.date, name=gl["name"], sv=gl["sv"], sa=gl["sa"], vs_m1={g.hdiv, g.adiv} == {1, 2}))
    goalies = defaultdict(lambda: dict(sv=0, sa=0, sv_m1=0, sa_m1=0, starts_m1=0))
    for k in kub:
        r = goalies[k["name"]]; r["sv"] += k["sv"]; r["sa"] += k["sa"]
        if k["vs_m1"]:
            r["sv_m1"] += k["sv"]; r["sa_m1"] += k["sa"]; r["starts_m1"] += 1
    out["goalies"] = [dict(name=n, **v) for n, v in goalies.items()]
    wkg = defaultdict(lambda: dict(sv=0, sa=0))
    for gid in SERIES:
        g = next(x for x in allg[CUR] if x.id == gid)
        for gl in stats[gid]["home" if g.home == OSU else "away"]["goalies"]:
            if gl["sa"]:
                wkg[gl["name"]]["sv"] += gl["sv"]; wkg[gl["name"]]["sa"] += gl["sa"]
    out["weekend_goalies"] = [dict(name=n, **v) for n, v in wkg.items()]

    # comeback base rate (road team trailing by one after the first period)
    tot = win = 0
    for f in glob.glob(os.path.join(ROOT, "data/game_stats/*.json")):
        for gid, x in json.load(open(f)).items():
            p = x["periods"]
            if not p or x["home"]["goals"] is None or x["away"]["goals"] is None or gid in SERIES:
                continue
            if p[0]["hg"] - p[0]["vg"] == 1:
                tot += 1; win += x["away"]["goals"] > x["home"]["goals"]
    out["comeback"] = dict(games=tot, road_wins=win, rate=win / tot if tot else None)

    # ---------- M1 ranking counterfactual
    G = allg[CUR]
    base = {r.team: r.rank for r in ranking(m1_games(G))}
    osu_x = [g for g in G if OSU in (g.home, g.away) and {g.hdiv, g.adiv} == {1, 2}]
    with_osu = {r.team: r.rank for r in ranking(m1_games(G, extra=osu_x))}
    out["counterfactual"] = [dict(team=short("M1 " + t) if t != "Oklahoma State University" else "Oklahoma State",
                                  actual=base.get(t), with_osu=with_osu.get(t))
                             for t in sorted(with_osu, key=lambda t: with_osu[t])[:12]]
    out["counterfactual_ohio"] = dict(actual=base.get("Ohio University"), with_osu=with_osu.get("Ohio University"))

    # ---------- remaining M1 schedule and record chase
    rem = []
    excluded = set(map(str, json.load(open(os.path.join(ROOT, f"data/overrides_{CUR}.json"))).get("exclude_game_ids", [])))
    for g in load_feed(CUR):
        if str(g["id"]) in excluded:
            continue
        hd, h = parse_team(g["home_team_name"]); ad, a = parse_team(g["visiting_team_name"])
        if g["game_status"].startswith("Final") or g["date_played"] <= WEEKEND[1] or g["date_played"] > "2027-03-01":
            continue
        if OSU in (f"M{hd} {h}", f"M{ad} {a}") and 1 in (hd, ad):
            rem.append(XGame(str(g["id"]), CUR, g["date_played"], f"M{hd} {h}", f"M{ad} {a}", hd, ad, 0, 0, False, False))
    rps = []
    for g in rem:
        pr = m.predict(g)
        rps.append(dict(date=g.date, opp=short(g.away if g.home == OSU else g.home), home=g.home == OSU,
                        p=round(pr["p_home"] if g.home == OSU else 1 - pr["p_home"], 4),
                        opp_m1_rank=base.get((g.away if g.home == OSU else g.home)[3:])))
    rdist = poisson_binomial([r["p"] for r in rps])
    have = sum(c["res"] == "W" for c in osu_games)
    record = max(r["w"] for r in team_seasons if not (r["osu"] and r["season"] == CUR))
    need = record + 1 - have
    out["remaining"] = dict(games=rps, expected_more=round(sum(r["p"] for r in rps), 2), have=have, record=record,
                            record_holder=next(f"{r['team']} ({r['season']})" for r in team_seasons if r["w"] == record and not (r["osu"] and r["season"] == CUR)),
                            p_break=round(sum(rdist[max(need, 0):]), 4), p_tie_or_break=round(sum(rdist[max(need - 1, 0):]), 4),
                            p_perfect=round(rdist[-1], 5), dist=[round(x, 5) for x in rdist])

    path = os.path.join(ROOT, "data/ohio_deep_dive.json")
    old = json.load(open(path)) if os.path.exists(path) else {}
    if {k: v for k, v in old.items() if k != "generated_at"} != json.loads(json.dumps({k: v for k, v in out.items() if k != "generated_at"})):
        with open(path, "w") as f:
            json.dump(out, f, indent=1)
    dcp = out["decomposition"]
    print("decomposition:", {k: dcp[k] for k in ("model_margin", "shot_volume", "goaltending", "finishing", "actual")})
    print("comparison:", out["odds"]["comparison"])
    print("record chase:", {k: out["remaining"][k] for k in ("have", "record", "record_holder", "p_break", "p_perfect", "expected_more")})
    print("best M2:", [(b["season"], b["team"], b["m1_equiv"], b["lead_over_2nd"]) for b in best])
    print("counterfactual Ohio:", out["counterfactual_ohio"], "| home sweeps at Ohio:", [(x["date"], x["team"]) for x in sweeps_at_ohio])


if __name__ == "__main__":
    main()
