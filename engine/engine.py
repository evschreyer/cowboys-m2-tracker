"""ACHA Men's Division 2 ranking engine (reconstruction).

Reference implementation. engine/engine.js must produce identical numbers.

Formula, validated against the official 2025-26 ACHA raw-data and full-ranking files:
    GD          = clamp(goals_for - goals_against, -CAP, CAP)    CAP = 7
    GmPerf      = mean(GD) over M2-vs-M2 games
    Sched       = mean(Total of opponents)
    Total       = GmPerf + Sched            solved iteratively; GP-weighted mean pinned at START = 7.0
    OTAdj       = 0.5 * OTL / GP            added after convergence (does not feed opponents' Sched)
    RawRating   = Total + OTAdj
    AWP         = 0.8 * W / (W + L)
    FinalRating = RawRating + AWP - Penalty
Ranked by FinalRating within region. Forfeits are excluded from the math (ACHA Manual Part Five
Art. IV Sec. 5 applies the penalty post-calculation instead). League-playoff OT games count as ties (Sec. 3C).
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field, asdict

CAP = 7
START = 7.0
OT_ADJ = 0.5
AWP_WEIGHT = 0.8
MIN_GP_RANKED = 3
PENALTY_PER_FORFEIT = 0.25

FINAL_STATUSES = ("Final", "Final OT", "Final OT2", "Final SO", "Unofficial Final")
FORFEIT_STATUSES = ("Home Forfeit", "Visiting Forfeit")


@dataclass
class Game:
    id: str
    date: str
    home: str
    away: str
    hg: int
    ag: int
    ot: bool = False
    so: bool = False
    tie: bool = False  # forced tie (league-playoff OT rule)

    def gd_home(self, cap: int = CAP) -> float:
        if self.tie:
            return 0.0
        return float(max(-cap, min(cap, self.hg - self.ag)))


@dataclass
class TeamRating:
    team: str
    gp: int = 0
    w: int = 0
    l: int = 0
    t: int = 0
    otw: int = 0
    otl: int = 0
    gf: int = 0
    ga: int = 0
    gmperf: float = 0.0
    sched: float = 0.0
    total: float = 0.0
    otadj: float = 0.0
    raw: float = 0.0
    awp: float = 0.0
    penalty: float = 0.0
    final: float = 0.0
    region: str | None = None
    rank: int | None = None
    status: str = "ranked"  # ranked | min_games | not_good_standing
    opponents: list = field(default_factory=list)


def m2_name(feed_name: str) -> str | None:
    return feed_name[4:].strip() if feed_name.startswith("MD2 ") else None


def load_feed(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)["SiteKit"]["Schedule"]


def games_from_feed(schedule: list[dict], cutoff: str, overrides: dict | None = None,
                    start: str = "0000-00-00") -> tuple[list[Game], list[dict]]:
    """M2-vs-M2 completed games with start <= date <= cutoff (ISO dates).

    Returns (games, forfeits). Overrides keys used here:
      exclude_game_ids [id], score_fixes {id: {"hg","ag"}}, tie_game_ids [id],
      add_games [{id,date,home,away,hg,ag,ot,so}], aliases {feed_name: canonical}.
    """
    ov = overrides or {}
    alias = ov.get("aliases", {})
    excl = set(map(str, ov.get("exclude_game_ids", [])))
    fixes = {str(k): v for k, v in ov.get("score_fixes", {}).items()}
    ties = set(map(str, ov.get("tie_game_ids", [])))
    games, forfeits = [], []
    for g in schedule:
        h, a = m2_name(g["home_team_name"]), m2_name(g["visiting_team_name"])
        if not h or not a or not (start <= g["date_played"] <= cutoff):
            continue
        h, a = alias.get(h, h), alias.get(a, a)
        gid, st = str(g["id"]), g["game_status"]
        if gid in excl:
            continue
        if st in FORFEIT_STATUSES:
            forfeiter = h if st == "Home Forfeit" else a
            forfeits.append({"id": gid, "date": g["date_played"], "home": h, "away": a, "forfeiter": forfeiter})
            continue
        if st not in FINAL_STATUSES and gid not in fixes:
            continue
        hg, ag = int(g["home_goal_count"]), int(g["visiting_goal_count"])
        if gid in fixes:
            hg, ag = int(fixes[gid]["hg"]), int(fixes[gid]["ag"])
        so = g.get("shootout", "0") != "0" or "SO" in st
        ot = so or g.get("overtime", "0") != "0" or "OT" in st
        games.append(Game(gid, g["date_played"], h, a, hg, ag, ot, so, gid in ties))
    for x in ov.get("add_games", []):
        if x.get("date", "") <= cutoff:
            games.append(Game(str(x["id"]), x["date"], x["home"], x["away"], int(x["hg"]), int(x["ag"]),
                              bool(x.get("ot")), bool(x.get("so")), bool(x.get("tie"))))
    return games, forfeits


def solve(games: list[Game], cap: int = CAP, start: float = START, tol: float = 1e-10,
          max_iter: int = 100000) -> dict[str, TeamRating]:
    """Compute ratings. Damped Jacobi iteration: same fixed point and same GP-weighted mean
    as the plain recursion, but it also converges on bipartite (early-season) schedules."""
    teams: dict[str, TeamRating] = {}
    gd_sum = defaultdict(float)
    for g in games:
        d = g.gd_home(cap)
        for me, opp, dd, gf, ga in ((g.home, g.away, d, g.hg, g.ag), (g.away, g.home, -d, g.ag, g.hg)):
            r = teams.setdefault(me, TeamRating(me))
            r.gp += 1
            r.gf += gf
            r.ga += ga
            r.opponents.append(opp)
            gd_sum[me] += dd
            if g.tie or dd == 0:
                r.t += 1
            elif dd > 0:
                r.w += 1
                r.otw += g.ot
            else:
                r.l += 1
                r.otl += g.ot
    for r in teams.values():
        r.gmperf = gd_sum[r.team] / r.gp
    R = {t: start for t in teams}
    for _ in range(max_iter):
        new = {}
        delta = 0.0
        for t, r in teams.items():
            target = r.gmperf + sum(R[o] for o in r.opponents) / r.gp
            v = 0.5 * R[t] + 0.5 * target
            delta = max(delta, abs(v - R[t]))
            new[t] = v
        R = new
        if delta < tol:
            break
    for t, r in teams.items():
        r.total = R[t]
        r.sched = sum(R[o] for o in r.opponents) / r.gp
        r.otadj = OT_ADJ * r.otl / r.gp
        r.raw = r.total + r.otadj
        r.awp = AWP_WEIGHT * r.w / (r.w + r.l) if (r.w + r.l) else 0.0
    return teams


def rank(teams: dict[str, TeamRating], regions: dict[str, str], penalties: dict[str, float] | None = None,
         not_good_standing: set[str] | None = None, min_gp: int = MIN_GP_RANKED) -> dict[str, list[TeamRating]]:
    """Apply penalties, assign regions, rank within region.
    Tiebreak order: Final, Raw, Sched (ACHA 2024 article cites SOS as 3rd criterion)."""
    penalties = penalties or {}
    ngs = not_good_standing or set()
    out: dict[str, list[TeamRating]] = defaultdict(list)
    for t, r in teams.items():
        r.penalty = penalties.get(t, 0.0)
        r.final = r.raw + r.awp - r.penalty
        r.region = regions.get(t)
        r.status = "not_good_standing" if t in ngs else ("min_games" if r.gp < min_gp else "ranked")
        out[r.region or "Unassigned"].append(r)
    for reg, lst in out.items():
        lst.sort(key=lambda r: (r.status != "ranked", -r.final, -r.raw, -r.sched))
        n = 0
        for r in lst:
            if r.status == "ranked":
                n += 1
                r.rank = n
            else:
                r.rank = None
    return dict(out)


def components(teams: dict[str, TeamRating]) -> dict[str, int]:
    """Connected groups of the schedule graph (0 = largest). Ratings are only comparable
    within a group; each group's GP-weighted mean is pinned at START independently."""
    comp: dict[str, int] = {}
    groups = []
    for t in teams:
        if t in comp:
            continue
        stack, members = [t], []
        comp[t] = -1
        while stack:
            x = stack.pop()
            members.append(x)
            for o in teams[x].opponents:
                if o not in comp:
                    comp[o] = -1
                    stack.append(o)
        groups.append(members)
    groups.sort(key=len, reverse=True)
    for i, g in enumerate(groups):
        for t in g:
            comp[t] = i
    return comp


def forfeit_penalties(forfeits: list[dict]) -> dict[str, float]:
    """Suggested penalties: 0.25 per forfeited game (ineligible-player cases need manual entry)."""
    p = defaultdict(float)
    for f in forfeits:
        p[f["forfeiter"]] += PENALTY_PER_FORFEIT
    return dict(p)


def to_dict(r: TeamRating) -> dict:
    d = asdict(r)
    d.pop("opponents")
    return d
