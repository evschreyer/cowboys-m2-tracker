# OSU M2 Rankings Dashboard: Plan (rev 2, 2026-10-03)

## Decisions
- **Audience:** OSU staff and players. A private shared web page (claude.ai artifact) shared by link. Built around the Cowboys.
- **Data:** HockeyTech feed plus a manual override file (score fixes, missing games, forfeits, penalties, good standing, regions, league-playoff OT ties).
- **Rules source:** 2026-27 ACHA Manual, Part Five (see FINDINGS §2b).

## What changed after reading the manual
1. **Postseason format is new for 2026-27.** There are 16 teams per region. The cut lines are now #2 (Nationals auto-bid), #4 (Regionals Day-1 bye) and #16 (Regionals field, minus league autobids that displace the lowest seeds).
2. **Eligibility risk:** a team needs 16 M2 plus 18 ACHA games by 2/14/27. OSU has exactly 16 M2 games scheduled, so one cancellation puts the postseason at risk. This becomes a top-of-page tracker.
3. **Calendar:** ranking periods end 11/8, 12/13, 1/17 and 2/14 (final). Scores are due Monday and rankings post Thursday. Our snapshots mirror these "through Sunday" cutoffs.
4. **Forfeits:** excluded from the math (validated). The forfeiting team gets a 0.25 penalty per game per player, auto-suggested from the feed.
5. **League playoff OT = tie.** This is an override rule for conference tournaments that fall before 2/14.
6. **Each OSU M2 game is about 6% of the rating** (16 games). About half the schedule (M1 opponents: Oregon, Midland, Ohio, Illinois, Minot, UNLV, OU) does not count. The dashboard must make the counted vs. not-counted distinction obvious.
7. **The field changed:** 8 new or returning M2 teams need a region. Default to the league-mates' majority region, then confirm.

## Architecture
- **Engine:** the reference is `engine/engine.py` (backtests and the refresh job). The JS port `engine/engine.js` runs What-if and Projections in the browser and is verified in the browser pane against the Python output (no Node on this machine). Spec: SRS with GD cap 7, start 7.0, run to convergence, M2-vs-M2 only, forfeits excluded, then OTAdj, AWP, penalty, ranked by region.
- **Refresh job** (scheduled, e.g. nightly plus Monday night): pulls the feed, applies overrides, computes, stores a dated snapshot, republishes. Snapshots give week-over-week movement and validation history.
- **Page:** renders the latest snapshot. What-if and projections run the engine in the browser.
- **Spike in Phase 1:** test whether the published page can call HockeyTech directly. If it can, add "live now" mode. If not, the snapshot design already covers it.

## Tabs
Core tabs (user request 2026-10-03): one tab for each of the 4 features: **OSU Breakdown, Regional Rankings, What-if Simulator, Projections**. Supporting tabs: West Race, Validation, Methodology.

1. **Cowboys / OSU Breakdown (home):** West rank, Final rating and its parts (GmPerf, Sched, OTAdj, AWP); distance to #2, #4 and #16; eligibility tracker (M2 games played/scheduled vs 16, ACHA total vs 18); game-by-game impact on the rating; counted (M2) vs not counted (M1) games; next ranking cutoff countdown.
2. **Regional rankings:** all 4 regions, top 20 plus the rest. Movement vs the previous snapshot. Flags for good standing and minimum games.
3. **West race:** OSU's direct competitors (Weber St, Montana St, Utah St, Providence, Utah...): their remaining M2 schedule and head-to-head with OSU.
4. **What-if:** set scores for any upcoming M2 games and re-rank instantly. "What do we need vs X to stay top 2?"
5. **Projections:** predicted margin per game (rating difference) and Monte Carlo odds of finishing top 2, top 4 and top 16 in the West on 2/14.
6. **Validation:** our numbers vs each official ACHA release (R1 about 11/12).
7. **Methodology and data notes:** formula, rules, overrides log.

## Build phases
1. **Engine and backtest:** port to JS, backtest on all 9 rankings from 2025-26 and on 2024-25. Do the live-fetch spike.
2. **Data layer:** feed loader, cutoffs, forfeit handling, override file, 2026-27 region map (user confirms the new teams).
3. **v1 page:** Cowboys, Regional and Methodology tabs. Publish privately.
4. **West race, What-if and Projections tabs.**
5. **Refresh schedule and snapshot history.**
6. **Validate vs official R1** (period ends 11/8). Tune and record any differences in the override file.

## Progress
- [x] Phase 1: engine (`engine/engine.py`, `engine/engine.js`), backtest (`scripts/backtest.py`), parity test.
- [x] Phase 2 (core): feed loader and snapshot (`scripts/build_snapshot.py`), regions (`data/regions_2026-27.json`), overrides (`data/overrides_2026-27.json`), season config.
- [x] Phase 3/4: dashboard v1 published (https://claude.ai/artifact/PADoAjHhr6HqMsPgmgMDRz) with tabs OSU Breakdown, Regional Rankings, What-If, Projections, Method.
- [x] Phase 5: automated refresh. Moved to GitHub on 2026-10-03: repo evschreyer/cowboys-m2-tracker (public), site https://evschreyer.github.io/cowboys-m2-tracker/, refreshed by Actions (nightly, Monday deadline, every 30 min on Fri/Sat nights). The Mac scheduled tasks are disabled.
- [ ] Validate projection calibration on 2025-26.
- [ ] Phase 6: compare against official R1 (period ends 11/8/26).
- Not possible: live fetch from the page. Artifact CSP blocks requests to other hosts, so the snapshot plus republish design is required.
