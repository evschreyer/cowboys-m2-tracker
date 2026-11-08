"""Validate the dashboard against an official ACHA M2 ranking release.

Run as soon as a release drops:
  python3 scripts/validate_official.py --label R1 --thru 2026-11-08
        [--season 2026-27] [--raw data/official/2026-27/R1_raw.pdf] [--full data/official/2026-27/R1_full.xlsx]
        [--no-fetch]

Checks (each PASS / WARN / FAIL):
  1  files parsed                    raw-data PDF and full-rankings PDF/XLSX
  2  formula unchanged               Final = Raw + AWP - Penalty; AWP = 0.8 W/(W+L); OTAdj = 0.5 OTL/GP;
                                     GP-weighted mean of (Total - OTAdj) = 7.0; raw Total == full Raw
  3  team names                      every official team maps to a HockeyTech team
  4  team set                        teams we rate that ACHA does not list, and vice versa
  5  regions                         official region vs data/regions_<season>.json
  6  records                         W/L/T/OTW/OTL per team, with the likely culprit games
  7  rating components               GmPerf, Sched, OTAdj, Total (MAE, bias, worst teams)
  8  ranked / minimum games          official "did not meet minimum" vs our 3-GP rule
  9  penalties                       official penalty column vs our overrides + forfeit suggestions
  10 regional order                  exact rank, top 2, top 16 (regional field), top 20 (published)
  11 dashboard snapshot              the snapshot the live site showed for the same games
  12 Oklahoma State                  full line, official vs ours

Writes data/validation/<season>_<label>.json and data/validation/<season>_<label>.md, prints a summary.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import statistics
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scripts")]

from engine.allgames import MEN_SEASONS  # noqa: E402
from engine.engine import (MIN_GP_RANKED, forfeit_penalties, games_from_feed, load_feed, rank,  # noqa: E402
                           solve)
from official import parse_raw_pdf  # noqa: E402

REGIONS = ("Northeast", "Southeast", "Central", "West")
FOCUS = "Oklahoma State University"
FULL_ROW = re.compile(r"^(?:(\d+)\s+)?(.+?)\s+(\d+)\s+(\d+)\s+(-?\d*\.\d+)\s+(-?\d*\.\d+)\s+(?:(\d*\.?\d+)\s+)?(-?\d*\.\d+)\s*$")


# ----------------------------------------------------------------------------- parsing
def clean_name(s: str) -> tuple[str, str]:
    s = (s or "").strip()
    flags = "".join(c for c in s if c in "*#")
    return re.sub(r"[\s*#]+$", "", re.sub(r"\s*[*#]+\s*", " ", s)).strip(), flags


def parse_full(path: str) -> dict[str, dict]:
    """Full-rankings file (PDF or XLSX) -> {official name: {region, rank, W, L, AWP, Raw, Penalty, Final, flags, below_min}}."""
    rows: dict[str, dict] = {}
    if path.lower().endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        for ws in wb.worksheets:
            sheet_note = None if ws.title.lower().startswith("sheet") else ws.title
            region, below = None, None
            for r in ws.iter_rows(values_only=True):
                cells = [c for c in r]
                txt = " ".join(str(c) for c in cells if c is not None)
                m = re.search(r"(NORTHEAST|SOUTHEAST|CENTRAL|WEST) REGION", txt.upper())
                if m:
                    region, below = m.group(1).title(), None
                    continue
                low = txt.lower()
                if "minimum" in low:
                    below = "min_games"
                    continue
                if "good acha standing" in low:
                    below = "not_good_standing"
                    continue
                if "=" in txt and not any(isinstance(c, (int, float)) for c in cells):
                    continue
                # locate the team-name cell: first string cell that is not a header
                idx = next((i for i, c in enumerate(cells) if isinstance(c, str) and c.strip() and c.strip() not in ("Rank", "Team")), None)
                if idx is None:
                    continue
                nums = cells[idx + 1: idx + 7]
                if len(nums) < 6 or not isinstance(nums[0], (int, float)) or not isinstance(nums[1], (int, float)):
                    continue
                name, flags = clean_name(cells[idx])
                rk = cells[idx - 1] if idx > 0 and isinstance(cells[idx - 1], (int, float)) else None
                w, l, awp, raw, pen, fin = nums[:6]
                rows[name] = dict(region=region, rank=int(rk) if rk else None, W=int(w), L=int(l),
                                  AWP=float(awp or 0), Raw=float(raw), Penalty=float(pen or 0), Final=float(fin),
                                  flags=flags, below_min=below, sheet=sheet_note)
        return rows
    import pypdf
    text = "\n".join(p.extract_text() for p in pypdf.PdfReader(path).pages)
    region, below = None, None
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^(NORTHEAST|SOUTHEAST|CENTRAL|WEST) REGION", s.upper())
        if m:
            region, below = m.group(1).title(), None
            continue
        if "minimum" in s.lower():
            below = "min_games"
            continue
        if "good acha standing" in s.lower():
            below = "not_good_standing"
            continue
        m = FULL_ROW.match(s)
        if not m or s.startswith("Rank "):
            continue
        rk, name, w, l, awp, raw, pen, fin = m.groups()
        name, flags = clean_name(name)
        rows[name] = dict(region=region, rank=int(rk) if rk else None, W=int(w), L=int(l), AWP=float(awp),
                          Raw=float(raw), Penalty=float(pen or 0), Final=float(fin), flags=flags, below_min=below, sheet=None)
    return rows


# ----------------------------------------------------------------------------- strict name matching
EXPAND = {"univ": ["university"], "wisc": ["wisconsin"], "mass": ["massachusetts"], "nc": ["north", "carolina"],
          "unc": ["north", "carolina"], "csu": ["california", "state"], "cal": ["california"], "st": ["saint"],
          "ucla": ["california", "los", "angeles"], "uc": ["california"], "tech": ["technological"], "mt": ["mount"],
          "msu": ["metropolitan", "state"], "suny": ["suny"], "u": []}
STOP = {"university", "of", "the", "college", "at", "and", "in"}


def core(name: str) -> list[str]:
    s = name.lower().replace("&;", "&").replace("&amp;", "&").replace("&", " and ").replace("'", "").replace("\u2019", "").replace(".", " ")
    s = re.sub(r"\(.*?\)", " ", s).replace("-", " ").replace(",", " ")
    out = []
    for t in s.split():
        out += EXPAND.get(t, [t])
    return [t for t in out if t not in STOP]


def tok_eq(a: str, b: str) -> bool:
    import difflib
    return a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a))) or \
        (min(len(a), len(b)) >= 5 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.8)


def covered(xs: list[str], ys: list[str]) -> bool:
    return all(any(tok_eq(x, y) for y in ys) for x in xs)


ALIASES = {"Dakota College": "Dakota College-Bottineau"}  # official -> feed, where word rules can't decide


def match_strict(official: list[str], feed: list[str]) -> dict[str, str]:
    """One-to-one official -> feed mapping. Exact core-token match beats a fuzzy token bijection, which beats a
    unique subset ('Dakota College' -> 'Dakota College-Bottineau'). Distinctive words must agree, so
    'Saint Cloud State' never maps to 'Colorado State'."""
    fc = {f: core(f) for f in feed}
    cands = [(4, o, ALIASES[o]) for o in official if ALIASES.get(o) in feed]
    for o in official:
        oc = core(o)
        if not oc:
            continue
        subs = []
        for f, c in fc.items():
            if sorted(oc) == sorted(c):
                cands.append((3, o, f))
            elif covered(oc, c) and covered(c, oc):
                cands.append((2, o, f))
            elif covered(oc, c) or covered(c, oc):
                subs.append(f)
        if len(subs) == 1:
            cands.append((1, o, subs[0]))
    cands.sort(key=lambda x: -x[0])
    out, used = {}, set()
    for sc, o, f in cands:
        if o in out or f in used:
            continue
        # a subset/fuzzy match is ambiguous if the same official name has another candidate at that score
        if sc < 3 and sum(1 for s2, o2, f2 in cands if o2 == o and s2 == sc and f2 not in used) > 1:
            continue
        out[o] = f
        used.add(f)
    return out


# ----------------------------------------------------------------------------- helpers
class Report:
    def __init__(self):
        self.checks: list[dict] = []

    def add(self, n: int, title: str, status: str, summary: str, details=None):
        self.checks.append(dict(n=n, title=title, status=status, summary=summary, details=details or []))
        print(f"[{status:4}] {n:2d} {title}: {summary}", flush=True)


def jload(rel, default=None):
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        return default
    with open(p) as f:
        return json.load(f)


def find_file(season: str, label: str, kind: str) -> str | None:
    pats = {"raw": [f"{label}_raw.pdf"], "full": [f"{label}_full.xlsx", f"{label}_full.pdf"]}[kind]
    for p in pats:
        f = os.path.join(ROOT, "data/official", season, p)
        if os.path.exists(f):
            return f
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=list(MEN_SEASONS)[-1])
    ap.add_argument("--label", required=True, help="R1, R2, ... (as on achahockey.org/m2-rankings)")
    ap.add_argument("--thru", required=True, help="games-through date printed on the release (YYYY-MM-DD)")
    ap.add_argument("--raw")
    ap.add_argument("--full")
    ap.add_argument("--no-fetch", action="store_true", help="do not re-download the current season's feed")
    a = ap.parse_args()
    season, label, thru = a.season, a.label, a.thru
    rep = Report()

    # ---------------- 1. parse official files
    raw_path = a.raw or find_file(season, label, "raw")
    full_path = a.full or find_file(season, label, "full")
    off_raw = parse_raw_pdf(raw_path) if raw_path else {}
    off_full = parse_full(full_path) if full_path else {}
    st = "PASS" if off_raw and off_full else ("WARN" if off_raw or off_full else "FAIL")
    rep.add(1, "Files parsed", st, f"raw PDF {len(off_raw)} teams ({os.path.basename(raw_path or '-')}), "
            f"full rankings {len(off_full)} teams ({os.path.basename(full_path or '-')})")
    if st == "FAIL":
        return finish(rep, season, label, thru, {})

    # ---------------- our side: engine at the same cutoff
    sid = MEN_SEASONS[season]
    feed_path = os.path.join(ROOT, f"data/feeds/season{sid}.json")
    if season == list(MEN_SEASONS)[-1] and not a.no_fetch:
        from engine.allgames import load_feed as refresh_feed
        refresh_feed(season, refresh=True)
    feed = load_feed(feed_path)
    ov = jload(f"data/overrides_{season}.json", {}) or {}
    games, forfeits = games_from_feed(feed, thru, ov)
    teams = solve(games)
    pen = forfeit_penalties(forfeits)
    pen.update(ov.get("penalties", {}))
    reg_file = (jload(f"data/regions_{season}.json", {}) or {}).get("regions")

    # ---------------- 3. names
    feed_teams = sorted(set(teams) | set(reg_file or {}))
    nm_raw = match_strict(list(off_raw), feed_teams)
    nm_full = match_strict(list(off_full), feed_teams)
    # one key space: full-file names, with raw-file rows re-keyed onto them via the shared feed team
    full_by_feed = {f: o for o, f in nm_full.items()}
    off_raw = {full_by_feed.get(nm_raw.get(o), o): r for o, r in off_raw.items()}
    nm = {**{o: nm_raw[k] for k in nm_raw for o in [full_by_feed.get(nm_raw[k], k)]}, **nm_full}
    unmatched_raw = [o for o in off_raw if o not in nm]
    unmatched_full = [o for o, x in off_full.items() if o not in nm and not x.get("sheet")]
    gone = [o for o, x in off_full.items() if o not in nm and x.get("sheet")]
    n_off = len(set(off_raw) | set(off_full))
    rep.add(3, "Team names", "PASS" if not unmatched_raw and not unmatched_full else "FAIL",
            f"{len(nm)}/{n_off} official names mapped one-to-one"
            + (f"; unmatched {sorted(set(unmatched_raw + unmatched_full))}" if unmatched_raw or unmatched_full else "")
            + (f"; not in the feed (ACHA 'no longer in M2' sheet): {len(gone)}" if gone else ""),
            [dict(official=o, feed=nm.get(o)) for o in sorted(nm) if nm.get(o) != o] +
            [dict(official=o, feed="UNMATCHED") for o in sorted(set(unmatched_raw + unmatched_full))])
    inv = {f: o for o, f in nm.items()}

    regions = dict(reg_file) if reg_file else {}
    off_region = {nm[o]: (off_full.get(o) or off_raw.get(o) or {}).get("region") for o in nm}
    if not regions:  # past seasons: no region file, use ACHA's
        regions = {t: r for t, r in off_region.items() if r}
    ranked = rank(teams, regions, pen, set(ov.get("not_good_standing", [])))
    ours = {r.team: r for lst in ranked.values() for r in lst}

    # ---------------- 2. formula unchanged
    det, bad = [], 0
    for o, x in off_full.items():
        w, l = x["W"], x["L"]
        awp = 0.8 * w / (w + l) if w + l else 0.0
        fin = x["Raw"] + x["AWP"] - x["Penalty"]
        if abs(awp - x["AWP"]) > 0.0015 or abs(fin - x["Final"]) > 0.0025:
            bad += 1
            det.append(dict(team=o, AWP=x["AWP"], AWP_expected=round(awp, 4), Final=x["Final"], Final_expected=round(fin, 4)))
        r = off_raw.get(o)
        if r and abs(r["Total"] - x["Raw"]) > 0.006:
            bad += 1
            det.append(dict(team=o, issue="raw-data Total differs from full-rankings Raw", Total=r["Total"], Raw=x["Raw"]))
    ot_bad = []
    for o, r in off_raw.items():
        gp = r["W"] + r["L"] + r["T"]
        if gp and abs(0.5 * r["OTL"] / gp - r["OTAdj"]) > 0.0051:
            ot_bad.append(dict(team=o, OTL=r["OTL"], GP=gp, OTAdj=r["OTAdj"], expected=round(0.5 * r["OTL"] / gp, 3)))
    gpw = [(r["W"] + r["L"] + r["T"], r["Total"] - r["OTAdj"]) for r in off_raw.values() if r["W"] + r["L"] + r["T"]]
    pin = sum(g * v for g, v in gpw) / sum(g for g, _ in gpw) if gpw else float("nan")
    st = "PASS" if not bad and not ot_bad and abs(pin - 7.0) < 0.03 else ("WARN" if bad + len(ot_bad) <= 3 and abs(pin - 7.0) < 0.06 else "FAIL")
    rep.add(2, "Formula unchanged", st, f"{bad} AWP/Final/Raw inconsistencies, {len(ot_bad)} OTAdj != 0.5*OTL/GP, "
            f"GP-weighted mean of Total-OTAdj = {pin:.3f} (expect 7.000)", det + ot_bad)

    # ---------------- 4. team set
    official_feed = {nm[o] for o in nm}
    ours_not_official = sorted(t for t in teams if t not in official_feed)
    official_not_ours = sorted(nm[o] for o in nm if nm[o] not in teams)
    no_longer = sorted(o for o, x in off_full.items() if x.get("sheet"))
    rep.add(4, "Team set", "PASS" if not ours_not_official and not official_not_ours else "WARN",
            f"we rate {len(teams)}, ACHA lists {len(official_feed)}; ours-only {len(ours_not_official)}, ACHA-only {len(official_not_ours)}"
            + (f"; ACHA 'no longer in M2' sheet: {no_longer}" if no_longer else ""),
            [dict(ours_only=t, gp=teams[t].gp) for t in ours_not_official] + [dict(acha_only=t) for t in official_not_ours])

    # ---------------- 5. regions
    rdiff = [dict(team=t, official=r, ours=regions.get(t)) for t, r in off_region.items() if r and reg_file and regions.get(t) != r]
    rep.add(5, "Regions", "PASS" if not rdiff else "FAIL", f"{len(rdiff)} region assignments differ" if reg_file else
            "no region file for this season (ACHA regions used)", rdiff)

    # ---------------- 6. records
    rec_diff = []
    for o, r in off_raw.items():
        t = nm.get(o)
        if not t:
            continue
        m = teams.get(t)
        mine = (m.w, m.l, m.t, m.otw, m.otl) if m else (0, 0, 0, 0, 0)
        theirs = (r["W"], r["L"], r["T"], r["OTW"], r["OTL"])
        if mine != theirs:
            gd = sum(theirs[:3]) - sum(mine[:3])
            kind = ("OT flags only" if mine[:3] == theirs[:3] else "ACHA has fewer games" if gd < 0 else
                    "ACHA has more games" if gd > 0 else "different results")
            rec_diff.append(dict(team=t, official="-".join(map(str, theirs)), ours="-".join(map(str, mine)), gp_diff=gd, kind=kind))
    kind_of = {d["team"]: d["kind"] for d in rec_diff}
    suspects = []
    for g in games:
        kh, ka = kind_of.get(g.home), kind_of.get(g.away)
        if kh == ka == "ACHA has fewer games":
            suspects.append(dict(id=g.id, date=g.date, game=f"{g.away} {g.ag} at {g.home} {g.hg}", note="in the feed, probably not yet reported to ACHA"))
        elif kh == ka == "different results":
            suspects.append(dict(id=g.id, date=g.date, game=f"{g.away} {g.ag} at {g.home} {g.hg}", note="both teams' results differ: check the score"))
    counted_ids = {g.id for g in games}
    from engine.engine import m2_name
    for x in feed:
        h, aw = m2_name(x["home_team_name"]), m2_name(x["visiting_team_name"])
        if (x["id"] not in counted_ids and x["date_played"] <= thru and h and aw
                and kind_of.get(h) == kind_of.get(aw) == "ACHA has more games"):
            suspects.append(dict(id=x["id"], date=x["date_played"], game=f"{aw} {x['visiting_goal_count']} at {h} {x['home_goal_count']}",
                                 note=f"ACHA seems to count it; feed status '{x['game_status']}'"))
    n_rec = len([o for o in off_raw if nm.get(o)])
    wlt_ok = n_rec - sum(d["kind"] != "OT flags only" for d in rec_diff)
    kinds = defaultdict(int)
    for d in rec_diff:
        kinds[d["kind"]] += 1
    rate = wlt_ok / n_rec if n_rec else 0
    st = "PASS" if rate >= 0.6 else ("WARN" if rate >= 0.45 else "FAIL")
    rep.add(6, "Records (W-L-T)", st, f"{wlt_ok}/{n_rec} teams ({rate:.0%}) have the same W-L-T "
            f"(2025-26 baseline: 63% at R1, 71% at R5, 72% at the final); exact incl. OT flags {n_rec - len(rec_diff)}. "
            + ", ".join(f"{k}: {v}" for k, v in sorted(kinds.items())) + f"; {len(suspects)} specific suspect games",
            sorted(rec_diff, key=lambda d: d["kind"]) + suspects)

    # ---------------- 7. rating components
    comp_rows, rec_ok = [], {d["team"] for d in rec_diff}
    for o, r in off_raw.items():
        t = nm.get(o)
        if not t or t not in teams:
            continue
        m = teams[t]
        comp_rows.append(dict(team=t, records_match=t not in rec_ok,
                              d_gmperf=round(r["GmPerf"] - m.gmperf, 3), d_sched=round(r["Sched"] - m.sched, 3),
                              d_otadj=round(r["OTAdj"] - m.otadj, 3), d_total=round(r["Total"] - m.raw, 3)))
    errs = [c["d_total"] for c in comp_rows]
    errs_ok = [c["d_total"] for c in comp_rows if c["records_match"]]
    mae = statistics.mean(abs(e) for e in errs) if errs else float("nan")
    mae_ok = statistics.mean(abs(e) for e in errs_ok) if errs_ok else float("nan")
    worst = sorted(comp_rows, key=lambda c: -abs(c["d_total"]))[:12]
    st = "PASS" if mae_ok <= 0.12 and mae <= 0.25 else ("WARN" if mae <= 0.4 else "FAIL")
    rep.add(7, "Rating components", st, f"Total MAE {mae:.3f} (bias {statistics.mean(errs):+.3f}, max {max(abs(e) for e in errs):.2f}); "
            f"teams with matching records MAE {mae_ok:.3f}. 2025-26 backtest: 0.10-0.24", worst)

    if not off_full:
        for n, t in ((8, "Ranked vs unranked"), (9, "Penalties"), (10, "Regional order"), (11, "Dashboard snapshot")):
            rep.add(n, t, "SKIP", "no full-rankings file in this release")
    if off_full:
        # ---------------- 8. ranked / unranked (minimum games, good standing)
        mm, ngs_new = [], []
        ngs_ours = set(ov.get("not_good_standing", []))
        for o, x in off_full.items():
            t = nm.get(o)
            if not t or x.get("sheet"):
                continue
            off_ranked = x["rank"] is not None and not x["below_min"]
            our_ranked = t in ours and ours[t].status == "ranked"
            if x["below_min"] == "not_good_standing" and t not in ngs_ours:
                ngs_new.append(dict(team=t, official="not in good ACHA standing", action="add to overrides not_good_standing",
                                    official_flags=x["flags"]))
            if off_ranked != our_ranked:
                mm.append(dict(team=t, official="ranked" if off_ranked else (x["below_min"] or "unranked"),
                               ours=ours[t].status if t in ours else "absent", official_W_L=f"{x['W']}-{x['L']}",
                               our_gp=teams[t].gp if t in teams else 0))
        min_gp_unranked = sorted({int(d["official_W_L"].split("-")[0]) + int(d["official_W_L"].split("-")[1])
                                  for d in mm if d["official"] == "min_games"})
        min_gp_ranked = min((x["W"] + x["L"] for x in off_full.values() if x["rank"]), default=None)
        rep.add(8, "Ranked vs unranked", "PASS" if not mm else "WARN",
                f"{len(mm)} teams ranked by one side only; {len(ngs_new)} teams ACHA lists as not in good standing that the "
                f"dashboard still ranks. Our minimum is {MIN_GP_RANKED} GP; ACHA's fewest W+L among ranked teams: {min_gp_ranked}"
                + (f"; below-minimum teams had W+L {min_gp_unranked}" if min_gp_unranked else ""), ngs_new + mm)

        # ---------------- 9. penalties
        pd = []
        for o, x in off_full.items():
            t = nm.get(o)
            if not t:
                continue
            mine = pen.get(t, 0.0)
            if abs(mine - x["Penalty"]) > 1e-6:
                pd.append(dict(team=t, official=x["Penalty"], ours=mine, ours_source="override" if t in ov.get("penalties", {}) else "forfeit suggestion"))
        rep.add(9, "Penalties", "PASS" if not pd else "WARN", f"{len(pd)} penalty differences" +
                (" (add confirmed ones to overrides 'penalties')" if pd else ""), pd)

        # ---------------- 10. regional order
        order_rows, tot = [], defaultdict(int)
        for reg in REGIONS:
            off_list = sorted([(x["rank"], nm[o]) for o, x in off_full.items() if x["region"] == reg and x["rank"] and nm.get(o)
                               and not x.get("sheet")])
            our_list = [r.team for r in ranked.get(reg, []) if r.status == "ranked"]
            o_ord = [t for _, t in off_list]
            for k in (2, 16, 20):
                kk = min(k, len(o_ord))
                tot[f"set{k}"] += len(set(o_ord[:kk]) & set(our_list[:kk]))
                tot[f"n{k}"] += kk
            kk = min(20, len(o_ord))
            tot["exact20"] += sum(i < len(our_list) and o_ord[i] == our_list[i] for i in range(kk))
            for i, t in enumerate(o_ord[:20]):
                ours_rk = our_list.index(t) + 1 if t in our_list else None
                if ours_rk != i + 1:
                    order_rows.append(dict(region=reg, team=t, official=i + 1, ours=ours_rk))
        st = "PASS" if tot["set2"] == tot["n2"] and tot["set16"] >= 0.95 * tot["n16"] else (
            "WARN" if tot["set2"] >= tot["n2"] - 1 and tot["set16"] >= 0.9 * tot["n16"] else "FAIL")
        rep.add(10, "Regional order", st, f"top 2 {tot['set2']}/{tot['n2']}, top 16 set {tot['set16']}/{tot['n16']}, "
                f"top 20 set {tot['set20']}/{tot['n20']}, exact position (top 20) {tot['exact20']}/{tot['n20']}", order_rows)

        # ---------------- 11. what the dashboard showed for these games
        dash = None
        if season == list(MEN_SEASONS)[-1]:
            cands = []
            for p in sorted(glob.glob(os.path.join(ROOT, "data/snapshots/20*.json"))):
                s = jload(os.path.relpath(p, ROOT))
                if s and s.get("last_game_date") and s["last_game_date"] <= thru:
                    cands.append((p, s))
            if cands:
                p, s = cands[-1]
                dd = []
                for row in s["teams"]:
                    o = inv.get(row["team"])
                    x = off_full.get(o) if o else None
                    if not x or row.get("rank") is None and x["rank"] is None:
                        continue
                    if row.get("rank") != x["rank"] or abs((row.get("final") or 0) - x["Final"]) > 0.25:
                        dd.append(dict(team=row["team"], region=row.get("region"), dashboard_rank=row.get("rank"), official_rank=x["rank"],
                                       dashboard_final=round(row.get("final") or 0, 3), official_final=x["Final"]))
                dd.sort(key=lambda d: (d["official_rank"] or 99))
                n_r = sum(1 for x in off_full.values() if x["rank"])
                same = n_r - sum(1 for d in dd if d["official_rank"])
                dash = dict(snapshot=os.path.basename(p), generated_at=s.get("generated_at"), last_game=s.get("last_game_date"))
                rep.add(11, "Dashboard snapshot", "PASS" if len(dd) <= 0.1 * n_r else ("WARN" if len(dd) <= 0.25 * n_r else "FAIL"),
                        f"{os.path.basename(p)} (games through {s.get('last_game_date')}): {same}/{n_r} ranked teams same rank "
                        f"and Final within 0.25", dd)
            else:
                rep.add(11, "Dashboard snapshot", "WARN", "no saved snapshot covers exactly this period; engine recomputed instead")

    # ---------------- 12. Oklahoma State
    o = inv.get(FOCUS)
    if o and FOCUS in teams:
        r, x, m = off_raw.get(o, {}), off_full.get(o, {}), ours[FOCUS]
        line = dict(official=dict(rank=x.get("rank"), W=r.get("W"), L=r.get("L"), OTL=r.get("OTL"), GmPerf=r.get("GmPerf"),
                                  Sched=r.get("Sched"), Total=r.get("Total"), AWP=x.get("AWP"), Penalty=x.get("Penalty"), Final=x.get("Final")),
                    ours=dict(rank=m.rank, W=m.w, L=m.l, OTL=m.otl, GmPerf=round(m.gmperf, 2), Sched=round(m.sched, 2),
                              Total=round(m.raw, 3), AWP=round(m.awp, 3), Penalty=m.penalty, Final=round(m.final, 3)))
        ok = line["official"]["rank"] == line["ours"]["rank"] and (r.get("W"), r.get("L")) == (m.w, m.l)
        rep.add(12, "Oklahoma State", "PASS" if ok and abs((x.get("Final") or 0) - m.final) < 0.2 else "WARN",
                f"official #{x.get('rank')} West, Final {x.get('Final')} | ours #{m.rank}, Final {m.final:.3f}", [line])
    else:
        rep.add(12, "Oklahoma State", "WARN", "OSU not found in the official files")

    return finish(rep, season, label, thru, dict(raw=raw_path and os.path.relpath(raw_path, ROOT),
                                                  full=full_path and os.path.relpath(full_path, ROOT),
                                                  games_counted=len(games), dashboard=dash))


def _minus(d: str, days: int) -> str:
    import datetime as dt
    return (dt.date.fromisoformat(d) - dt.timedelta(days=days)).isoformat()


def finish(rep: Report, season: str, label: str, thru: str, meta: dict):
    import datetime as dt
    rep.checks.sort(key=lambda c: c["n"])
    worst = "FAIL" if any(c["status"] == "FAIL" for c in rep.checks) else ("WARN" if any(c["status"] == "WARN" for c in rep.checks) else "PASS")
    out = dict(season=season, label=label, thru=thru, validated_at=dt.datetime.now().isoformat(timespec="minutes"),
               overall=worst, **meta, checks=rep.checks)
    d = os.path.join(ROOT, "data/validation")
    os.makedirs(d, exist_ok=True)
    base = os.path.join(d, f"{season}_{label}")
    with open(base + ".json", "w") as f:
        json.dump(out, f, indent=1, default=str)
    md = [f"# Validation: official ACHA M2 {label} ({season}, games through {thru})", "",
          f"Validated {out['validated_at']}. Overall: **{worst}**", "", "| # | Check | Status | Result |", "|---|---|---|---|"]
    md += [f"| {c['n']} | {c['title']} | {c['status']} | {c['summary']} |" for c in rep.checks]
    for c in rep.checks:
        if c["details"]:
            md += ["", f"## {c['n']}. {c['title']}", ""]
            keys = list(dict.fromkeys(k for row in c["details"][:40] for k in row))
            md += ["| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
            md += ["| " + " | ".join(str(row.get(k, "")) for k in keys) + " |" for row in c["details"][:40]]
            if len(c["details"]) > 40:
                md.append(f"\n…{len(c['details']) - 40} more rows in the JSON file.")
    with open(base + ".md", "w") as f:
        f.write("\n".join(md) + "\n")
    print(f"\nOVERALL {worst} -> {os.path.relpath(base, ROOT)}.md / .json")
    return out


if __name__ == "__main__":
    main()
