"""Parse ACHA official M2 raw-data PDFs and map their team names to HockeyTech feed names."""
from __future__ import annotations

import difflib
import re

import pypdf

REGIONS = ("Northeast", "Southeast", "Central", "West")
ROW = re.compile(
    r"^\s*(-|\d+)\s*,(.+?)_+\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+),\s*(-?\s*[\d.]+),\s*(-?\s*[\d.]+),"
    r"\s*(-?[\d.]+)\s+(-?[\d.]+),")

# Official-name -> feed-name exceptions that fuzzy matching gets wrong.
MANUAL_ALIASES: dict[str, str] = {}


def parse_raw_pdf(path: str) -> dict[str, dict]:
    text = "\n".join(p.extract_text() for p in pypdf.PdfReader(path).pages)
    rows, region = {}, None
    for line in text.splitlines():
        s = line.strip()
        if s in REGIONS:
            region = s
            continue
        m = ROW.match(line)
        if not m:
            continue
        g = m.groups()
        num = lambda x: float(x.replace(" ", ""))
        rows[re.sub(r"[\s,_\\]+$", "", g[1])] = dict(region=region, rank=None if g[0] == "-" else int(g[0]),
                                  W=int(g[2]), L=int(g[3]), T=int(g[4]), OTW=int(g[5]), OTL=int(g[6]),
                                  GmPerf=num(g[7]), Sched=num(g[8]), OTAdj=num(g[9]), Total=num(g[10]))
    return rows


def _norm(s: str) -> str:
    s = s.lower().replace("&", "and").replace(".", "").replace("-", " ")
    s = re.sub(r"\(.*?\)", "", s)
    for w in ("university of ", " university", "college of ", " college", "the ", "saint ", "st "):
        s = s.replace(w, " ")
    return re.sub(r"\s+", " ", s).strip()


def match_names(official: list[str], feed: list[str]) -> dict[str, str]:
    """official name -> feed name (best fuzzy match on normalized names)."""
    norm_feed = {_norm(f): f for f in feed}
    out = {}
    for o in official:
        if o in MANUAL_ALIASES:
            out[o] = MANUAL_ALIASES[o]
            continue
        if o in feed:
            out[o] = o
            continue
        c = difflib.get_close_matches(_norm(o), list(norm_feed), 1, 0.75)
        if c:
            out[o] = norm_feed[c[0]]
    return out
