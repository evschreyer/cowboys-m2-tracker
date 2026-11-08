"""Download and compact box-score stats for the games the M1 study needs.

Selection (per season): every M1-vs-M2 game, plus every game played by the focus team;
in the current season, every game involving an M1 team.
Usage: python3 scripts/fetch_game_stats.py [--seasons 2025-26 2026-27] [--refresh-feed]
Writes data/game_stats/<season>.json  ({game_id: compact stats}).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.allgames import MEN_SEASONS, games  # noqa: E402
from engine.gamestats import compact, fetch_summary  # noqa: E402

FOCUS = "M2 Oklahoma State University"


def selected(season: str, refresh: bool) -> list:
    """Every M1-vs-M2 game and every focus-team game; in the current season also every game
    involving an M1 team (for the OSU-vs-M1 stat comparison)."""
    current = season == list(MEN_SEASONS)[-1]
    return [g for g in games(season, refresh=refresh)
            if {g.hdiv, g.adiv} == {1, 2} or FOCUS in (g.home, g.away) or (current and 1 in (g.hdiv, g.adiv))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="*", default=list(MEN_SEASONS))
    ap.add_argument("--refresh-feed", action="store_true")
    args = ap.parse_args()
    out_dir = os.path.join(ROOT, "data/game_stats")
    os.makedirs(out_dir, exist_ok=True)
    for season in args.seasons:
        path = os.path.join(out_dir, f"{season}.json")
        stats = json.load(open(path)) if os.path.exists(path) else {}
        todo = selected(season, args.refresh_feed and season == list(MEN_SEASONS)[-1])
        new = 0
        for g in todo:
            if g.id in stats:
                continue
            stats[g.id] = compact(fetch_summary(g.id))
            new += 1
        with open(path, "w") as f:
            json.dump(dict(sorted(stats.items())), f, separators=(",", ":"))
        ok = sum(s["shots_ok"] for s in stats.values())
        print(f"{season}: {len(todo)} games selected, {new} fetched, {len(stats)} stored, shots tracked in {ok}")


if __name__ == "__main__":
    main()
