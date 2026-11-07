"""Cross-division strength model: every ACHA men's team (M1, M2, M3) on one goal-unit scale.

This is a prediction model, separate from the official ACHA formulas. For a team t:

    (gp_t + k) * s_t - sum(s_opp) = sum(GD - home_edge * side) + k * prior_t

i.e. a team's strength is its average (capped GD + opponent strength), with home edge removed and
its prior counted as k extra games. The prior is last season's final strength regressed toward its
division's average (slope b); teams without one get their division's average. Cross-division games
are what tie the three divisions to one scale.

Win probability: margin ~ Normal(s_home - s_away + home_edge, sigma). |margin| < 0.5 is an OT
game, split 50/50 (cross-division games can still end tied; those count as half a win when scoring).
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from engine.allgames import MEN_SEASONS, XGame, games

SEASONS = list(MEN_SEASONS)


FITTED = None  # set below


@dataclass
class Params:
    k: float = 3.0           # prior weight, in games
    b: float = 0.7           # regression of last season's strength toward the division mean
    home_edge: float = 0.25  # goals
    sigma: float = 2.7       # game-to-game spread, goals
    cap: int = 7
    # Extra goals for the higher division in cross-division games, on top of the shared scale.
    # Fitted by recency-weighted log loss on 2022-23..2026-27 cross-division games (see FINDINGS §8).
    gap_12: float = 0.0
    gap_13: float = 0.0
    gap_23: float = 0.0

    def gap(self, home_div: int, away_div: int) -> float:
        """Margin adjustment for the home side: + if home is the higher division."""
        if home_div == away_div:
            return 0.0
        g = {frozenset((1, 2)): self.gap_12, frozenset((1, 3)): self.gap_13,
             frozenset((2, 3)): self.gap_23}[frozenset((home_div, away_div))]
        return g if home_div < away_div else -g


def div_of(team: str) -> int:
    return int(team[1])


def solve_strength(gs: list[XGame], priors: dict[str, float], div_prior: dict[int, float], p: Params,
                   teams: list[str] | None = None) -> dict[str, float]:
    teams = sorted(set(teams or []) | {t for g in gs for t in (g.home, g.away)} | set(priors))
    ix = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    M = np.zeros((n, n))
    rhs = np.zeros(n)
    for t, i in ix.items():
        pr = priors.get(t, div_prior.get(div_of(t), 0.0))
        M[i, i] += p.k
        rhs[i] += p.k * pr
    for g in gs:
        d = 0.0 if g.tie else float(max(-p.cap, min(p.cap, g.hg - g.ag)))
        h, a = ix[g.home], ix[g.away]
        M[h, h] += 1; M[h, a] -= 1; rhs[h] += d - p.home_edge
        M[a, a] += 1; M[a, h] -= 1; rhs[a] += -d + p.home_edge
    s = np.linalg.solve(M, rhs)
    return {t: float(s[i]) for t, i in ix.items()}


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def p_home_win(margin: float, sd: float) -> float:
    reg = 1 - _phi((0.5 - margin) / sd)
    ot = _phi((0.5 - margin) / sd) - _phi((-0.5 - margin) / sd)
    return reg + ot / 2


def season_priors(prev_final: dict[str, float], p: Params) -> tuple[dict[str, float], dict[int, float]]:
    """Regress last season's final strengths toward each division's mean."""
    by = defaultdict(list)
    for t, v in prev_final.items():
        by[div_of(t)].append(v)
    mu = {d: float(np.mean(v)) for d, v in by.items()}
    pri = {t: mu[div_of(t)] + p.b * (v - mu[div_of(t)]) for t, v in prev_final.items()}
    return pri, mu


class SeasonModel:
    """Strengths for one season as of any date, using only games played before it."""

    def __init__(self, season: str, p: Params, prev_final: dict[str, float] | None,
                 games_override: list[XGame] | None = None):
        self.season, self.p = season, p
        self.games = games_override if games_override is not None else games(season)
        if prev_final:
            self.priors, self.div_prior = season_priors(prev_final, p)
        else:  # first season: no history, every division starts level
            self.priors, self.div_prior = {}, {1: 0.0, 2: 0.0, 3: 0.0}
        self._cache: dict[str, dict[str, float]] = {}

    def strengths_before(self, date: str) -> dict[str, float]:
        if date not in self._cache:
            self._cache[date] = solve_strength([g for g in self.games if g.date < date], self.priors, self.div_prior, self.p)
        return self._cache[date]

    def final(self) -> dict[str, float]:
        return solve_strength(self.games, self.priors, self.div_prior, self.p)

    def gp_before(self, date: str) -> dict[str, int]:
        c = defaultdict(int)
        for g in self.games:
            if g.date < date:
                c[g.home] += 1; c[g.away] += 1
        return c

    def predict(self, g: XGame) -> dict:
        s = self.strengths_before(g.date)
        dp = self.div_prior
        sh = s.get(g.home, self.priors.get(g.home, dp.get(div_of(g.home), 0.0)))
        sa = s.get(g.away, self.priors.get(g.away, dp.get(div_of(g.away), 0.0)))
        margin = sh - sa + self.p.home_edge + self.p.gap(div_of(g.home), div_of(g.away))
        return dict(margin=margin, p_home=p_home_win(margin, self.p.sigma), s_home=sh, s_away=sa)


def build_chain(p: Params, through_season: str | None = None) -> dict[str, SeasonModel]:
    """SeasonModels for every season in order, each seeded with the previous season's final strengths."""
    out, prev = {}, None
    for season in SEASONS:
        m = SeasonModel(season, p, prev)
        out[season] = m
        prev = m.final()
        if season == through_season:
            break
    return out


# Calibrated values (scripts/calibrate_xdiv.py + FINDINGS §8)
FITTED = Params(k=2, b=0.6, home_edge=0.328, sigma=3.0, gap_12=0.65, gap_13=0.85, gap_23=0.5)
