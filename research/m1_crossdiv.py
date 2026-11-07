"""Exploratory: historical M1-vs-M2 results by M1 strength tier (research for the M1 case study)."""
import json, re, sys, os
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.engine import Game, solve

SEASONS = {10: '2021-22', 21: '2022-23', 34: '2023-24', 46: '2024-25', 60: '2025-26', 73: '2026-27'}
DIV = re.compile(r'^M(?:D)?([123]) (.+)$')

def parse(name):
    m = DIV.match(name)
    return (int(m.group(1)), m.group(2).strip()) if m else (None, name)

def season_games(sid):
    out = []
    for g in json.load(open(f'data/feeds/season{sid}.json'))['SiteKit']['Schedule']:
        if not g['game_status'].startswith('Final'):
            continue
        hd, h = parse(g['home_team_name']); ad, a = parse(g['visiting_team_name'])
        if not hd or not ad:
            continue
        so = g['shootout'] != '0' or 'SO' in g['game_status']
        ot = so or g['overtime'] != '0' or 'OT' in g['game_status']
        out.append(dict(id=g['id'], date=g['date_played'], hd=hd, h=h, ad=ad, a=a,
                        hg=int(g['home_goal_count']), ag=int(g['visiting_goal_count']), ot=ot, so=so))
    return out

def m1_ranks(games, cap):
    """USHSHO-style M1 rating: M1 vs M1 only, OT/SO = tie."""
    gs = [Game(x['id'], x['date'], x['h'], x['a'], x['hg'], x['ag'], x['ot'], x['so'], tie=x['ot'])
          for x in games if x['hd'] == 1 and x['ad'] == 1]
    T = solve(gs, cap=cap)
    order = sorted((t for t in T.values() if t.gp >= 3), key=lambda r: -r.total)
    return {r.team: i + 1 for i, r in enumerate(order)}

if __name__ == '__main__':
    tiers = [(1, 5), (6, 10), (11, 25), (26, 999)]
    tot = defaultdict(Counter)
    upsets = []
    for sid, lab in SEASONS.items():
        G = season_games(sid)
        A, B = m1_ranks(G, 7), m1_ranks(G, 1)
        avg = {t: (A[t] + B[t]) / 2 for t in A if t in B}
        rk = {t: i + 1 for i, t in enumerate(sorted(avg, key=lambda t: (avg[t], B[t])))}
        for x in G:
            if {x['hd'], x['ad']} != {1, 2}:
                continue
            m1, m2 = (x['h'], x['a']) if x['hd'] == 1 else (x['a'], x['h'])
            m1g, m2g = (x['hg'], x['ag']) if x['hd'] == 1 else (x['ag'], x['hg'])
            r = rk.get(m1)
            tier = next((f'{lo}-{hi if hi < 999 else "+"}' for lo, hi in tiers if r and lo <= r <= hi), 'unranked')
            res = 'W' if m2g > m1g else 'L' if m2g < m1g else 'T'
            tot[tier][res] += 1
            tot[tier]['n'] += 1
            if r and r <= 5 and res == 'W':
                upsets.append((lab, x['date'], m2, m2g, m1g, m1, r, 'OT' if x['ot'] else ''))
    print('M2 record vs M1 by M1 season-end computer rank (2021-22 .. 2026-27 to date)')
    for k in ['1-5', '6-10', '11-25', '26-+', 'unranked']:
        c = tot[k]
        if c['n']:
            print(f"  M1 #{k:8s} n={c['n']:3d}  M2 W-L-T {c['W']}-{c['L']}-{c['T']}  M2 win% {c['W']/c['n']:.1%}")
    print('\nM2 wins over a top-5 M1 team:')
    for u in upsets: print('  ', *u)
