# ACHA M2 Ranking: Research Findings (Phase 0)

_Compiled 2026-10-03_

## 1. The formula (verified against the official 2025-26 files)

ACHA publishes two files for every M2 ranking at https://www.achahockey.org/m2-rankings:
- **Raw Data PDF**: the computer rating per team (`GmPerf`, `Sched`, `OTAdj`, `Total`)
- **Full Rankings XLSX/PDF**: adds win % and penalties. The live Excel formulas are in the file.

```
GD_game    = clamp(goals_for - goals_against, -7, +7)         # OT and SO games count normally
GmPerf     = mean(GD_game) over M2-vs-M2 games
Sched      = mean(Total_opponent) over the same games          # recursive (SRS / least squares)
Total      = GmPerf + Sched          (iterated to convergence; starts every team at 7.0)
OTAdj      = 0.5 * OTL / GP          # added after convergence; it does NOT feed into opponents' Sched
RawRating  = Total + OTAdj
AWP        = (W / (W + L)) * 0.8
Final      = RawRating + AWP - Penalty
```
Teams are ranked by `Final` **within each region** (Northeast, Southeast, Central, West). OSU is in the West.

### Evidence
- The rating engine is the USHSHO.com program (same output format). ACHA has used USHSHO since 2013.
  Historically it averaged a "GD cap 7" ranking with a "GD cap 1" ranking. **For 2024-25 and 2025-26 only the cap-7 ranking is used, plus the AWP term.**
- `OTAdj = 0.5*OTL/GP` matches every row checked (e.g. BU 5 OTL/21 GP = 0.12; Utah St 4/37 = 0.05).
- The GP-weighted mean of (Total - OTAdj) is **7.000** for the final ranking and **7.008** for Ranking #1, which pins the start constant at 7.0.
- My rebuild from HockeyTech scores, compared with the official final (thru 2/8/26):
  - mean offset -0.006, mean abs error 0.10, 0.06 on teams whose W-L matches exactly
  - Regional top 12: same 12 teams in all 4 regions, and 10/12 exact positions in NE, Central and West
- Cap 6 is clearly worse, and so is treating OT/SO games as 0 or ±0.5. Cap 7 with full GD for OT/SO is the best fit.
- **Only M2-vs-M2 games count.** OSU 2025-26: official 18-1 excludes both M1 Oklahoma games. Ranking #1 (9-1) also matches the M2-only count.

## 2. Data source: HockeyTech LeagueStat (public feed used by achahockey.org)
```
https://lscluster.hockeytech.com/feed/index.php?feed=modulekit&view=schedule
    &season_id={73 = 2026-27 men, 60 = 2025-26 men}&key=e6867b36742a0c9d&client_code=acha&fmt=json&lang=en
```
- Each game has team names prefixed `MD1`/`MD2`/`MD3`, scores, `overtime`, `shootout` and `game_status` ("Final", "Final OT", "Final SO", "Home/Visiting Forfeit", "Postponed", and so on).
- The statviewfeed endpoint also supports JSONP, so a static web page can pull it live.
- 2026-27 so far: 194 M2 teams, 1,739 M2-vs-M2 games scheduled, 137 final.

## 2b. Rules from the 2026-27 ACHA Manual (Part Five = Men's Division 2)
Source: `ACHA_Manual_2026_27_Season-FINAL-8-10-2026-1.pdf`, Part Five Art. III-V, plus the OT document and the M2 Important Dates page.

| Topic | Rule | Model impact |
|---|---|---|
| Ranking basis (Art. IV §1B) | Computer ranking by region using strength of schedule, W-L %, and goal differential | Matches the reverse-engineered formula |
| Regions (§1A) | 4 geographic regions set by the M2 VP. Disputes go to the Commissioner | Region map comes from official files plus new-team assignments |
| Published depth (§1C) | Top 20 per region | Display 20+, flag 21+ as "unpublished" |
| Good standing (§1D) | Required to be ranked | Manual flag. Team stays in the math but is listed separately (seen in 2025-26 files) |
| Reporting (§1F, §3) | Home games reported by Monday 11:59pm. Rankings posted Thursday | Snapshot "through Sunday" and recompute Tuesday |
| Ranking cutoffs 2026-27 | End of R1 period 11/8. Last before break 12/13. First spring 1/17. **Final 2/14/27** | Calendar plus countdown |
| League playoff OT (§3C) | A league tournament game that goes to OT = **tie** for rankings | Override GD to 0 for these games |
| Regular-season OT/SO (Art. II §3N-P) | M2-vs-M2: 3v3 OT, then shootout (always a winner). Cross-division can tie | Shootout winner's score includes the SO goal (validated) |
| Penalties (§5) | Post-calculation, **0.25 per player per game** for ineligible-player forfeits or game forfeiture | Penalty column. Feed forfeits suggest a penalty, manual confirms |
| Forfeit games | Validated on 2025-26: forfeited games are **excluded** from the rating calc (143 vs 127 exact records) | Drop forfeit statuses from the math |
| Postseason eligibility (§2A) | **>= 16 M2 games and >= 18 ACHA games** by the final ranking period | **OSU has exactly 16 M2 games scheduled through 2/14. Zero margin** |
| Nationals auto-bid (Art. V §1A, §2E) | Top 2 per region go straight to Nationals | Cut line at #2 |
| Regionals (2026 format) | 16 teams/region: seeds 3-16 plus league autobids, which displace the lowest seeds. Day 1: 5v16, 6v15 ... 10v11. Day 2: #3/#4 enter vs the lowest re-seeded. Day 3: 2 winners advance | Cut lines at #4 (Day-1 bye) and #16 (in field) |
| Host bye (§2A/H) | The Nationals host team takes a top-2 bye in its region | 2027 Nationals in **St. Louis**, 3/11-16. Host team TBD (Central region likely) |
| Dates 2026-27 | West Regionals 2/18-20/27. Nationals 3/11-16/27 | |
| Nationals pools (§1C) | West 1 joins Pool D (with SE2, C3, NE4) | Info only |
| Ranking Committee (Part Three Art. III) | Decisions final, no appeal | Human discretion can override the math |

Context: OSU were the 2026 M2 national runner-up (lost 3-2 in OT to FGCU) and finished 2025-26 #1 in the West.

## 2c. 2026-27 field changes (HockeyTech plus ACHA M2 rosters page)
- New or returning M2 teams needing a region: Alvernia, Kutztown (ACCHL Delaware Valley), Calvin (GL6), Lewis & Clark CC, Mercyhurst, Wittenberg (Independent), LSU (SECHC), Saint Thomas University (ACCHL Palmetto, **not** Univ. of St. Thomas MN).
- Moved to M1: Farmingdale State, TCNJ. Gone from M2: Bemidji State, East Carolina.
- Default region assignment: the majority region of the team's league-mates from last season, then by geography. The user confirms.

## 3. Known gaps / open questions
1. **Data drift:** at season end, 47/190 teams had a W-L in HockeyTech that differed from ACHA's ranking data by 1-2 games, and a few games had different scores. For example, OSU's GmPerf is about 4 goals lower officially, probably in a Creighton game. ACHA likely compiles from reported scores at the cutoff, and some of today's differences are later corrections.
2. ~~Penalties~~ **Resolved:** 0.25 per player per game for ineligible-player forfeits or game forfeiture (Manual Part Five Art. IV §5).
3. **Minimum games to be ranked (display):** not in the manual. A team with 3 GP was ranked in R1 and teams with 1 GP were not. The probable rule is 3. This is separate from the 16/18 **postseason** minimum.
4. **Tiebreakers:** not in the manual. A 2024 ACHA article says close teams were separated by a "third" criterion, Strength of Schedule. The order will be Final Rating, then Raw Rating, then Sched.
5. **Flags:** `*` = not in good ACHA standing (listed separately), `#` = not eligible for postseason.
6. **Region assignment:** this is not in HockeyTech. It comes from the official files. The 2026-27 mapping needs to be built.
7. **Postseason (as of 2024):** the top 2 per region get auto-bids to Nationals, #3-10 go to Regionals, plus league autobids or wild cards. 2026-27 needs to be confirmed.
8. **Release cadence 2025-26:** R1 covered games thru 11/9, then weekly or biweekly, with the final thru about 2/8. 9 rankings in total.

## 4. Files
- `engine/engine.py` (reference) and `engine/engine.js` (browser): the ranking engine
- `scripts/official.py`: parser for the ACHA raw-data PDFs. `scripts/backtest.py`: backtest against all 2025-26 releases
- `data/official/`: the ACHA ranking files used for validation

## 5. Projection model (dashboard only, not part of the ACHA formula)
- Team strength is the average game score (capped GD − home edge + opponent strength). Last season's final ACHA rating, regressed (7 + 0.733 × (Total − mean)), counts as 3 extra games, or 1 game at 6.5 for teams new to M2.
- Calibrated on 2024-25 → 2025-26: rest-of-season RMSE at Oct 12 was 3.10 goals (3.75 using raw current ratings). At Nov 9 it was 2.89.
- Home edge 0.24 goals. Game-to-game SD 2.6. Strength SD = 2.6 / sqrt(GP + k).
- Simulation: each run draws every team's true strength, plays all remaining M2 games (including unreported past games), then reruns the full ACHA engine.
- Not yet validated: whether the probabilities are well calibrated, e.g. projecting from Oct 2025 and checking against the final 2025-26 results.

## 6. Engine status (2026-10-03)
- `engine/engine.py` and `engine/engine.js` agree to 0.0 on the 2025-26 season (`tests/parity.html`).
- `scripts/backtest.py` on all 9 official 2025-26 rankings: rating MAE 0.10-0.24. Top-2 per region correct in 8 of 9 rankings (6/8 in R2). Top-16 sets 97%+.
- OSU's official GmPerf is about 4 goals (total) lower than the feed from R1 onward. This is a single-game data difference, probably a Creighton game. It is not systematic: there is no correlation with blowout counts.

## 7. ACHA M1 computer ranking: reconstruction (M1 study step 2, 2026-11-07)
`engine/m1rank.py`, validated by `scripts/backtest_m1.py` against all 13 published M1 "Computer Poll Average" PDFs (2025-26 R5-R16 and 2026-27 R5).
- Method: M1 vs M1 games only. **Every OT/SO game is a tie.** Rating A has GD capped at 7 and rating B at 1, using the same recursive rating as M2. Published rank = order of the average of the A and B rank positions, with ties going to the better B rank.
- Accuracy across 1,053 team-weeks: top 10 identical in all 13 releases. Top 25 matched for 23-25 of 25. Rank exact 65%, within one place 90%, mean miss 0.15-0.89 places. 2026-27 R5: B exact 81/81, A 71/81, rank 71/81.
- Alternatives tested and rejected:
  - Only shootouts as ties: A 55%, B 24% exact.
  - No ties at all: A 52%, B 19%.
  - Ranking on ratings rounded to 2 decimals, with several tiebreakers: no better.
  - The home-game imbalance penalty (§1F): no correlation between schedule imbalance and our misses, so ACHA apparently doesn't apply it.
- The remaining 2025-26 misses are data drift. Today's feed includes score corrections and late additions made after each ranking was published. Every 2025-26 game was re-saved in a later bulk update, so the `last_modified` timestamps can't recover what ACHA saw.
- Name aliases for the M1 PDFs: Buffalo = University at Buffalo, Navy = United States Naval Academy (`scripts/official.py`).
- Guest ranking: `m1_games(games, extra=osu_games)` ranks a non-M1 team on its games vs M1 teams. As of Nov 7 (before game 2 at Ohio), OSU is 6-0 in 6 M1 games and comes out #1 of 82 in both A and B. That's a small sample, and an unbeaten record automatically tops B. Step 3 adds uncertainty.

## 8. Cross-division win-probability model (M1 study step 3, 2026-11-07)
`engine/xdiv.py` (FITTED params), `scripts/calibrate_xdiv.py`, results in `data/xdiv_model.json`.
- **Shared scale:** every ACHA men's team (M1/M2/M3) gets a goal-unit strength. It is the average of (capped GD − home edge + opponent strength), with last season's final strength (regressed 0.6 toward its division mean) counted as k = 2 extra games. Every prediction uses only games before that date. Cross-division games tie the divisions together.
- **Fitted:** home edge 0.33 goals (all-game residual MLE), game spread sigma 3.0 (chosen on cross-division log loss).
- **Division gap correction:** the higher division wins more often than the shared scale implies.
  - M1-side lean in M1-M2 games, actual minus predicted: 2022-23 +0.16, 2023-24 +0.16, 2024-25 +0.06, 2025-26 +0.04, 2026-27 +0.01. It is shrinking every year and is largest in Jan-Mar (+0.15).
  - Leave-one-season-out log loss improves from 0.531 to 0.515 with the correction.
  - Adopted recency-weighted values: **M1 +0.65 goals vs M2**, M1 +0.85 vs M3, M2 +0.50 vs M3.
- **Accuracy:**

  | Games | Log loss | Brier | Constant-rate baseline log loss |
  |---|---|---|---|
  | M1-M2, 2022-23..2025-26 (n=274) | 0.514 | 0.174 | |
  | M1-M2, 2026-27 holdout before Nov 6 (n=52) | 0.504 | 0.170 | |
  | All cross-division (n=825) | 0.534 | 0.181 | 0.656 |

  Calibration is good across deciles; for example, games predicted at 0.25 were won 20% of the time, 0.45 → 51%, 0.85 → 80%, 0.94 → 96%.
- **OSU at Ohio (Nov 6):** pre-game strengths OSU 6.76, Ohio 7.93. Predicted Ohio by 2.1 goals (strength gap, home edge and division correction). **P(OSU win) = 24%**, a surprise of 2.06 bits.
  - Superseded estimate: 32% from the earlier uncalibrated version, with no division correction.
  - Historical base rate for M2 vs a top-5 M1 team: 11.5%, i.e. 3.1 bits.
- **OSU's 6-0 vs M1 this season:** pre-game P(win) of 49%, 59%, 75%, 59%, 64% and 24%. The chance of sweeping all six was 2.0% (1 in 51).
- **OSU on the M1 scale after Nov 6** (M1 strengths + 0.65): about **#8 of 81 M1 teams**. That is more conservative than the uncalibrated estimate (#3) and the guest-ranking estimate (#1). On this scale OSU leads M2 by 1.5 goals over #2 Lindenwood.
- Game 2 at Ohio (Nov 7): pre-game P(OSU win) = 27%.

## 9. vs-M1 tab and data-quality fixes (M1 study step 5, 2026-11-07)
- After the Ohio sweep (3-2, 3-1), OSU is 7-0 vs M1 in 2026-27. The pre-game odds of a perfect run were 0.54% (1 in 187).
- On the shared scale OSU is #7 of 81 M1 teams. A Monte Carlo over strength uncertainty (sd = sigma/sqrt(GP + k)) gives an 80% range of #3-#14, a 95% range of #2-#18, and a 76% chance of being top 10.
- Gap between the average top-25 M1 and top-25 M2 team, including the +0.65 adjustment: 2022-23 1.27, 2023-24 1.26, 2024-25 1.89, 2025-26 2.39, 2026-27 2.22 goals. The all-teams gap is larger (2.4-3.5) partly because M2 keeps adding new, weaker teams. 2021-22 is excluded: it has no prior season, so every division started level and its gap reads too small (0.6 top-25).
- **Data guard added** (`engine.engine.plausible_final`): skip games dated after today and 0-0 "Unofficial Final" placeholders. Two JMU M2 games (Nov 14 and Jan 23) had been counted as 0-0 ties. Backtests are unchanged.
- **Save % fix:** team save % now uses goals against only from games where shots were tracked.

## 10. Ohio sweep deep dive (2026-11-07)
`scripts/build_deep_dive.py` writes `data/ohio_deep_dive.json`, shown on the page `ohio-analysis.html`. It is rebuilt by CI. All findings cover 2021-22 onward, with M1 rank at the time from our rebuild.
- **Series:** there were 118 multi-game M2-M1 series. Against a top-5 M1 team, 7 series, in which M2 teams won a game in 2 and swept 1 (OSU at Ohio).
  - All 4 M2 sweeps of a top-25 M1 team are OSU's: Oklahoma 2025, Oregon 2026, Midland 2026, Ohio 2026.
  - OSU's two Ohio wins are the only M2 road wins over a top-5 M1 team.
- **Odds at Ohio on Nov 6 (pre-weekend ratings):**

  | Team | One game | Sweep |
  |---|---|---|
  | OSU | 24.1% | 1 in 17 (1 in 15 when Saturday's odds reflect Friday's win) |
  | #2 M2 (Lindenwood) | 13.7% | 1 in 54 |
  | #10 M2 | 5.0% | 1 in 403 |
  | Average M2 | 0.3% | about 1 in 100,000 |

- **Wins above expectation vs M1:** OSU 2026-27 has +3.42 (7-0), first of 171 M2 team-seasons. OSU 2025-26 is second at +1.62 (3-0). Only OSU has gone unbeaten vs M1 with 3 or more wins, and it is 10-0 vs M1 across the two seasons.
- **Best M2 team each season, as an M1-equivalent rank** (anchored seasons):

  | Season | Best M2 team | M1-equivalent rank |
  |---|---|---|
  | 2022-23 | Mary | 8 |
  | 2023-24 | Lindenwood | 10 |
  | 2024-25 | Lindenwood | 8 |
  | 2025-26 | Lindenwood | 9 |
  | 2026-27 | OSU | **7** |

  OSU's 1.67-goal lead over M2's #2 is the widest in the data (previous high 1.01).
- **Trajectory:** OSU's M1-equivalent rank went #16 (Sep 13), #27 (Sep 27, after the loss at Jamestown), #8 (Nov 1), #9 (Nov 6), #7 (Nov 8).
- **Weekend decomposition, in goals:** model expected -4.0; shot volume +1.54; goaltending vs OSU's season save % +3.00; finishing vs Ohio's season save % +2.46; actual +3. Ohio's power play went 2/8 against 3.4 expected at its 43% rate. Kubrytskyi stopped 66/69 on the weekend and 129/136 (.949) in 5 starts vs M1. That is about 4.0 goals better than the average M1 save rate (.899) on Ohio's 70 shots.
- **Comebacks:** road teams down 1 after the first period won 56 of 225 box-scored games (24.9%).
- **Ohio:** first M2 opponent in the data (now 0-2). It went 28-3 at home from the start of 2025-26 until this weekend. OSU is the 3rd team to sweep a weekend at Ohio since 2022-23, after Liberty (Feb 2024) and Minot State (Feb 2025).
- **Counterfactual:** with OSU's games counted, ACHA's M1 formula puts OSU #1, Ohio #3→#4, Drury #1→#2 and Midland #10→#12.
- **Record chase:** the M2 record for wins over M1 in a season is 9 (Mary 2022-23). OSU has 7 with 9 M1 games left and an expected 5.67 more wins. P(new record) is 99.3%; P(16-0) is 0.9%.

## 11. Deep-dive extensions (2026-11-07)
`scripts/build_deep_dive_extra.py` writes `data/ohio_extra.json`. `scripts/simulate_title.py` writes `data/title_odds.json`. Box scores now include goal events and penalty shots (`engine/gamestats.compact`).
- **Game flow vs M1:** 46-10 over 7 games. By period 18-5, 16-4, **12-1 in thirds**. OSU scored first in 6 of 7 and led after two periods in all 7. Across all games OSU is 13-0 when scoring first. PP 6/21 and PK 24/30 vs M1, with 2 shorthanded goals for and 0 against. In game 2 Kubrytskyi stopped a penalty shot (Laker Aldridge, 3rd period 11:27).
- **Scoring vs M1:** Budd 6-5-11 (2 GWG), Roach 5-6-11, Milburn 3-7-10, Z. Green 1-8-9, Ziliotto 3-6-9 (2 GWG).
- **Neutral-ice odds vs M1 top 10:**

  | Range | Teams |
  |---|---|
  | Underdog | Drury 35%, Minot State 42%, Ohio 36% |
  | 47-55% | UNLV, Niagara, Jamestown, Liberty, Adrian, Maryville |
  | Favored | Midland 74% |

  OSU's rating is 7.12 ± 0.73. P(OSU truly stronger than Ohio) is 14%.
- **Title simulation** (3,000 runs; full remaining M2 schedule, official formula, 2026-27 Regionals bracket, Nationals pools from the manual; no auto-bids or host bye):

  | Stage | OSU probability |
  |---|---|
  | No. 1 in the West | 99.3% |
  | Reach the national semifinals | 71% |
  | Reach the final | 58% |
  | **Win the title** | **42.6%** |

  Next teams: Lindenwood 14.6%, Liberty 6.8%, Wisconsin 6.5%, FGCU 5.0%. History tempers this: only 2 of the last 5 champions were the top-rated M2 team at season's end. UMass 2023 was #11 and Indiana 2024 was #6.
- **Past champions' end-of-season strength:** Mary 5.58 (2021-22), UMass 3.57, Indiana 4.35, Lindenwood 6.53, FGCU 6.38. OSU is at 7.12 to date, above all of them.
- **Robustness**, 10 settings (M1 adjustment 0/0.65/1.0, k 1/2/5, b 0.4/0.6/0.8, spread 2.6/3.0/3.4, no home edge):
  - Holds in every setting: OSU is #1 in wins above expectation (+2.89 to +3.71), and it has the widest lead at the top of M2.
  - Holds in 9 of 10: OSU is the strongest M2 team on the M1 scale (fails at k=5).
  - Ranges: Friday 21-31%, sweep 1 in 9 to 1 in 21, M1-equivalent #3-#9, P(7-0) 0.27-1.63%.
- **Significance:** expected M2 sweeps across the 7 top-5 M1 series is 0.27. P(at least one) is 24%, and OSU's series alone makes up 25% of that expectation.
