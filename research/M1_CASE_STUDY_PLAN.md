# OSU vs ACHA M1: Case Study and Dashboard Plan (draft, 2026-11-07)

## Trigger
Nov 6, 2026: **Oklahoma State (M2) 3, Ohio (M1) 2**, in regulation at Ohio. Ohio is the defending M1 national champion and **#3 in ACHA M1 Computer Ranking #5** (thru 11/1/26). Game 2 is Nov 7, 5:00 pm EST.

## What we know about ACHA M1 (Manual Part Four, Art. IV-V, plus the ACHA site)
- Coaches poll until Nov 1, then **one national computer ranking**. It is the average of two USHSHO-style rankings: **A** = rating with GD capped at 7, **B** = GD capped at 1. The average is of the **rank positions**, and ties go to the team ranked higher in B. There are no regions.
- Only **M1 vs M1** games count. **OT and SO results count as ties.** There is a home-game imbalance penalty (Art. IV §1F; the size of the penalty is set at the national meeting).
- The ranking is published as a Top 25 plus a full A/B/average PDF, every Wednesday. Next: Nov 11. The final is released 3/24/27.
- **Nationals:** 24 teams, single elimination, March 11-23, 2027 in St. Louis. Seeds 1-4 and 5-8 get byes. Seeding follows the computer average. League auto-bids come from 9 leagues, and the host gets an auto-bid.
- Ranking #5 top 5: 1 Drury, 2 Minot State, 3 Ohio, 4 UNLV, 5 Niagara (M1). There are 81 ranked teams.
- Data: the same HockeyTech feed (`MD1` prefix; `M1` before 2023-24). Game summaries give shots, scoring by period, PP/PK and goalie saves. The standings feed gives PP%, PK% and OT/SO W-L.

## Early findings
1. **Base rate.** In 2021-22 through 2026-27, M2 teams went **3-23 (11.5%)** against teams that finished in M1's top 5:
   - Mary over Minot State (2022)
   - FGCU over Liberty (2024)
   - OSU over Ohio (2026)

   By M1 tier, M2 win rates were: top 6-10, 8.3%; 11-25, 24%; 26+, 39%. (Tiers use our season-end replication of the M1 computer ranking.)
2. **Team-adjusted odds.** A single rating built on all ACHA men's games, with 52 M1-M2 games linking the divisions before 11/6, rated OSU 14.47 and Ohio 15.52 going in. That predicts Ohio by 1.3 goals with the home edge. **P(OSU win) ≈ 32%.** The win was a big upset by label but only a moderate one given OSU's strength. That gap is the story.
3. **Neither ranking counts it.** The M1 ranking ignores cross-division games, and the M2 ranking ignores them too. Ohio's M1 ranking can't fall and OSU's M2 rating can't rise from this result.
4. **Where OSU fits among M1 teams.**
   - All-division rating: OSU **#3 of 82 M1 teams** (behind Ohio and Drury). On that scale the average M1 team is 3.1 goals better than the average M2 team.
   - Adding OSU to the M1 computer ranking using its 6 M1 games (6-0): **#1** in both A and B. This is a 6-game sample, so it's overstated.
5. **Game stats.** Ohio outshot OSU 36-30 (16-11 in the 1st, even after that). OSU's goalie saved 34 of 36 (.944). PP: Ohio 1/2, OSU 0/2. OSU won the 2nd period 2-0.
6. **Replication gap.** Our copy of the M1 method lands on exactly the official rank for only 10-13 of 80 teams (mean miss about 3 places), with 74 of 80 agreeing on top-25 membership. ACHA's M1 game set differs from the feed, possibly through the home-game penalty or data differences. This needs reconciling before we present "phantom M1" ranks as ACHA-equivalent.

## Proposed methods

### A. Case study: "How big was this upset?"
1. **Base rate.** M2 win % against M1 by M1 tier, at the time of the game rather than season-end. Rebuild the M1 ranking as of each game date for 2021-22 to 2026-27, with bootstrap confidence intervals.
2. **Pre-game probability.** Run the all-division rating as of game day, calibrated on all M1-M2 games from past seasons: predicted vs actual, Brier score and calibration curve. Report P(OSU win), the surprise in bits (−log2 p), and where this result falls among all M2-over-M1 wins.
3. **Context adjustments.** Road game, opponent's home record, rest days, and game 1 vs game 2 of the weekend.
4. **Performance vs result.** Shots, period flow, special teams and goaltending vs each team's season averages: did OSU outplay Ohio, or out-goaltend them?
5. **Historical leaderboard.** Every M2 win over a top-10 M1 team since 2021-22, ranked by pre-game probability. Where does OSU's rank?
6. **Weekend view.** Update all of the above after game 2: series result and combined probability.

### B. Dashboard: new "vs M1" tab
1. **Where OSU would rank in M1**, two ways, with confidence intervals:
   - All-division rating
   - OSU added to the M1 computer ranking
2. **OSU vs M1 game log.** Each opponent's current M1 rank, score, shots, PP, goalie save %, pre-game win probability and surprise.
3. **Stat comparison.** OSU vs the M1 average, the M1 top 25 and the M1 top 5: GF/GA per game, shots for/against, PP% and PK%. M1-only and all-games versions.
4. **Division gap tracker.** M1 average minus M2 average on the shared scale by season, and M2's record vs M1 by tier.
5. **Combined top 25 across M1 and M2** (unofficial), using the all-division rating.

### C. Engineering
- Generalize the feed loader to all divisions: handle both prefixes, and count cross-division ties.
- Build an M1 replication module and validate it against all 2025-26 M1 computer releases (download from achahockey.org/m1-2025-2026-rankings).
- Load game summaries (shots, PP, goalies) for every M1-M2 game and every OSU game. This is about 500 requests per season, cached.
- Calibration notebook/script, with results written into FINDINGS.
- Snapshot gains a `m1` block. Add the "vs M1" tab.

## Open questions for the user
See chat.
