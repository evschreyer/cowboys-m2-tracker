"""Roster construction step 4: EliteProspects pilot (free Explorer tier).

The free tier only exposes /players (identity: name, date of birth, nationality, position). Career
endpoints (/players/{id}/stats, rosters, search) return 403, so this pilot measures COVERAGE: what share
of ACHA players have an EP profile we can match with confidence. That is the go/no-go input for a paid tier.

Match rules (ACHA roster vs EP /players?q=<last name>):
  confirmed  last name + exact date of birth (+ first name or first initial)
  probable   last name + first name + same birth year (ACHA birthdate missing or off by a typo)
  ambiguous  2+ candidates pass "probable"
  none       no candidate
Output: research/out/ep_pilot.json (gitignored; internal).
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from engine import ep  # noqa: E402

TEAMS = ["M2 Oklahoma State University", "M2 Lindenwood University", "M2 Liberty University",
         "M2 Florida Gulf Coast University", "M1 Ohio University", "M1 Midland University"]
NICK = {"will": "william", "bill": "william", "matt": "matthew", "mike": "michael", "nick": "nicholas", "alex": "alexander",
        "chris": "christopher", "jake": "jacob", "joe": "joseph", "tom": "thomas", "dan": "daniel", "danny": "daniel",
        "sam": "samuel", "ben": "benjamin", "zach": "zachary", "zack": "zachary", "tony": "anthony", "andy": "andrew",
        "drew": "andrew", "rob": "robert", "bob": "robert", "jon": "jonathan", "nate": "nathan", "josh": "joshua",
        "max": "maxwell", "maxx": "maxwell", "cam": "cameron", "ty": "tyler", "jimmy": "james", "jim": "james"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower())


def first_ok(a: str, b: str) -> bool:
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    a2, b2 = NICK.get(a, a), NICK.get(b, b)
    return a == b or a2 == b2 or a.startswith(b) or b.startswith(a) or a2.startswith(b2) or b2.startswith(a2)


def main():
    db = json.load(open(os.path.join(ROOT, "data/cache/rosters/roster_db.json")))
    P = db["players"]
    cur = db["seasons"][-1]
    rows = [r for r in db["profile"] if r["season"] == cur and r["team"] in TEAMS and (r["on_roster"] or r["gp"] > 0)]
    print(f"{len(rows)} players on {len(TEAMS)} teams; EP calls used before: {ep.calls_this_month()}", flush=True)
    out = []
    for i, r in enumerate(rows):
        b = P[r["pid"]]
        last = b.get("last_name") or b["name"].split()[-1]
        first = b.get("first_name") or b["name"].split()[0]
        # strip suffixes so "Smith Jr." searches as Smith
        q = re.sub(r"\b(jr|sr|ii|iii|iv)\.?$", "", last.strip(), flags=re.I).strip()
        res = ep.get("/players", {"q": q, "limit": 1000})
        if "_error" in res:
            print("EP error", res, flush=True)
            break
        cands = [c for c in res.get("data", []) if norm(c.get("lastName")) == norm(q) or norm(q) in norm(c.get("lastName"))]
        bd = (b.get("birthdate") or "")[:10]
        # free tier caps q-search at 30 results (and q also hits first names), so a common last name can hide
        # the right player: fall back to a full-name query when no date-of-birth match is in the first page
        if not any(bd and c.get("dateOfBirth") == bd for c in cands) and res.get("_meta", {}).get("totalRecords", 0) >= 30 or not cands:
            res2 = ep.get("/players", {"q": f"{first} {q}", "limit": 1000})
            if "_error" not in res2:
                seen = {c["id"] for c in cands}
                cands += [c for c in res2.get("data", []) if c["id"] not in seen and
                          (norm(c.get("lastName")) == norm(q) or norm(q) in norm(c.get("lastName")))]
        conf = [c for c in cands if bd and c.get("dateOfBirth") == bd and (first_ok(first, c.get("firstName")) or norm(first)[:1] == norm(c.get("firstName"))[:1])]
        prob = [c for c in cands if first_ok(first, c.get("firstName")) and bd and (c.get("dateOfBirth") or "")[:4] == bd[:4]]
        prob_nobd = [c for c in cands if first_ok(first, c.get("firstName")) and not bd]
        if len(conf) == 1:
            status, m = "confirmed", conf[0]
        elif len(conf) > 1:
            status, m = "ambiguous", None
        elif len(prob) == 1:
            status, m = "probable", prob[0]
        elif len(prob) > 1 or len(prob_nobd) > 1:
            status, m = "ambiguous", None
        elif len(prob_nobd) == 1:
            status, m = "probable", prob_nobd[0]
        else:
            status, m = "none", None
        out.append(dict(team=r["team"], div=r["div"], name=b["name"], pid=r["pid"], gp=r["gp"], pos=r["pos"],
                        birthdate=bd, acha_seasons_before=r["acha_seasons_before"], status=status,
                        n_lastname_hits=len(cands), capped=res.get("_meta", {}).get("totalRecords", 0) >= 30, ep_id=m and m["id"], ep_dob=m and m.get("dateOfBirth"),
                        ep_nat=m and (m.get("nationality") or {}).get("slug")))
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(rows)} {Counter(o['status'] for o in out)}", flush=True)
    os.makedirs(os.path.join(ROOT, "research/out"), exist_ok=True)
    with open(os.path.join(ROOT, "research/out/ep_pilot.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("\nby team:")
    for t in TEAMS:
        tt = [o for o in out if o["team"] == t]
        c = Counter(o["status"] for o in tt)
        played = [o for o in tt if o["gp"] > 0]
        print(f"  {t:36s} n={len(tt):2d} confirmed {c['confirmed']:2d} probable {c['probable']:2d} ambiguous {c['ambiguous']} none {c['none']:2d}"
              f" | matched among players who played: {sum(o['status'] in ('confirmed', 'probable') for o in played)}/{len(played)}")
    c = Counter(o["status"] for o in out)
    print("total", dict(c), f"EP calls used this month: {ep.calls_this_month()}")


if __name__ == "__main__":
    main()
