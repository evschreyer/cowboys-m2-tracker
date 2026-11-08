"""All-division ACHA men's game loader (M1, M2, M3 and cross-division games).

The HockeyTech feed prefixes team names with the division: "MD1 Ohio University" from 2023-24 on,
"M1 Ohio University" before that. Teams are keyed as "M1 Ohio University" etc. so the same school's
programs in different divisions stay distinct.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass

from engine.engine import plausible_final

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# HockeyTech season ids for the men's regular season ("Men's Divisions")
MEN_SEASONS = {"2021-22": 10, "2022-23": 21, "2023-24": 34, "2024-25": 46, "2025-26": 60, "2026-27": 73}
FEED_URL = ("https://lscluster.hockeytech.com/feed/index.php?feed=modulekit&view=schedule&season_id={sid}"
            "&key=e6867b36742a0c9d&client_code=acha&fmt=json&lang=en")

_DIV = re.compile(r"^M(?:D)?([123]) (.+)$")
FINAL = ("Final", "Final OT", "Final OT2", "Final SO", "Unofficial Final")


def parse_team(feed_name: str) -> tuple[int | None, str]:
    """'MD2 Oklahoma State University' -> (2, 'Oklahoma State University'). Non-ACHA -> (None, name)."""
    m = _DIV.match(feed_name.strip())
    return (int(m.group(1)), m.group(2).strip()) if m else (None, feed_name.strip())


def key(div: int, school: str) -> str:
    return f"M{div} {school}"


@dataclass
class XGame:
    id: str
    season: str
    date: str
    home: str          # "M1 Ohio University"
    away: str
    hdiv: int
    adiv: int
    hg: int
    ag: int
    ot: bool
    so: bool

    @property
    def cross(self) -> bool:
        return self.hdiv != self.adiv

    @property
    def tie(self) -> bool:
        """Cross-division games can end tied after OT (no shootout); recorded score shows it."""
        return self.hg == self.ag


def feed_path(season: str) -> str:
    return os.path.join(ROOT, "data/feeds", f"season{MEN_SEASONS[season]}.json")


def load_feed(season: str, refresh: bool = False) -> list[dict]:
    path = feed_path(season)
    if refresh or not os.path.exists(path):
        req = urllib.request.Request(FEED_URL.format(sid=MEN_SEASONS[season]), headers={"User-Agent": "osu-m2-rankings/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        json.loads(data)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
    with open(path) as f:
        return json.load(f)["SiteKit"]["Schedule"]


def games(season: str, through: str = "9999-12-31", divisions: set[int] | None = None,
          refresh: bool = False) -> list[XGame]:
    """Completed ACHA men's games (forfeits excluded). divisions limits to games where BOTH teams
    are in the set; None = every game between two ACHA men's teams."""
    out = []
    ov_path = os.path.join(ROOT, f"data/overrides_{season}.json")
    excluded = set(map(str, json.load(open(ov_path)).get("exclude_game_ids", []))) if os.path.exists(ov_path) else set()
    for g in load_feed(season, refresh):
        if str(g["id"]) in excluded:
            continue
        if g["game_status"] not in FINAL or g["date_played"] > through or not plausible_final(g):
            continue
        hd, h = parse_team(g["home_team_name"])
        ad, a = parse_team(g["visiting_team_name"])
        if not hd or not ad or "TBD" in (h, a):
            continue
        if divisions and not (hd in divisions and ad in divisions):
            continue
        so = g.get("shootout", "0") != "0" or "SO" in g["game_status"]
        ot = so or g.get("overtime", "0") != "0" or "OT" in g["game_status"]
        out.append(XGame(str(g["id"]), season, g["date_played"], key(hd, h), key(ad, a), hd, ad,
                         int(g["home_goal_count"]), int(g["visiting_goal_count"]), ot, so))
    return sorted(out, key=lambda x: (x.date, x.id))
