"""Extra sections for the Ohio analysis page (data/ohio_extra.json):
  players   - OSU scoring vs M1 and season (from box-score goal events)
  flow      - scoring first, period margins, special teams (all games / vs M1)
  h2h       - OSU's neutral-ice win chance vs each M1 top-10 team, plus common-opponent margins
  robust    - headline numbers under alternative model settings, and significance checks
Usage: python3 scripts/build_deep_dive_extra.py [--quick]
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math
import os
import statistics
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scripts")]

from build_case_study import m1_rank_at_game_time, short  # noqa: E402
from engine.allgames import MEN_SEASONS, games  # noqa: E402
from engine.m1rank import m1_games, ranking  # noqa: E402
from engine.xdiv import FITTED, build_chain, p_home_win  # noqa: E402

SEASONS = list(MEN_SEASONS)
CUR = SEASONS[-1]
OSU, OHIO = "M2 Oklahoma State University", "M1 Ohio University"
SERIES = ("31985", "31986")
PERIOD_ORDER = ["1st", "2nd", "3rd", "OT", "OT1", "OT2", "SO"]


def secs(e):
    m, s = (e["time"] or "0:00").split(":")
    p = PERIOD_ORDER.index(e["period"]) if e["period"] in PERIOD_ORDER else 9
    return p * 10000 + int(m) * 60 + int(s)


def players_and_flow(G, stats):
    pl = defaultdict(lambda: dict(g=0, a=0, gwg=0, ppg=0, shg=0, g_m1=0, a_m1=0, gwg_m1=0, gp_m1=0))
    flow = {k: defaultdict(int) for k in ("all", "m1")}
    log = []
    for g in sorted(G, key=lambda g: g.date):
        if OSU not in (g.home, g.away) or g.id not in stats:
            continue
        x = stats[g.id]; side = "home" if g.home == OSU else "away"; vm1 = {g.hdiv, g.adiv} == {1, 2}
        for e in x.get("goals", []):
            if e["side"] != side:
                continue
            p = pl[e["scorer"]]; p["g"] += 1; p["gwg"] += e["gwg"]; p["ppg"] += e["pp"]; p["shg"] += e["sh"]
            if vm1:
                p["g_m1"] += 1; p["gwg_m1"] += e["gwg"]
            for a in e["assists"]:
                pl[a]["a"] += 1
                if vm1:
                    pl[a]["a_m1"] += 1
        evs = sorted(x.get("goals", []), key=secs)
        first = (evs[0]["side"] == side) if evs else None
        gf, ga = (g.hg, g.ag) if side == "home" else (g.ag, g.hg)
        me, op = (x["home"], x["away"]) if side == "home" else (x["away"], x["home"])
        per = []
        for pp in x["periods"][:3]:
            per.append((pp["hg"], pp["vg"]) if side == "home" else (pp["vg"], pp["hg"]))
        lead2 = sum(a for a, _ in per[:2]) - sum(b for _, b in per[:2])
        for key in ("all", "m1") if vm1 else ("all",):
            f = flow[key]; f["games"] += 1; f["wins"] += gf > ga; f["gf"] += gf; f["ga"] += ga
            if first is True:
                f["scored_first"] += 1; f["scored_first_won"] += gf > ga
            elif first is False:
                f["allowed_first"] += 1; f["allowed_first_won"] += gf > ga
            for i, (a, b) in enumerate(per):
                f[f"p{i + 1}_gf"] += a; f[f"p{i + 1}_ga"] += b
            if lead2 > 0:
                f["led_after_2"] += 1; f["led_after_2_won"] += gf > ga
            elif lead2 < 0:
                f["trailed_after_2"] += 1; f["trailed_after_2_won"] += gf > ga
            f["ppg"] += me["ppg"] or 0; f["ppo"] += me["ppo"] or 0; f["ppga"] += op["ppg"] or 0; f["ppoa"] += op["ppo"] or 0
            f["shg"] += sum(1 for e in x.get("goals", []) if e["side"] == side and e["sh"])
            f["shga"] += sum(1 for e in x.get("goals", []) if e["side"] != side and e["sh"])
        if vm1:
            for n in {e["scorer"] for e in x.get("goals", []) if e["side"] == side} | {a for e in x.get("goals", []) if e["side"] == side for a in e["assists"]}:
                pl[n]["gp_m1"] += 1
            log.append(dict(date=g.date, opp=short(g.away if side == "home" else g.home), gf=gf, ga=ga, first=first,
                            periods=[f"{a}-{b}" for a, b in per],
                            penalty_shots=[ps for ps in x.get("penalty_shots", [])]))
    players = sorted(({"name": n, **v, "p": v["g"] + v["a"], "p_m1": v["g_m1"] + v["a_m1"]} for n, v in pl.items() if n),
                     key=lambda r: (-r["p_m1"], -r["g_m1"], -r["p"]))
    return players[:14], {k: dict(v) for k, v in flow.items()}, log


def h2h(chain, G):
    m = chain[CUR]
    s = m.final(); gp = m.gp_before("2999-01-01")
    sd = lambda t: FITTED.sigma / math.sqrt(gp.get(t, 0) + FITTED.k)
    rows = ranking(m1_games(G))
    top = [r for r in rows if r.rank <= 10]
    # opponents per team with capped, home-adjusted GD (positive = good for the team)
    res = defaultdict(lambda: defaultdict(list))
    for g in G:
        d = max(-7, min(7, g.hg - g.ag))
        res[g.home][g.away].append(d - FITTED.home_edge)
        res[g.away][g.home].append(-d + FITTED.home_edge)
    out = []
    for r in top:
        t = "M1 " + r.team
        margin = s[OSU] - (s[t] + FITTED.gap_12)
        tot_sd = math.sqrt(FITTED.sigma ** 2 + sd(OSU) ** 2 + sd(t) ** 2)
        p_neutral = p_home_win(margin, tot_sd)
        p_home = p_home_win(margin + FITTED.home_edge, tot_sd)
        p_away = p_home_win(margin - FITTED.home_edge, tot_sd)
        p_stronger = 0.5 * (1 + math.erf(margin / math.sqrt(2 * (sd(OSU) ** 2 + sd(t) ** 2))))
        common = sorted(set(res[OSU]) & set(res[t]) - {OSU, t})
        comp = []
        for o in common:
            a, b = statistics.mean(res[OSU][o]), statistics.mean(res[t][o])
            comp.append(dict(opp=short(o), div=int(o[1]), osu=round(a, 2), them=round(b, 2), diff=round(a - b, 2),
                             osu_games=len(res[OSU][o]), their_games=len(res[t][o])))
        direct = res[OSU].get(t)
        out.append(dict(team=short(t), m1_rank=r.rank, strength=round(s[t] + FITTED.gap_12, 2), margin=round(margin, 2),
                        p_neutral=round(p_neutral, 4), p_home=round(p_home, 4), p_away=round(p_away, 4),
                        p_osu_stronger=round(p_stronger, 4), common=comp,
                        common_margin=round(statistics.mean(c["diff"] for c in comp), 2) if comp else None,
                        played=len(direct) if direct else 0))
    return out, dict(osu=round(s[OSU], 2), osu_sd=round(sd(OSU), 2))


def headline_numbers(p, allg_cache=None):
    """Headline quantities for one parameter setting."""
    chain = build_chain(p)
    m = chain[CUR]
    G = m.games
    out = {}
    for gid in SERIES:
        g = next(x for x in G if x.id == gid)
        pr = m.predict(g)
        out[f"p_{gid}"] = pr["p_home"] if g.home == OSU else 1 - pr["p_home"]
    out["sweep"] = out[f"p_{SERIES[0]}"] * out[f"p_{SERIES[1]}"]
    s = m.final(); gp = m.gp_before("2999-01-01")
    m1 = sorted([v + p.gap_12 for t, v in s.items() if t.startswith("M1") and gp[t] >= 3], reverse=True)
    out["m1_equiv"] = sum(x > s[OSU] for x in m1) + 1
    # wins above expectation rank among M2 team-seasons, and P(7-0)
    ts = defaultdict(lambda: [0.0, 0.0])
    osu_ps = []
    for sn in SEASONS:
        ms = chain[sn]
        for g in ms.games:
            if {g.hdiv, g.adiv} != {1, 2}:
                continue
            m2h = g.hdiv == 2; m2 = g.home if m2h else g.away
            pp = ms.predict(g)["p_home"]; pp = pp if m2h else 1 - pp
            m2g, m1g = (g.hg, g.ag) if m2h else (g.ag, g.hg)
            ts[(sn, m2)][0] += (m2g > m1g) + 0.5 * (m2g == m1g); ts[(sn, m2)][1] += pp
            if sn == CUR and m2 == OSU:
                osu_ps.append(pp)
    above = sorted(((w - e, k) for k, (w, e) in ts.items()), reverse=True)
    out["above_rank"] = next(i + 1 for i, (_, k) in enumerate(above) if k == (CUR, OSU))
    out["above"] = next(v for v, k in above if k == (CUR, OSU))
    out["p_perfect"] = math.prod(osu_ps)
    # best M2 team-season on the M1 scale
    best = []
    for sn in SEASONS[1:]:
        ms = chain[sn]; f = ms.final(); g2 = ms.gp_before("2999-01-01")
        mm1 = sorted([v + p.gap_12 for t, v in f.items() if t.startswith("M1") and g2[t] >= 5], reverse=True)
        top2 = sorted([(v, t) for t, v in f.items() if t.startswith("M2") and g2[t] >= 5], reverse=True)[:2]
        best.append((sn, top2[0][1], sum(x > top2[0][0] for x in mm1) + 1, top2[0][0] - top2[1][0]))
    osu_best = next(b for b in best if b[0] == CUR)
    out["osu_best_m1_equiv"] = osu_best[2] if osu_best[1] == OSU else None
    out["osu_is_best_m1_equiv"] = osu_best[1] == OSU and all(osu_best[2] <= b[2] for b in best)
    out["osu_widest_lead"] = osu_best[1] == OSU and all(osu_best[3] >= b[3] for b in best)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="skip the robustness grid")
    args = ap.parse_args()
    allg = {s: games(s) for s in SEASONS}
    chain = build_chain(FITTED)
    G = allg[CUR]
    stats = json.load(open(os.path.join(ROOT, f"data/game_stats/{CUR}.json")))
    players, flow, m1log = players_and_flow(G, stats)
    h2h_rows, osu_s = h2h(chain, G)

    # ---- significance checks under the fitted model
    ranks = m1_rank_at_game_time(allg)
    cross = []
    for s in SEASONS:
        for g in allg[s]:
            if {g.hdiv, g.adiv} != {1, 2}:
                continue
            m2h = g.hdiv == 2
            pp = chain[s].predict(g)["p_home"]
            cross.append(dict(season=s, id=g.id, date=g.date, m2=g.home if m2h else g.away, m1=g.away if m2h else g.home,
                              p=pp if m2h else 1 - pp, rank=(ranks.get(g.id) or {}).get("rank"),
                              w=(g.hg > g.ag) if m2h else (g.ag > g.hg)))
    by = defaultdict(list)
    for c in cross:
        by[(c["season"], c["m2"], c["m1"])].append(c)
    top5_series = []
    for v in by.values():
        v.sort(key=lambda c: c["date"])
        chunks, cur = [], [v[0]]
        for c in v[1:]:
            if (dt.date.fromisoformat(c["date"]) - dt.date.fromisoformat(cur[-1]["date"])).days <= 2:
                cur.append(c)
            else:
                chunks.append(cur); cur = [c]
        chunks.append(cur)
        top5_series += [x for x in chunks if len(x) >= 2 and any(c["rank"] and c["rank"] <= 5 for c in x)]
    sweep_ps = [math.prod(c["p"] for c in x) for x in top5_series]
    exp_sweeps = sum(sweep_ps)
    p_any = 1 - math.prod(1 - q for q in sweep_ps)
    osu_cur = [c for c in cross if c["m2"] == OSU and c["season"] == CUR]
    m = chain[CUR]; s = m.final(); gp = m.gp_before("2999-01-01")
    sd = lambda t: FITTED.sigma / math.sqrt(gp[t] + FITTED.k)
    z = (s[OSU] - s[OHIO] - FITTED.gap_12) / math.sqrt(sd(OSU) ** 2 + sd(OHIO) ** 2)
    sig = dict(
        p_perfect=math.prod(c["p"] for c in osu_cur), n_m1_games=len(osu_cur),
        top5_series=len(top5_series), expected_sweeps=round(exp_sweeps, 3), p_any_sweep=round(p_any, 3),
        osu_sweep_share=round(next((q for x, q in zip(top5_series, sweep_ps) if x[0]["m2"] == OSU), 0) / exp_sweeps, 3) if exp_sweeps else None,
        p_osu_stronger_than_ohio=round(0.5 * (1 + math.erf(z / math.sqrt(2))), 3),
        osu_rating_80=[round(s[OSU] - 1.2816 * sd(OSU), 2), round(s[OSU] + 1.2816 * sd(OSU), 2)])

    # ---- robustness grid
    grid = []
    if not args.quick:
        settings = [("As fitted", {}), ("No M1 adjustment", dict(gap_12=0.0, gap_13=0.0, gap_23=0.0)),
                    ("M1 adjustment +1.0", dict(gap_12=1.0)), ("Prior weight k=1", dict(k=1)), ("Prior weight k=5", dict(k=5)),
                    ("Prior regression b=0.4", dict(b=0.4)), ("Prior regression b=0.8", dict(b=0.8)),
                    ("Spread 2.6 goals", dict(sigma=2.6)), ("Spread 3.4 goals", dict(sigma=3.4)),
                    ("No home edge", dict(home_edge=0.0))]
        for name, kw in settings:
            p = dataclasses.replace(FITTED, **kw)
            h = headline_numbers(p)
            grid.append(dict(setting=name, **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in h.items()}))
            print(f"  {name:24s} Fri {h[f'p_{SERIES[0]}']:.0%} Sat {h[f'p_{SERIES[1]}']:.0%} sweep 1/{1/h['sweep']:.0f} "
                  f"M1-eq #{h['m1_equiv']} above-rank #{h['above_rank']} ({h['above']:+.2f}) P(7-0) {h['p_perfect']:.3%} "
                  f"best-M2? {h['osu_is_best_m1_equiv']} widest? {h['osu_widest_lead']}")

    out = dict(generated_at=dt.datetime.now().isoformat(timespec="minutes"), players=players, flow=flow, m1_games=m1log,
               h2h=h2h_rows, osu_strength=osu_s, significance=sig, robustness=grid)
    path = os.path.join(ROOT, "data/ohio_extra.json")
    old = json.load(open(path)) if os.path.exists(path) else {}
    if args.quick and old.get("robustness"):
        out["robustness"] = old["robustness"]  # keep the last full grid
    if {k: v for k, v in old.items() if k != "generated_at"} != json.loads(json.dumps({k: v for k, v in out.items() if k != "generated_at"})):
        with open(path, "w") as f:
            json.dump(out, f, indent=1)
    print("flow vs M1:", flow.get("m1"))
    print("h2h:", [(r["team"], r["m1_rank"], f"{r['p_neutral']:.0%}", r["common_margin"], len(r["common"])) for r in h2h_rows])
    print("significance:", sig)


if __name__ == "__main__":
    main()
