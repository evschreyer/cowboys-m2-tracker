# Roster construction exploration: plan (draft 2026-11-07)

**Question:** how did each ACHA team build its roster, and does pedigree (the level players came from) explain on-ice strength? The output is a weighted **Roster Pedigree Index (RPI)** per team. Pedigree is then compared with the calibrated strength model (`engine/xdiv.py`) to see who outperforms their roster.

## 1. What data exists (checked 2026-11-07)

### ACHA HockeyTech feed (free; already in use)
- **Rosters**
  - Every team and season back to 2022-23 (`view=roster&team_id&season_id`).
  - Each player has name, birthdate (~90% filled), hometown, height and weight, position and shoots/catches.
  - **No previous team field.**
- **Player careers** (`view=player&category=seasonstats`)
  - Every ACHA season, team and stat line for a player.
  - **This gives ACHA-internal pedigree for free:** M1 → M2 moves, transfers between M2 teams, and years of ACHA experience.
  - Example: Kubrytskyi played three seasons at M1 Grand Canyon before OSU, and Nieuwendyk came from M2 FAU.
- **Scale this season**
  - 81 M1 teams, 195 M2 teams and 163 M3 teams.
  - About 29 players per roster: roughly 8,100 players across M1 and M2, and about 12,800 with M3.

### EliteProspects (the only broad source of junior, prep, NCAA and CHL history)
- **Coverage:** EP has ACHA team pages, including M2 (for example Keene State lists 27 players). Profiles carry each player's full career by league and season.
- **Website scraping is prohibited** by the terms (§3.1(d)). We use the API or manual lookup only.
- **API plans:**

  | Plan | Price | Calls per month | Notes |
  |---|---|---|---|
  | Explorer | Free | 1,000 | Evaluation and internal testing only. No public display. |
  | Personal | "$0 base" plus paid modules | 5,000 | |
  | Commercial | $990/yr | 50,000 | |
  | Enterprise | $5,000/yr | 250,000 | |

  - Current-season data is included; deeper history is a one-time purchase.
  - Junior and youth leagues are an **add-on**.
- **License limits:**
  - Data may be cached for **24 hours** in season and 30 days for historical data.
  - No building a standalone dataset that could be bulk exported.
  - Attribution ("Data provided by EliteProspects") is required.
  - No consumer use.
  - **Consequence:** player-level EP data **cannot be committed to the public GitHub repo.** Team-level aggregates on the public dashboard are probably fine on a paid tier; confirm with api@eliteprospects.com.
- **Matching:** name plus birthdate (ACHA has a birthdate for about 90% of players, and EP stores date of birth). Hometown breaks remaining ties.

### Other sources (secondary)
- **Junior leagues on HockeyTech** (USHL, NAHL, possibly others):
  - These would allow free matching by name and birthdate.
  - Each league issues its own feed key, and we would need its permission. **Not pursued unless a league publishes or grants access.**
- **ACHA team websites:** some list a "previous team" per player. The format varies, so this is useful only for spot checks.
- **NCAA school rosters** (Sidearm sites): would help confirm former NCAA players.

### Manual rules that shape the pipeline (ACHA Manual 2026-27)
- **Pros:** players from pro leagues (NHL, AHL, ECHL, SPHL, FHL, LNAH, top European leagues) are **ineligible**. The top of the pedigree scale is therefore NCAA D1 or CHL.
- **CHL (major junior):** players became **eligible on Aug 1, 2025.** This is a new pipeline worth tracking as a trend story for 2025-26 vs 2026-27.
- **NCAA:** former NCAA players are eligible but use a year of ACHA eligibility per NCAA year, within a five-year limit.
- **M1 games:** a player with 6+ M1 games in a year cannot return to M2 that year, so M1 experience on an M2 roster is mostly from prior seasons.

## 2. Scoring model

### Player pedigree
- Each player gets a **level score** from the top level of their pre-ACHA career (or their M1 history).
- That score is adjusted by **games at that level**: a 3-game call-up should count much less than 50 games.

Draft tier ladder (expert prior, to be calibrated):

| Tier | Points | Levels |
|---|---|---|
| 1 | 10 | NCAA D1, CHL (OHL/WHL/QMJHL), USHL |
| 2 | 8 | NAHL, BCHL, NCAA D3, U Sports, ACHA M1 (2+ seasons) |
| 3 | 6 | Canadian Junior A (OJHL, AJHL, SJHL, MJHL, CCHL, NOJHL, MHL, SIJHL, LHJAAAQ), USPHL NCDC, ACHA M1 (1 season) |
| 4 | 4 | Tier III / Junior B (NA3HL, USPHL Premier, EHL, GOJHL, KIJHL, PJHL, VIJHL), top 18U AAA (HPHL, T1EHL, NAPHL, CSSHL U18) |
| 5 | 2 | High school (including MN/MI/MA varsity), prep, 18U AA, ACHA M2/M3 only |
| 6 | 0 | No record found (kept separate from "low pedigree") |

### Team index
- **RPI:** pedigree weighted by usage (games played this season; goalies weighted by their share of goalie games).
- **Top-of-lineup RPI:** the top 12 forwards, 6 defensemen and 1 goalie by games played, because depth players matter less.
- **Composition mix:** the share of the roster from each tier, shown as stacked bars per team.

### Calibration (how the weights stop being guesses)
- **Team level:** regress xdiv strength on each team's tier shares, across M1 and M2 and several seasons. The coefficients are "goals per game added per roster spot from tier X". They replace or refine the points in the table above.
- **Player level:** compare ACHA points per game against prior level (like an "NHLe" league-translation factor), controlling for team strength.
- **Validation:** check that the RPI predicts next season's strength out of sample, and report how much variance it explains.

## 3. Findings this could produce
- **Pedigree vs results:** a scatter of RPI against strength. The residual measures "outperformed its roster" (coaching and development).
  - **OSU angle:** if OSU's RPI is below the M1 teams it is beating, the significance case gets stronger.
- **Recruiting pipelines:** which feeder leagues supply each contender, and OSU vs Lindenwood, FGCU and Liberty.
- **M1 → M2 flow:** M2 contenders built on M1 transfers; free from the ACHA feed alone.
- **The CHL effect:** how many CHL players entered ACHA after Aug 2025, and where they went.
- **Age and experience:** roster age from birthdates, ACHA years, and grad students (free from the ACHA feed).
- **Geography:** hometowns from hockey heartlands vs non-traditional markets (free).

## 4. Phases
0. **Free layer (no EP needed).** Pull every M1 and M2 roster and career since 2022-23 from the ACHA feed. Build the ACHA-internal pedigree (M1 experience, transfers), age, size and hometown, and run a first test of whether this partial pedigree predicts strength.
1. **EP pilot.** Use the free Explorer key (the user signs up; Claude never handles the key in chat; it goes into a local env variable). Match OSU plus about 10 contenders (about 300 players, well within 1,000 calls) to measure match rate and coverage. Internal only.
2. **Decision point.** Based on pilot coverage, choose a paid tier and the team scope.
3. **Full build.** Pipeline `scripts/build_rosters.py` → `data/rosters_*.json`. Player-level EP data stays local, gitignored and refreshed within the cache limits. Only team aggregates are published.
4. **Calibrate and report.** New Case Studies report `roster-construction.html`, as a snapshot plus a yearly refresh. Recruiting changes slowly, so nightly CI is not needed.

## 5. Decisions (user, 2026-11-07)
- **Source:** build the free ACHA layer first, then run an EP pilot on the free Explorer key (OSU plus about 10 contenders) before any spending.
- **Scope:** M1 + M2, about 276 teams and 8,100 players this season, with history back to 2022-23.
- **Weights:** both. The user signs off on an expert tier ladder, then the data refines it.
- **Audience:** internal first. Player-level data stays local and gitignored. Only team-level indexes may go public later, if licensing allows.

## Results so far (2026-11-08)

### Step 1: ACHA layer (`scripts/fetch_rosters.py` → `data/cache/rosters/roster_db.json`)
- **Size:** 2021-22 to 2026-27, 32,295 players and 44,335 M1/M2 player-seasons. Games played come from the league-wide stats feed (step 2 is folded in).
- **Field coverage:** birthdate 79% in 2021-22, rising to 97% in 2026-27.
- **Hometowns:** teams often enter their campus city when a hometown is unknown (OSU: 7 players listed as "Stillwater, OK", including 3 Norwegians). A city shared by 4+ players on one roster is treated as a placeholder and falls back to the country field.
- **2026-27 first look:**
  - 39% of M2 players who have played are new to ACHA.
  - 3% of M2 players have prior M1 experience.
  - Most M1 veterans on an M2 roster: Lehigh 14, George Mason 11, Buffalo 11.
  - OSU has 12 players new to ACHA. Kubrytskyi is OSU's only M1 veteran (39 games at Grand Canyon).

### Step 4: EP pilot (`research/ep_pilot.py`, `engine/ep.py`; 260 of 1,000 free calls used in Nov 2026)
- **Free tier access:** only `/players` (name, date of birth, nationality, position) is allowed. **Career stats, rosters, team or league player-stats, and search all return 403.** The free tier cannot provide pre-college history.
- **Search quirk:** a name search returns at most 30 results and also matches first names. A last-name query is therefore followed by a full-name query.
- **Coverage on 6 teams** (OSU, Lindenwood, Liberty, FGCU, M1 Ohio, M1 Midland; 174 players):
  - **96% matched** (158 on exact date of birth, 9 probable).
  - Weighted by games played: **98%**.
  - Players new to ACHA: 95%.
  - OSU: 28 of 29 matched (all but Corbin Roach).
- **Conclusion:** EP has profiles for nearly every ACHA M1 and M2 player. The only blocker is paid access to career data.
- **Paid setup estimate** (developer.eliteprospects.com pricing, Nov 2026):

  | Item | Cost |
  |---|---|
  | Personal plan | $0 base, 5,000 calls/month |
  | North America region | $480/yr |
  | 5-year history (one-time) | $500 |
  | 20-year history (one-time) | $1,500 |
  | Youth/junior add-on (if NAHL/OJHL count as youth) | ~+$144 |
  | **Total** | **~$1,100–2,100** |

  - 5-year history covers 2022-23 onward. That misses junior seasons from 2019-22 for the oldest current players, so 20-year history is safer.
  - Confirm with api@eliteprospects.com whether ACHA, NAHL and Junior A are in the North America region.
- **Cache compliance:** EP responses live in `data/cache/ep/` (gitignored). `python3 -m engine.ep` purges anything older than 30 days.

## 6. Steps
1. **ACHA roster layer.** `scripts/fetch_rosters.py` pulls every M1 and M2 roster for 2022-23 to 2026-27 plus player careers into `data/cache/rosters/` (gitignored). It produces each player's ACHA history (M1 seasons, transfers, years in ACHA), age, size and hometown.
2. **Usage weights.** Games played per player from ACHA season stats; goalie games from goalie stats.
3. **Free-layer analysis.** Does ACHA-internal pedigree (M1 experience, age, experience) predict xdiv strength? What is OSU's profile against contenders and M1 opponents?
4. **EP pilot.**
   - The user creates the Explorer key and stores it locally in `.env` (`EP_API_KEY`, gitignored). Claude never sees or handles it in chat.
   - Match by name and birthdate. Report the match rate, unmatched players and league coverage.
5. **Tier ladder sign-off.** The user edits the ladder; leagues found in the pilot get mapped to tiers.
6. **Decide on paid EP and full scope.** Then the full build, calibration and the internal report `roster-construction.html`.
