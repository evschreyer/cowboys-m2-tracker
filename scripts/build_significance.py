"""Data for the living "Significance Report" (data/significance.json).

  ladder        evidence that OSU is better than a set of benchmark teams (z, one-sided p, verdict),
                recomputed every refresh, plus the same ladder as of every week since mid-September
  history       where OSU's season ranks among all M2 team-seasons since 2022-23
  champions     chance OSU is stronger than each past M2 champion; chance it's the strongest M2 team-season
  dominance     per-game performance vs M1 benchmarks; share of regulation time leading vs every M1 team
  rivals        title contenders and West chasers: strength, head-to-head odds, results, upcoming meetings
Usage: python3 scripts/build_significance.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import statistics
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scripts")]

from build_case_study import short  # noqa: E402
from engine.allgames import MEN_SEASONS, XGame, games, load_feed, parse_team  # noqa: E402
from engine.xdiv import FITTED, build_chain, p_home_win  # noqa: E402

SEASONS = list(MEN_SEASONS)
CUR = SEASONS[-1]
ANCHORED = SEASONS[1:]
OSU = "M2 Oklahoma State University"
CHAMPIONS = {"2021-22": "M2 University of Mary", "2022-23": "M2 University of Massachusetts-Amherst",
             "2023-24": "M2 Indiana University", "2024-25": "M2 Lindenwood University",
             "2025-26": "M2 Florida Gulf Coast University"}
PER = {"1st": 0, "2nd": 1, "3rd": 2}
Phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))


def verdict(z):
    return "Proven" if z >= 3 else "Strong" if z >= 2 else "Likely" if z >= 1.2816 else "Not yet"


def sd_of(gp, t):
    return FITTED.sigma / math.sqrt(gp.get(t, 0) + FITTED.k)


def main():
    chain = build_chain(FITTED)
    m = chain[CUR]
    excluded = set(map(str, json.load(open(os.path.join(ROOT, f"data/overrides_{CUR}.json"))).get("exclude_game_ids", [])))

    # season-best M2 strength in each completed anchored season (constant benchmarks)
    season_best = {}
    for s in ANCHORED[:-1]:
        ms = chain[s]; f = ms.final(); g = ms.gp_before("2999-01-01")
        season_best[s] = max((v, t) for t, v in f.items() if t.startswith("M2") and g[t] >= 5)
    typical_best = statistics.mean(v for v, _ in season_best.values())
    best_prev = max(season_best.values())

    def ladder_at(date):
        st = m.strengths_before(date); gp = m.gp_before(date)
        if OSU not in st or gp.get(OSU, 0) == 0:
            return None
        m1 = sorted([v + FITTED.gap_12 for t, v in st.items() if t.startswith("M1") and gp.get(t, 0) >= 3], reverse=True)
        if len(m1) < 40:  # early season: fall back to every M1 team (ratings anchored to last season)
            m1 = sorted([v + FITTED.gap_12 for t, v in st.items() if t.startswith("M1")], reverse=True)
        s_, sd_ = st[OSU], sd_of(gp, OSU)
        benches = [("avg_m1", "An average M1 team", statistics.mean(m1)),
                   ("m1_25", "M1's No. 25 team", m1[24]),
                   ("typical_best_m2", "A typical season-best M2 team (2022-23 to 2025-26)", typical_best),
                   ("m1_10", "M1's No. 10 team", m1[9]),
                   ("best_prev_m2", f"The best previous M2 team-season ({short(best_prev[1])} {[s for s, v in season_best.items() if v == best_prev][0]})", best_prev[0])]
        rows = []
        for key, label, b in benches:
            z = (s_ - b) / sd_
            rows.append(dict(key=key, label=label, benchmark=round(b, 3), z=round(z, 3), p=1 - Phi(z), verdict=verdict(z)))
        return dict(date=date, strength=round(s_, 3), sd=round(sd_, 3), gp=gp[OSU], rows=rows)

    today = dt.date.today()
    now_date = (today + dt.timedelta(days=1)).isoformat()
    ladder_now = ladder_at(now_date)
    hist, d = [], dt.date(2026, 9, 13)
    while d <= today:
        x = ladder_at(d.isoformat())
        if x:
            hist.append(dict(date=x["date"], strength=x["strength"], sd=x["sd"], gp=x["gp"], z={r["key"]: r["z"] for r in x["rows"]}))
        d += dt.timedelta(days=7)
    hist.append(dict(date=ladder_now["date"], strength=ladder_now["strength"], sd=ladder_now["sd"], gp=ladder_now["gp"],
                     z={r["key"]: r["z"] for r in ladder_now["rows"]}))

    # ---------- history ranks among M2 team-seasons
    s_now = m.final(); gp_now = m.gp_before("2999-01-01")
    rows = []
    for s in ANCHORED:
        ms = chain[s]; f = ms.final(); g = ms.gp_before("2999-01-01")
        mean2 = statistics.mean(v for t, v in f.items() if t.startswith("M2") and g[t] >= 5)
        resid = defaultdict(list)
        for gm in ms.games:
            pr = ms.predict(gm)
            d_ = max(-7, min(7, gm.hg - gm.ag))
            resid[gm.home].append(d_ - pr["margin"]); resid[gm.away].append(-d_ + pr["margin"])
        for t, v in f.items():
            if t.startswith("M2") and g[t] >= 5:
                rows.append(dict(season=s, team=t, strength=v, rel=v - mean2,
                                 z=sum(resid[t]) / (FITTED.sigma * math.sqrt(len(resid[t]))) if resid[t] else 0))
    def rank(key):
        srt = sorted(rows, key=lambda r: -r[key])
        i = next(i for i, r in enumerate(srt) if r["team"] == OSU and r["season"] == CUR)
        return dict(rank=i + 1, of=len(srt), value=round(srt[i][key], 3),
                    top=[dict(season=r["season"], team=short(r["team"]), value=round(r[key], 3)) for r in srt[:5]])
    # two-year rise relative to the M2 average
    rel = defaultdict(dict)
    for r in rows:
        rel[r["team"]][r["season"]] = r["rel"]
    rises = sorted(((v[b] - v[a], t, a, b) for t, v in rel.items() for a, b in zip(ANCHORED, ANCHORED[2:]) if a in v and b in v), reverse=True)
    osu_rise = next(((i + 1, x) for i, x in enumerate(rises) if x[1] == OSU and x[3] == CUR), None)
    # record vs combined M1+M2 top 25 at the time
    top25 = defaultdict(lambda: [0, 0, 0])
    osu_top25 = []
    for s in ANCHORED:
        ms = chain[s]; cache = {}
        for gm in ms.games:
            if gm.date not in cache:
                st = ms.strengths_before(gm.date); g = ms.gp_before(gm.date)
                pool = sorted(((v + (FITTED.gap_12 if t.startswith("M1") else 0), t) for t, v in st.items()
                               if t[:2] in ("M1", "M2") and g.get(t, 0) >= 3), reverse=True)
                cache[gm.date] = {t: i + 1 for i, (_, t) in enumerate(pool)}
            for me, opp, gf, ga in ((gm.home, gm.away, gm.hg, gm.ag), (gm.away, gm.home, gm.ag, gm.hg)):
                r_ = cache[gm.date].get(opp)
                if me.startswith("M2") and r_ and r_ <= 25:
                    x = top25[(s, me)]; x[0] += gf > ga; x[1] += gf < ga; x[2] += gf == ga
                    if me == OSU and s == CUR:
                        osu_top25.append(dict(date=gm.date, opp=short(opp), div=int(opp[1]), rank=r_, gf=gf, ga=ga))
    t25 = sorted(((v[0] + 0.5 * v[2]) / sum(v), k, v) for k, v in top25.items() if sum(v) >= 5)[::-1]
    osu_t25 = top25[(CUR, OSU)]
    history = dict(strength=rank("strength"), above_m2_avg=rank("rel"), beat_expectations=rank("z"),
                   rise=dict(rank=osu_rise[0] if osu_rise else None, of=len(rises), value=round(osu_rise[1][0], 2) if osu_rise else None,
                             top=[dict(team=short(t), seasons=f"{a}→{b}", value=round(v, 2)) for v, t, a, b in rises[:5]]),
                   top25=dict(record=osu_t25, games=osu_top25,
                              best=[dict(season=k[0], team=short(k[1]), record=v) for _, k, v in t25[:6]],
                              rank=next((i + 1 for i, (_, k, _) in enumerate(t25) if k == (CUR, OSU)), None), of=len(t25)),
                   osu_by_season=[dict(season=s, rel=round(rel[OSU][s], 2)) for s in ANCHORED if s in rel[OSU]])

    # ---------- champions
    so, sdo = s_now[OSU], sd_of(gp_now, OSU)
    champs = []
    for s, t in CHAMPIONS.items():
        ms = chain[s]; v = ms.final()[t]; sd = sd_of(ms.gp_before("2999-01-01"), t)
        champs.append(dict(season=s, team=short(t), strength=round(v, 2), p_osu_stronger=round(Phi((so - v) / math.sqrt(sdo ** 2 + sd ** 2)), 3)))
    import random
    rng = random.Random(5)
    pool = []
    for s in ANCHORED:
        ms = chain[s]; f = ms.final(); g = ms.gp_before("2999-01-01")
        for t, v in f.items():
            if t.startswith("M2") and g[t] >= 12 and not (s == CUR and t == OSU) and v > so - 3:
                pool.append((v, sd_of(g, t)))
    p_best = sum(all(rng.gauss(v, sd) < x for v, sd in pool) for x in (rng.gauss(so, sdo) for _ in range(4000))) / 4000

    # ---------- dominance: per-game performance and time leading
    def game_ratings(ms, team, f):
        out = []
        for gm in sorted(ms.games, key=lambda g: g.date):
            if team not in (gm.home, gm.away):
                continue
            home = gm.home == team; opp = gm.away if home else gm.home
            d_ = max(-7, min(7, (gm.hg - gm.ag) if home else (gm.ag - gm.hg)))
            adj = (-FITTED.home_edge if home else FITTED.home_edge) + (FITTED.gap(int(opp[1]), int(team[1])) if opp[1] != team[1] else 0)
            out.append(dict(date=gm.date, opp=short(opp), div=int(opp[1]), home=home, gf=gm.hg if home else gm.ag,
                            ga=gm.ag if home else gm.hg, rating=round(d_ + f[opp] + adj, 2)))
        return out
    m1_now = sorted([v + FITTED.gap_12 for t, v in s_now.items() if t.startswith("M1") and gp_now[t] >= 5], reverse=True)
    lvl25, lvl10 = m1_now[24], m1_now[9]
    osu_games = game_ratings(m, OSU, s_now)
    elite = []
    for s in ANCHORED:
        ms = chain[s]; f = ms.final(); g = ms.gp_before("2999-01-01")
        m1s = sorted([v + FITTED.gap_12 for t, v in f.items() if t.startswith("M1") and g[t] >= 5], reverse=True)
        for v, t in sorted(((v, t) for t, v in f.items() if t.startswith("M2") and g[t] >= 12), reverse=True)[:8]:
            gr = [x["rating"] for x in game_ratings(ms, t, f)]
            elite.append(dict(season=s, team=short(t), osu=t == OSU and s == CUR, share25=sum(x >= m1s[24] for x in gr) / len(gr),
                              share10=sum(x >= m1s[9] for x in gr) / len(gr), games=len(gr)))
    elite.sort(key=lambda r: (-r["share25"], -r["share10"]))
    # time leading (regulation), from goal events: OSU and every M1 team, 2026-27
    stats = json.load(open(os.path.join(ROOT, f"data/game_stats/{CUR}.json")))
    lead = defaultdict(lambda: dict(lead=0, trail=0, total=0, games=0, never_trailed=0))
    osu_m1_lead = dict(lead=0, trail=0, total=0, games=0, never_trailed=0)
    for gm in m.games:
        x = stats.get(gm.id)
        if not x or not x.get("goals"):
            continue
        evs = []
        for e in x["goals"]:
            if e["period"] in PER:
                mm, ss = e["time"].split(":"); evs.append((PER[e["period"]] * 1200 + int(mm) * 60 + int(ss), e["side"]))
        if sum(1 for _, sd in evs if sd == "home") > gm.hg or sum(1 for _, sd in evs if sd == "away") > gm.ag:
            continue
        reg_total = (gm.hg + gm.ag) - (1 if gm.ot and not gm.tie else 0)
        if len(evs) < reg_total:
            continue  # incomplete goal log
        evs.sort()
        for team, side in ((gm.home, "home"), (gm.away, "away")):
            if not (team.startswith("M1") or team == OSU):
                continue
            diff = t0 = L = T = 0; trailed = False
            for t_, sd in evs:
                L += (t_ - t0) * (diff > 0); T += (t_ - t0) * (diff < 0); trailed |= diff < 0
                diff += 1 if sd == side else -1; t0 = t_
            L += (3600 - t0) * (diff > 0); T += (3600 - t0) * (diff < 0); trailed |= diff < 0
            for r in ([lead[team]] + ([osu_m1_lead] if team == OSU and (gm.away if side == "home" else gm.home).startswith("M1") else [])):
                r["lead"] += L; r["trail"] += T; r["total"] += 3600; r["games"] += 1; r["never_trailed"] += not trailed
    lead_rows = sorted(((v["lead"] / v["total"], t, v) for t, v in lead.items() if v["games"] >= 8), reverse=True)
    dominance = dict(level_m1_25=round(lvl25, 2), level_m1_10=round(lvl10, 2), games=osu_games,
                     share25=sum(g["rating"] >= lvl25 for g in osu_games) / len(osu_games),
                     share10=sum(g["rating"] >= lvl10 for g in osu_games) / len(osu_games), elite=elite[:10],
                     osu_elite_rank=next(i + 1 for i, r in enumerate(elite) if r["osu"]), elite_n=len(elite),
                     lead=[dict(team=short(t), osu=t == OSU, lead=round(p, 3), trail=round(v["trail"] / v["total"], 3),
                                never_trailed=v["never_trailed"], games=v["games"]) for p, t, v in lead_rows[:10]],
                     osu_lead_rank=next(i + 1 for i, (_, t, _) in enumerate(lead_rows) if t == OSU), lead_n=len(lead_rows),
                     osu_m1_lead=dict(lead=round(osu_m1_lead["lead"] / osu_m1_lead["total"], 3) if osu_m1_lead["total"] else None,
                                      trail=round(osu_m1_lead["trail"] / osu_m1_lead["total"], 3) if osu_m1_lead["total"] else None,
                                      games=osu_m1_lead["games"], never_trailed=osu_m1_lead["never_trailed"]))

    # ---------- rivals & contenders
    title = json.load(open(os.path.join(ROOT, "data/title_odds.json")))
    T = title["teams"]
    contenders = [t for t, v in sorted(T.items(), key=lambda kv: -kv[1]["champ"]) if t != OSU[3:]][:7]
    west = [t for t, v in sorted(T.items(), key=lambda kv: -kv[1]["auto"]) if v["region"] == "West" and t != OSU[3:]][:3]
    # opponents' adjusted capped margins (for common-opponent comparison)
    res = defaultdict(lambda: defaultdict(list))
    for gm in m.games:
        d_ = max(-7, min(7, gm.hg - gm.ag))
        res[gm.home][gm.away].append(d_ - FITTED.home_edge); res[gm.away][gm.home].append(-d_ + FITTED.home_edge)
    upcoming = []
    for g in load_feed(CUR):
        if str(g["id"]) in excluded or g["game_status"].startswith("Final") or g["date_played"] < today.isoformat():
            continue
        hd, h = parse_team(g["home_team_name"]); ad, a = parse_team(g["visiting_team_name"])
        if OSU in (f"M{hd} {h}", f"M{ad} {a}"):
            upcoming.append((g["date_played"], f"M{hd} {h}", f"M{ad} {a}"))
    rivals = []
    for t in dict.fromkeys(contenders + west):
        k = "M2 " + t
        if k not in s_now:
            continue
        sdr = sd_of(gp_now, k)
        margin = so - s_now[k]
        rec = [0, 0, 0]
        for gm in m.games:
            if k in (gm.home, gm.away):
                me_h = gm.home == k; gf, ga = (gm.hg, gm.ag) if me_h else (gm.ag, gm.hg)
                rec[0] += gf > ga; rec[1] += gf < ga; rec[2] += gf == ga
        h2h = [dict(date=gm.date, osu_home=gm.home == OSU, osu=gm.hg if gm.home == OSU else gm.ag, them=gm.ag if gm.home == OSU else gm.hg, ot=gm.ot)
               for gm in m.games if {gm.home, gm.away} == {OSU, k}]
        meets = []
        for date, h, a in upcoming:
            if k in (h, a):
                xg = XGame("x", CUR, date, h, a, int(h[1]), int(a[1]), 0, 0, False, False)
                pr = m.predict(xg)
                meets.append(dict(date=date, osu_home=h == OSU, p_osu=round(pr["p_home"] if h == OSU else 1 - pr["p_home"], 3)))
        common = sorted(set(res[OSU]) & set(res[k]) - {OSU, k})
        cdiff = [statistics.mean(res[OSU][o]) - statistics.mean(res[k][o]) for o in common]
        rivals.append(dict(team=t and short(k), region=T[t]["region"], strength=round(s_now[k], 2), sd=round(sdr, 2),
                           p_osu_stronger=round(Phi(margin / math.sqrt(sdo ** 2 + sdr ** 2)), 3),
                           p_osu_neutral=round(p_home_win(margin, math.sqrt(FITTED.sigma ** 2 + sdo ** 2 + sdr ** 2)), 3),
                           record=rec, title=T[t]["champ"], nationals=T[t]["nat"], h2h=h2h, upcoming=meets,
                           common=len(common), common_margin=round(statistics.mean(cdiff), 2) if cdiff else None,
                           kind="West chaser" if t in west and t not in contenders else "Title contender"))

    out = dict(generated_at=dt.datetime.now().isoformat(timespec="minutes"), ladder=ladder_now, ladder_history=hist,
               history=history, champions=champs, p_best_m2_season=round(p_best, 3), dominance=dominance, rivals=rivals,
               osu_title=title["osu"], osu_opponents=title.get("osu_opponents"),
               osu=dict(strength=round(so, 2), sd=round(sdo, 2), gp=gp_now[OSU]))
    path = os.path.join(ROOT, "data/significance.json")
    old = json.load(open(path)) if os.path.exists(path) else {}
    if {k: v for k, v in old.items() if k != "generated_at"} != json.loads(json.dumps({k: v for k, v in out.items() if k != "generated_at"})):
        with open(path, "w") as f:
            json.dump(out, f, indent=1)
    print("ladder:", [(r["key"], r["z"], r["verdict"]) for r in ladder_now["rows"]])
    print("history weeks:", [(h["date"], h["z"]["avg_m1"], h["z"]["m1_25"]) for h in hist])
    print("ranks:", {k: (v["rank"], v["of"]) for k, v in history.items() if isinstance(v, dict) and "rank" in v})
    print("dominance: share25 %.0f%% share10 %.0f%% elite rank %d/%d | lead rank %d/%d | OSU vs M1 lead %s" % (
        100 * dominance["share25"], 100 * dominance["share10"], dominance["osu_elite_rank"], dominance["elite_n"],
        dominance["osu_lead_rank"], dominance["lead_n"], dominance["osu_m1_lead"]))
    print("rivals:", [(r["team"], r["p_osu_neutral"], r["h2h"], r["upcoming"]) for r in rivals])
    print("champions:", [(c["season"], c["p_osu_stronger"]) for c in champs], "P(best)", p_best)


if __name__ == "__main__":
    main()
