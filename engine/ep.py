"""Minimal EliteProspects API client (internal research only).

* Reads EP_API_KEY from the project's .env (gitignored). The key is never printed or logged.
* Every network call is appended to data/cache/ep/calls.log (timestamp + path, no key) so the monthly
  budget (Explorer tier: 1,000 calls/month) can be tracked: `python3 -m engine.ep` prints usage.
* Responses are cached in data/cache/ep/ (gitignored). EP license section 3.2: in-season data may be cached
  for at most 24 hours and historical data for at most 30 days. `get(..., max_age_h=...)` enforces that,
  and `purge()` deletes anything older than 30 days.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data/cache/ep")
LOG = os.path.join(CACHE, "calls.log")
BASE = "https://api.eliteprospects.com/v1"
MONTHLY_BUDGET = 1000


def _key() -> str:
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path):
            if line.startswith("EP_API_KEY="):
                k = line.split("=", 1)[1].strip().strip('"').strip("'")
                if k:
                    return k
    k = os.environ.get("EP_API_KEY", "")
    if not k:
        raise SystemExit("EP_API_KEY missing: paste it into .env")
    return k


def calls_this_month() -> int:
    if not os.path.exists(LOG):
        return 0
    m = dt.date.today().strftime("%Y-%m")
    return sum(1 for line in open(LOG) if line.startswith(m))


def get(path: str, params: dict | None = None, max_age_h: float = 24 * 30, reserve: int = 50):
    """GET BASE+path with params. Cached; refuses to run if the month's budget minus `reserve` is spent."""
    params = {k: v for k, v in (params or {}).items() if v is not None}
    q = urllib.parse.urlencode(params, doseq=True)
    url = f"{BASE}{path}" + (f"?{q}" if q else "")
    h = hashlib.sha1(url.encode()).hexdigest()[:20]
    cpath = os.path.join(CACHE, "resp", f"{h}.json")
    if os.path.exists(cpath) and time.time() - os.path.getmtime(cpath) < max_age_h * 3600:
        with open(cpath) as f:
            return json.load(f)["body"]
    if calls_this_month() >= MONTHLY_BUDGET - reserve:
        raise RuntimeError(f"EP budget guard: {calls_this_month()} calls used this month")
    req = urllib.request.Request(url, headers={"X-Api-Key": _key(), "User-Agent": "osu-m2-rankings/1.0",
                                               "Accept": "application/json"})
    os.makedirs(os.path.dirname(cpath), exist_ok=True)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json.loads(r.read().decode())
            status = 200
            break
        except urllib.error.HTTPError as e:
            status = e.code
            body = {"_error": e.code, "_body": e.read().decode()[:500]}
            if e.code == 429 and attempt < 2:
                time.sleep(7 * (attempt + 1))
                continue
            break
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise
            time.sleep(10 * (attempt + 1))
    with open(LOG, "a") as f:
        f.write(f"{dt.datetime.now().isoformat(timespec='seconds')} {status} {path}?{q}\n")
    if status in (200, 400, 403, 404):  # cache refusals too, so a blocked endpoint is never re-called
        with open(cpath, "w") as f:
            json.dump({"url": url, "fetched": time.time(), "body": body}, f)
    time.sleep(6.5)  # Explorer tier: 10 requests/minute
    return body


def purge(days: int = 30) -> int:
    d = os.path.join(CACHE, "resp")
    n = 0
    if os.path.isdir(d):
        for fn in os.listdir(d):
            p = os.path.join(d, fn)
            if time.time() - os.path.getmtime(p) > days * 86400:
                os.remove(p)
                n += 1
    return n


if __name__ == "__main__":
    print(f"EP calls this month: {calls_this_month()} / {MONTHLY_BUDGET}; purged {purge()} stale cache files")
