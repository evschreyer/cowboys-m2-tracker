"""ACHA Men's Division 1 computer ranking (reconstruction), validated against ACHA's published
"Computer Poll Average" PDFs (scripts/backtest_m1.py).

Rules (ACHA Manual 2026-27, Part Four, Art. IV §1):
  - one national ranking from Nov 1 on (coaches' poll before that)
  - only M1 vs M1 games count; every OT or shootout game counts as a tie
  - Ranking A: rating with goal differential capped at 7; Ranking B: capped at 1 (W/L/T only)
  - published rank = order of the AVERAGE OF THE TWO RANK POSITIONS; ties broken by Ranking B
  - the home-game imbalance penalty (§1F) is not visible in published rankings, so it isn't modeled
Ratings use the same recursive method as the M2 engine (engine.solve).
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.allgames import XGame
from engine.engine import Game, solve


@dataclass
class M1Row:
    team: str           # school name without the "M1 " prefix
    rank: int
    rank_a: int
    rank_b: int
    avg: float
    rating_a: float     # goal units
    rating_b: float     # win-percentage units
    gp: int
    w: int
    l: int
    t: int


def m1_games(games: list[XGame], extra: list[XGame] | None = None) -> list[Game]:
    """M1-vs-M1 games as engine Games (OT/SO -> tie). `extra` adds games for a guest team
    (e.g. OSU's games vs M1 teams) to rank it as if it were an M1 member."""
    picked = {g.id: g for g in games if g.hdiv == 1 and g.adiv == 1}
    for g in extra or []:
        picked.setdefault(g.id, g)
    return [Game(g.id, g.date, g.home[3:], g.away[3:], g.hg, g.ag, g.ot, g.so, tie=g.ot or g.tie)
            for g in sorted(picked.values(), key=lambda g: (g.date, g.id))]


def ranking(games: list[Game]) -> list[M1Row]:
    A = solve(games, cap=7)
    B = solve(games, cap=1)
    ra = {r.team: i + 1 for i, r in enumerate(sorted(A.values(), key=lambda r: -r.total))}
    rb = {r.team: i + 1 for i, r in enumerate(sorted(B.values(), key=lambda r: -r.total))}
    order = sorted(A, key=lambda t: ((ra[t] + rb[t]) / 2, rb[t]))
    rows = []
    for i, t in enumerate(order):
        a, b = A[t], B[t]
        rows.append(M1Row(t, i + 1, ra[t], rb[t], (ra[t] + rb[t]) / 2, a.total, b.total, a.gp, a.w, a.l, a.t))
    return rows
