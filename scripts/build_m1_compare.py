"""Build data/m1_compare.json for the dashboard's "vs M1" tab.

  - OSU's rank among M1 teams on the shared scale, with 80%/95% ranges (Monte Carlo over strength uncertainty)
  - OSU's rank if added to ACHA's M1 computer ranking (guest method)
  - OSU's game log vs M1 teams: pre-game odds, surprise, shots, PP, save %
  - per-game stats: OSU (all games, vs M1 only) vs M1 average / top 25 / top 5
  - the M1-M2 gap by season and M2's record vs M1
  - an unofficial combined M1+M2 top 25
Usage: python3 scripts/build_m1_compare.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.allgames import MEN_SEASONS  # noqa: E402
from engine.m1rank import m1_games, ranking  # noqa: E402
from engine.xdiv import FITTED, build_chain  # noqa: E402

SEASONS = list(MEN_SEASONS)
CUR = SEASONS[-1]
OSU = "M2 Oklahoma State University"
MIN_GP = 5


def short(t: str) -> str:
    n = t[3:] if t[:2] in ("M1", "M2", "M3") else t
    for a, b in (("University of ", ""), (" University", ""), ("The ", ""), (" College", "")):
        n = n.replace(a, b)
    return n


def profile(team: str, gs: list, stats: dict, only=None) -> dict | None:
    """Per-game averages from box scores; `only` filters games (e.g. vs M1 opponents)."""
    n = ns = gf = ga = ga_t = sf = sa = ppg = ppo = ppga = ppoa = 0
    for g in gs:
        if team not in (g.home, g.away) or g.id not in stats or (only and not only(g)):
            continue
        st = stats[g.id]
        me, opp = (st["home"], st["away"]) if g.home == team else (st["away"], st["home"])
        n += 1
        gf += me["goals"] or 0; ga += opp["goals"] or 0
        ppg += me["ppg"] or 0; ppo += me["ppo"] or 0; ppga += opp["ppg"] or 0; ppoa += opp["ppo"] or 0
        if st["shots_ok"]:
            ns += 1; sf += me["shots"]; sa += opp["shots"]; ga_t += opp["goals"] or 0
    if not n:
        return None
    return dict(games=n, gf=gf / n, ga=ga / n, shots_for=sf / ns if ns else None, shots_against=sa / ns if ns else None,
                shot_share=sf / (sf + sa) if ns else None, save_pct=1 - ga_t / sa if sa else None,
                pp_pct=ppg / ppo if ppo else None, pk_pct=1 - ppga / ppoa if ppoa else None)


def mean_profile(profiles: list[dict]) -> dict:
    keys = ["gf", "ga", "shots_for", "shots_against", "shot_share", "save_pct", "pp_pct", "pk_pct"]
    out = {}
    for k in keys:
        v = [p[k] for p in profiles if p and p.get(k) is not None]
        out[k] = statistics.mean(v) if v else None
    out["teams"] = len([p for p in profiles if p])
    return out


def main():
    chain = build_chain(FITTED)
    m = chain[CUR]
    G = m.games
    strength = m.final()
    gp = m.gp_before("2999-01-01")
    stats = json.load(open(os.path.join(ROOT, f"data/game_stats/{CUR}.json")))

    # ---- M1 computer ranking (our reconstruction) now, and OSU as a guest
    m1_rows = ranking(m1_games(G))
    m1_rank = {r.team: r.rank for r in m1_rows}
    osu_m1_games = [g for g in G if OSU in (g.home, g.away) and {g.hdiv, g.adiv} == {1, 2}]
    guest = ranking(m1_games(G, extra=osu_m1_games))
    grow = next(r for r in guest if r.team == OSU[3:])

    # ---- shared-scale rank among M1 teams with uncertainty
    m1_teams = [t for t in strength if t.startswith("M1 ") and gp[t] >= 3]
    sd = lambda t: FITTED.sigma / math.sqrt(gp[t] + FITTED.k)
    adj = {t: strength[t] + FITTED.gap_12 for t in m1_teams}
    point = sum(adj[t] > strength[OSU] for t in m1_teams) + 1
    rng = random.Random(11)
    draws = []
    for _ in range(4000):
        so = rng.gauss(strength[OSU], sd(OSU))
        draws.append(1 + sum(rng.gauss(adj[t], sd(t)) > so for t in m1_teams))
    draws.sort()
    q = lambda p: draws[int(p * (len(draws) - 1))]
    top10 = sum(d <= 10 for d in draws) / len(draws)

    # ---- game log vs M1
    log = []
    for g in osu_m1_games:
        home = g.home == OSU
        opp = g.away if home else g.home
        pr = m.predict(g)
        p = pr["p_home"] if home else 1 - pr["p_home"]
        gf, ga = (g.hg, g.ag) if home else (g.ag, g.hg)
        res = "W" if gf > ga else "L" if gf < ga else "T"
        st = stats.get(g.id)
        me = op = None
        if st:
            me, op = (st["home"], st["away"]) if home else (st["away"], st["home"])
        log.append(dict(id=g.id, date=g.date, opponent=short(opp), home=home, gf=gf, ga=ga, ot=g.ot, result=res,
                        opp_m1_rank=m1_rank.get(opp[3:]), p_osu=round(p, 4),
                        surprise_bits=round(-math.log2(p if res == "W" else (1 - p) if res == "L" else 0.5), 2),
                        shots_for=me["shots"] if st and st["shots_ok"] else None,
                        shots_against=op["shots"] if st and st["shots_ok"] else None,
                        pp=f"{me['ppg']}/{me['ppo']}" if st else None,
                        save_pct=round(1 - ga / op["shots"], 3) if st and st["shots_ok"] and op["shots"] else None))
    p_perfect = math.prod(x["p_osu"] for x in log) if log and all(x["result"] == "W" for x in log) else None

    # ---- stat comparison
    is_m1 = lambda team: (lambda g: (g.away if g.home == team else g.home).startswith("M1 "))
    prof_m1 = {t: profile(t, G, stats) for t in m1_teams}
    ranked = sorted(m1_teams, key=lambda t: m1_rank.get(t[3:], 999))
    comp = dict(
        osu_all=profile(OSU, G, stats),
        osu_vs_m1=profile(OSU, G, stats, only=is_m1(OSU)),
        m1_top5=mean_profile([prof_m1[t] for t in ranked[:5]]),
        m1_top25=mean_profile([prof_m1[t] for t in ranked[:25]]),
        m1_all=mean_profile(list(prof_m1.values())),
    )
    coverage = sum(1 for g in G if 1 in (g.hdiv, g.adiv) and g.id in stats) / max(1, sum(1 for g in G if 1 in (g.hdiv, g.adiv)))

    # ---- division gap by season
    gaps = []
    for s in SEASONS:
        ms = chain[s]
        fin = ms.final()
        gps = ms.gp_before("2999-01-01")
        mean = lambda d: statistics.mean(v for t, v in fin.items() if t.startswith(f"M{d} ") and gps[t] >= MIN_GP)
        cross = [g for g in ms.games if {g.hdiv, g.adiv} == {1, 2} and g.date < ("2026-11-06" if s == CUR else "9999")]
        w = sum((g.hg > g.ag) == (g.hdiv == 2) and g.hg != g.ag for g in cross)
        t = sum(g.hg == g.ag for g in cross)
        lean = statistics.mean(((1.0 if g.hg > g.ag else 0.0 if g.hg < g.ag else 0.5) - ms.predict(g)["p_home"]) *
                               (1 if g.hdiv == 1 else -1) for g in cross) if s != SEASONS[0] and cross else None
        top = lambda d: statistics.mean(sorted((v for t, v in fin.items() if t.startswith(f"M{d} ") and gps[t] >= MIN_GP), reverse=True)[:25])
        gaps.append(dict(season=s, anchored=s != SEASONS[0], m1_mean=mean(1), m2_mean=mean(2),
                         gap=mean(1) - mean(2) + FITTED.gap_12, top25_gap=top(1) - top(2) + FITTED.gap_12,
                         m1_teams=sum(1 for t in fin if t.startswith("M1 ") and gps[t] >= MIN_GP),
                         m2_teams=sum(1 for t in fin if t.startswith("M2 ") and gps[t] >= MIN_GP),
                         games=len(cross), m2_w=w, m2_l=len(cross) - w - t, m2_t=t,
                         m2_win_rate=(w + 0.5 * t) / len(cross) if cross else None, m1_lean=lean))

    # ---- combined M1+M2 top 25 (unofficial)
    snap = json.load(open(os.path.join(ROOT, "data/snapshots/latest.json")))
    m2_info = {t["team"]: t for t in snap["teams"]}
    nat = sorted((t for t in snap["teams"] if t.get("status") == "ranked"), key=lambda t: (-t["final"], -t["raw"], -t["sched"]))
    nat_rank = {t["team"]: i + 1 for i, t in enumerate(nat)}
    pool = [(strength[t] + (FITTED.gap_12 if t.startswith("M1 ") else 0.0), t) for t in strength
            if t[:2] in ("M1", "M2") and gp[t] >= MIN_GP]
    pool.sort(reverse=True)
    combined = []
    for i, (v, t) in enumerate(pool[:25]):
        d = int(t[1]); name = t[3:]
        row = dict(rank=i + 1, team=short(t), div=d, strength=round(v, 2), gp=gp[t])
        if d == 1:
            row["div_rank"] = m1_rank.get(name)
        else:
            info = m2_info.get(name, {})
            row["region"], row["div_rank"], row["m2_national"] = info.get("region"), info.get("rank"), nat_rank.get(name)
        combined.append(row)
    m1_in = sum(r["div"] == 1 for r in combined)

    out = dict(
        generated_at=dt.datetime.now().isoformat(timespec="minutes"),
        model=dict(gap_12=FITTED.gap_12, home_edge=FITTED.home_edge, sigma=FITTED.sigma),
        osu=dict(strength=strength[OSU], gp=gp[OSU]),
        m1_scale=dict(rank=point, of=len(m1_teams), p10=q(0.10), p90=q(0.90), p025=q(0.025), p975=q(0.975), p_top10=top10,
                      top=[dict(team=short(t), strength=round(adj[t], 2), m1_rank=m1_rank.get(t[3:]))
                           for t in sorted(m1_teams, key=lambda t: -adj[t])[:10]]),
        guest=dict(rank=grow.rank, of=len(guest), w=grow.w, l=grow.l, t=grow.t, rank_a=grow.rank_a, rank_b=grow.rank_b),
        games=log, p_perfect=p_perfect, stats=comp, stats_coverage=coverage, gaps=gaps,
        combined=combined, combined_m1=m1_in, combined_m2=len(combined) - m1_in,
    )
    path = os.path.join(ROOT, "data/m1_compare.json")
    old = json.load(open(path)) if os.path.exists(path) else {}
    if {k: v for k, v in old.items() if k != "generated_at"} == json.loads(json.dumps({k: v for k, v in out.items() if k != "generated_at"})):
        print("m1 compare unchanged")
    else:
        with open(path, "w") as f:
            json.dump(out, f, indent=1)
    print(f"OSU M1-scale #{point}/{len(m1_teams)} (80%: {q(.1)}-{q(.9)}, 95%: {q(.025)}-{q(.975)}, P(top 10) {top10:.0%}); "
          f"guest #{grow.rank}/{len(guest)}; {len(log)} games vs M1; P(perfect) {p_perfect}")
    print(f"stats coverage {coverage:.0%}; combined top 25: {m1_in} M1 / {len(combined) - m1_in} M2")
    for gg in gaps:
        print(f"  {gg['season']}: avg gap {gg['gap']:.2f}, top-25 gap {gg['top25_gap']:.2f} ({gg['m1_teams']} M1 / {gg['m2_teams']} M2 teams), M2 {gg['m2_w']}-{gg['m2_l']}-{gg['m2_t']} vs M1")


if __name__ == "__main__":
    main()
