# How significant is OSU's 2026-27 season? Exploration notes (2026-11-07)

Scripts: `research/explore_significance.py` and the ad-hoc analyses recorded below. Data covers every ACHA men's game since 2021-22. Strengths come from the calibrated cross-division model (`engine/xdiv.py`, FITTED). "M2 team-seasons" means 1,062 seasons with 5 or more games. Anchored seasons are 2022-23 onward. OSU has played 15 games (14-1).

## Evidence ladder (the core of the significance case)
Each row compares the likelihood of OSU's 15 game margins (capped at 7, opponent strengths fixed) under OSU's estimated strength (7.12 ± 0.73) with the likelihood under a benchmark strength.

| Claim: OSU is better than… | Benchmark strength | z | One-sided p | Likelihood ratio | Read |
|---|---|---|---|---|---|
| An average M1 team | 3.71 | 4.40 | ~5e-6 | 426,000× | Overwhelming |
| M1's #25 team | 4.95 | 2.80 | ~0.003 | 406× | Strong |
| A typical season-best M2 team (2022-23 to 2025-26 average) | 6.09 | 1.33 | ~0.09 | 6.5× | Moderate |
| M1's #10 team | 6.70 | 0.54 | ~0.29 | 1.7× | Inconclusive |
| The best previous M2 team-season (Lindenwood 2025-26) | 7.00 | 0.15 | ~0.44 | 1.1× | Inconclusive |

Defensible headline: **OSU is playing at M1 level, comfortably above M1's top 25.** "Best M2 team ever" is not yet provable.

## Comparisons with history
| Measure | OSU 2026-27 | Rank among M2 team-seasons | Notes |
|---|---|---|---|
| Schedule-adjusted strength (to date) | 7.12 | **#1 of 1,062** (all ACHA: #8 of 2,144) | Lindenwood 2025-26 finished at 7.00 |
| Strength after 15 games (same-point comparison) | 7.12 | #2 of 798 | Lindenwood 2025-26 was 7.51 at that point |
| Strength above the M2 average | +6.58 | #2 | Lindenwood 2025-26 is #1 at +6.79 |
| Beating pre-game expectations (z) | 2.67 | **#2** | #1 is OSU 2025-26 (3.42). All-ACHA #5 |
| Record vs combined M1+M2 top 25 at the time | 6-0 | **Best win %** (5+ games) | The only other M2 team unbeaten vs ranked teams: Montana State 2023-24 (4-0) |
| Two-year rise vs the M2 average | +8.81 (2024-25 → 2026-27) | **#1 of 433** | Next: Nebraska +5.73. OSU also has #5 (+4.56, 2023-24 → 2025-26) |
| Raw win %, goal margin, goals against | 93%, +5.1, 2.2 | #9, #4, #47 | Raw stats don't separate OSU; schedule does |

## Probability that OSU is stronger than past champions (end of regular season, both uncertainties)
| Champion | Chance OSU is stronger |
|---|---|
| Mary 2022 | 96% |
| UMass 2023 | ~100% |
| Indiana 2024 | ~100% |
| Lindenwood 2025 | 75% |
| FGCU 2026 | 79% |
| Lindenwood 2025-26 (not champion) | 55% |

Probability that OSU is the strongest M2 team-season of the anchored era: **48%**.

## Against M1
- 7-0 vs M1. The chance of that run for OSU itself was 0.54% (1 in 187); for a typical season-best M2 team it would be 1 in 249.
- At the time of the series, the model rated Ohio **#1 across all of M1 and M2 combined**.

## Program trajectory (strength relative to the M2 average)
| Season | OSU vs M2 average |
|---|---|
| 2022-23 | -1.45 |
| 2023-24 | +0.51 |
| 2024-25 | -2.23 |
| 2025-26 | +5.06 (national runner-up) |
| 2026-27 | +6.58 (to date) |

## Cautions
- **Multiple comparisons.** With 1,062 team-seasons, about 4 would reach z ≥ 2.67 on beating expectations by chance. OSU holding both #1 and #2 is the more meaningful pattern than either season alone.
- **Partial season.** At the same 15-game point, Lindenwood 2025-26 rated higher. Re-check at season's end.
- **2021-22 has no prior season,** so it is excluded wherever ratings are compared across seasons.

## Not yet explored
- Goalie and shot metrics league-wide. This needs box scores for all ~4,000 games per season (about an hour of downloads per season).
- Consistency: the distribution of OSU's game-level performance.
- Head-to-head with Lindenwood (OSU 2-0 this season) and Penn State or other national contenders.
- Opponent-adjusted special teams.
