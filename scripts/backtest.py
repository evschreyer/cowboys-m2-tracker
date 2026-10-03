"""Backtest the engine against every official 2025-26 ACHA M2 ranking.

Usage: python3 scripts/backtest.py [--team "Oklahoma State University"]
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from engine.engine import load_feed, games_from_feed, solve  # noqa: E402
from official import parse_raw_pdf, match_names  # noqa: E402

RANKINGS_2025_26 = [  # (label, games-through date) from achahockey.org/m2-rankings
    ("R1", "2025-11-09"), ("R2", "2025-11-16"), ("R3", "2025-11-24"), ("R4", "2025-12-07"),
    ("R5", "2025-12-14"), ("R6", "2026-01-18"), ("R7", "2026-01-25"), ("R8", "2026-02-01"),
    ("R9", "2026-02-08"),
]


def final_rating(x: dict) -> float:
    w, l = x["W"], x["L"]
    return x["Total"] + 0.8 * w / (w + l) if w + l else x["Total"]


def evaluate(label: str, cutoff: str, feed: list, team: str | None) -> dict:
    off = parse_raw_pdf(os.path.join(ROOT, "data/official/2025-26", f"{label}_raw.pdf"))
    games, _ = games_from_feed(feed, cutoff)
    mine = solve(games)
    m = match_names(list(off), list(mine))
    unmatched = [o for o in off if o not in m]
    err = [off[o]["Total"] - mine[m[o]].raw for o in m]
    rec_ok = [o for o in m if (off[o]["W"], off[o]["L"]) == (mine[m[o]].w, mine[m[o]].l)]
    err_ok = [off[o]["Total"] - mine[m[o]].raw for o in rec_ok]
    # Regional ordering by Final Rating (official uses their records, ours uses ours)
    top = {"exact16": 0, "set16": 0, "top2": 0, "n16": 0}
    for reg in ("Northeast", "Southeast", "Central", "West"):
        teams = [o for o in m if off[o]["region"] == reg and off[o]["rank"] is not None]
        oo = sorted(teams, key=lambda o: -final_rating(off[o]))
        mm = sorted(teams, key=lambda o: -(mine[m[o]].raw + mine[m[o]].awp))
        k = min(16, len(oo))
        top["n16"] += k
        top["exact16"] += sum(oo[i] == mm[i] for i in range(k))
        top["set16"] += len(set(oo[:k]) & set(mm[:k]))
        top["top2"] += len(set(oo[:2]) & set(mm[:2]))
    res = dict(label=label, cutoff=cutoff, games=len(games), teams_off=len(off), unmatched=unmatched,
               mae=statistics.mean(abs(e) for e in err), bias=statistics.mean(err),
               max_err=max(abs(e) for e in err), rec_match=len(rec_ok) / len(m),
               mae_rec_ok=statistics.mean(abs(e) for e in err_ok), **top)
    if team:
        o = next((k for k, v in m.items() if v == team), None)
        if o:
            a, b = off[o], mine[team]
            res["team"] = (f"official {a['W']}-{a['L']} GmPerf {a['GmPerf']:.1f} Sched {a['Sched']:.1f} "
                           f"Total {a['Total']:.2f} #{a['rank']} | ours {b.w}-{b.l} GmPerf {b.gmperf:.2f} "
                           f"Sched {b.sched:.2f} Raw {b.raw:.2f}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", default="Oklahoma State University")
    args = ap.parse_args()
    feed = load_feed(os.path.join(ROOT, "data/feeds/season60.json"))
    print(f"{'Rk':3} {'thru':10} {'games':>5} {'MAE':>6} {'bias':>6} {'max':>5} {'rec%':>5} {'MAE*':>6} "
          f"{'top2':>5} {'top16 set':>9} {'top16 exact':>11}")
    for label, cutoff in RANKINGS_2025_26:
        r = evaluate(label, cutoff, feed, args.team)
        print(f"{label:3} {cutoff:10} {r['games']:5d} {r['mae']:6.3f} {r['bias']:6.3f} {r['max_err']:5.2f} "
              f"{100*r['rec_match']:4.0f}% {r['mae_rec_ok']:6.3f} {r['top2']:3d}/8 "
              f"{r['set16']:4d}/{r['n16']:<4d} {r['exact16']:6d}/{r['n16']}")
        if r["unmatched"]:
            print("    unmatched:", r["unmatched"])
        if "team" in r:
            print("    ", r["team"])
    print("\nMAE* = mean abs error on teams whose W-L matches the official record exactly.")


if __name__ == "__main__":
    main()
