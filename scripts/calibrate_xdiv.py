"""Calibrate and test the cross-division win-probability model (engine/xdiv.py).

Every prediction uses only games played before that game's date (plus last season's ratings).
Fit seasons: 2022-23 .. 2025-26 (2021-22 only seeds the priors). 2026-27 to date is a holdout.

Usage: python3 scripts/calibrate_xdiv.py [--quick]
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.xdiv import SEASONS, Params, build_chain  # noqa: E402

FIT = SEASONS[1:-1]
HOLDOUT = SEASONS[-1]


def outcome(g) -> float:
    return 1.0 if g.hg > g.ag else 0.0 if g.hg < g.ag else 0.5


def predictions(p: Params, seasons, only_cross=False, sample_every=1):
    chain = build_chain(p)
    rows = []
    for s in seasons:
        m = chain[s]
        gs = [g for g in m.games if (g.cross if only_cross else True)]
        for i, g in enumerate(gs):
            if not g.cross and i % sample_every:
                continue
            pr = m.predict(g)
            rows.append(dict(season=s, g=g, y=outcome(g), **pr))
    return rows


def scores(rows, sigma=None):
    eps = 1e-6
    ll, br, n = 0.0, 0.0, 0
    for r in rows:
        p = r["p_home"]
        br += (p - r["y"]) ** 2
        if r["y"] != 0.5:
            q = p if r["y"] == 1 else 1 - p
            ll -= math.log(max(q, eps)); n += 1
    return dict(n=len(rows), brier=br / len(rows), logloss=ll / max(n, 1))


def fit_sigma_home(rows):
    """MLE of home edge and sigma from margins (all games), given model strengths."""
    res = np.array([max(-7, min(7, r["g"].hg - r["g"].ag)) - (r["s_home"] - r["s_away"]) for r in rows if not r["g"].tie])
    return float(res.mean()), float(res.std())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    # 1) home edge + sigma from all-game residuals (prior-anchored strengths, default k/b)
    base = Params()
    rows_all = predictions(base, FIT, only_cross=False, sample_every=3)
    h, sd = fit_sigma_home(rows_all)
    print(f"all-game residuals (pre-game strengths): home edge {h:.3f}, sigma {sd:.3f}  (n={len(rows_all)})")

    # 2) grid over prior weight k and regression b, scored on cross-division games (fit seasons)
    grid_k = [1, 2, 3, 5, 8] if not args.quick else [2, 3, 5]
    grid_b = [0.5, 0.6, 0.7, 0.8, 0.9] if not args.quick else [0.6, 0.7, 0.8]
    results = []
    for k, b in itertools.product(grid_k, grid_b):
        p = Params(k=k, b=b, home_edge=round(h, 3), sigma=round(sd, 3))
        sc = scores(predictions(p, FIT, only_cross=True))
        results.append((sc["logloss"], sc["brier"], k, b))
        print(f"  k={k:<3} b={b:.1f}  cross log loss {sc['logloss']:.4f}  Brier {sc['brier']:.4f}")
    results.sort()
    _, _, k, b = results[0]
    best = Params(k=k, b=b, home_edge=round(h, 3), sigma=round(sd, 3))

    # 3) sigma for cross-division games specifically (does cross-division need extra spread?)
    best_s = None
    for s in [2.4, 2.6, 2.8, 3.0, 3.2, 3.5, 4.0]:
        p = Params(k=k, b=b, home_edge=best.home_edge, sigma=s)
        sc = scores(predictions(p, FIT, only_cross=True))
        print(f"  sigma={s:.1f}  cross log loss {sc['logloss']:.4f}  Brier {sc['brier']:.4f}")
        if best_s is None or sc["logloss"] < best_s[0]:
            best_s = (sc["logloss"], s)
    best.sigma = best_s[1]
    print(f"\nBEST: {best}")

    rows_fit = predictions(best, FIT, only_cross=True)
    rows_hold = predictions(best, [HOLDOUT], only_cross=True)
    rows_hold = [r for r in rows_hold if r["g"].date < "2026-11-06"]  # keep the Ohio game out of the holdout
    out = dict(params=best.__dict__, fit=scores(rows_fit), holdout=scores(rows_hold))

    # Baselines on the same cross-division games: constant rate by matchup type (from fit seasons)
    def key(r):
        g = r["g"]; return (int(g.home[1]), int(g.away[1]))
    rate = {}
    for r in rows_fit:
        rate.setdefault(key(r), []).append(r["y"])
    rate = {k_: float(np.mean(v)) for k_, v in rate.items()}
    for name, rows in (("fit", rows_fit), ("holdout", rows_hold)):
        base_rows = [dict(r, p_home=rate.get(key(r), 0.5)) for r in rows]
        out[f"baseline_{name}"] = scores(base_rows)

    # Calibration table (fit + holdout, cross-division): predicted home-win prob buckets
    allr = rows_fit + rows_hold
    bins = [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0001]
    cal = []
    for lo, hi in zip(bins, bins[1:]):
        rr = [r for r in allr if lo <= r["p_home"] < hi]
        if rr:
            cal.append(dict(bin=f"{lo:.1f}-{min(hi,1):.1f}", n=len(rr), predicted=float(np.mean([r['p_home'] for r in rr])),
                            actual=float(np.mean([r['y'] for r in rr]))))
    out["calibration"] = cal

    # Division-gap bias check: mean (actual - predicted) for the M1 side in M1-M2 games
    m12 = [r for r in allr if {int(r['g'].home[1]), int(r['g'].away[1])} == {1, 2}]
    bias = np.mean([(r["y"] - r["p_home"]) * (1 if r["g"].home.startswith("M1") else -1) for r in m12])
    out["m1_side_bias"] = dict(n=len(m12), mean_actual_minus_pred=float(bias))

    print(json.dumps({k_: v for k_, v in out.items() if k_ != "calibration"}, indent=1))
    print("calibration (predicted vs actual home win rate):")
    for c in cal:
        print(f"  {c['bin']}: n={c['n']:3d} predicted {c['predicted']:.2f} actual {c['actual']:.2f}")
    with open(os.path.join(ROOT, "data/xdiv_model.json"), "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
