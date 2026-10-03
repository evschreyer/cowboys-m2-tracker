# Cowboys M2 Tracker

Reconstructs ACHA Men's Division 2 regional rankings from live HockeyTech scores.

Dashboard: GitHub Pages (see repo About). Refreshed by `.github/workflows/refresh.yml`.

## Refresh the data
Automatic: GitHub Actions (`.github/workflows/refresh.yml`) runs nightly (about 3:30 AM Central), Monday night after ACHA's reporting deadline, and every 30 minutes on Friday/Saturday game nights. It commits the new snapshot and redeploys GitHub Pages only when the data changed. To run it by hand: Actions, then "Refresh rankings", then "Run workflow".

Manual:
```
python3 scripts/build_snapshot.py      # fetch feed, compute, write data/snapshots/<date>.json + latest.json
python3 scripts/build_site.py          # assemble _site/ (what GitHub Pages serves)
python3 scripts/backtest.py            # check the engine against ACHA's official 2025-26 rankings
```

## Corrections
Edit `data/overrides_2026-27.json` (score fixes, missing games, penalties, good standing, league-playoff OT ties) and rebuild.

## Layout
- `engine/` ranking engine (Python reference + browser port, kept identical)
- `scripts/` snapshot builder, backtest, official-file parser
- `data/` feeds, official ACHA files, regions, overrides, snapshots
- `research/` findings and plan
