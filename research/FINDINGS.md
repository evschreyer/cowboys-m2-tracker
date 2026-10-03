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
