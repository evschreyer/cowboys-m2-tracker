"""Backtest engine/m1rank.py against ACHA's published M1 computer rankings.

Usage: python3 scripts/backtest_m1.py
"""
from __future__ import annotations

import glob
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scripts")]

from engine.allgames import games  # noqa: E402
from engine.m1rank import m1_games, ranking  # noqa: E402
from official import match_names, parse_m1_computer  # noqa: E402


def main():
    print(f"{'thru':10} {'teams':>5} {'A exact':>8} {'B exact':>8} {'rank exact':>10} {'rank ±1':>8} "
          f"{'mean miss':>9} {'top10':>6} {'top25':>6} {'top24 set':>9}")
    tot = dict(a=0, b=0, r=0, r1=0, n=0)
    for f in sorted(glob.glob(os.path.join(ROOT, "data/official/m1/*/computer_*.pdf"))):
        season = os.path.basename(os.path.dirname(f))
        thru = os.path.basename(f)[9:19]
        off = parse_m1_computer(f)
        rows = {r.team: r for r in ranking(m1_games(games(season, through=thru)))}
        m = match_names(list(off), list(rows))
        n = len(m)
        a = sum(off[o]["A"] == rows[t].rank_a for o, t in m.items())
        b = sum(off[o]["B"] == rows[t].rank_b for o, t in m.items())
        r = sum(off[o]["rank"] == rows[t].rank for o, t in m.items())
        r1 = sum(abs(off[o]["rank"] - rows[t].rank) <= 1 for o, t in m.items())
        miss = statistics.mean(abs(off[o]["rank"] - rows[t].rank) for o, t in m.items())
        top = lambda k: len({o for o in m if off[o]["rank"] <= k} & {o for o, t in m.items() if rows[t].rank <= k})
        print(f"{thru:10} {n:5d} {a:4d}/{n:<3d} {b:4d}/{n:<3d} {r:6d}/{n:<3d} {r1:4d}/{n:<3d} {miss:9.2f} "
              f"{top(10):4d}/10 {top(25):4d}/25 {top(24):5d}/24")
        for k, v in (("a", a), ("b", b), ("r", r), ("r1", r1), ("n", n)):
            tot[k] += v
    n = tot["n"]
    print(f"\nall rankings: A exact {tot['a']/n:.1%}, B exact {tot['b']/n:.1%}, "
          f"final rank exact {tot['r']/n:.1%}, within one place {tot['r1']/n:.1%}")


if __name__ == "__main__":
    main()
