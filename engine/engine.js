/* ACHA Men's Division 2 ranking engine (browser port of engine/engine.py; keep the two identical).
 *
 *   GD        = clamp(goalsFor - goalsAgainst, -7, 7)   (forced ties -> 0)
 *   GmPerf    = mean(GD);  Sched = mean(opponent Total);  Total = GmPerf + Sched
 *               (damped Jacobi to convergence, GP-weighted mean pinned at 7.0)
 *   OTAdj     = 0.5 * OTL / GP   (after convergence)
 *   Raw       = Total + OTAdj;  AWP = 0.8 * W / (W + L);  Final = Raw + AWP - Penalty
 */
(function (root) {
  "use strict";
  const CAP = 7, START = 7.0, OT_ADJ = 0.5, AWP_WEIGHT = 0.8, MIN_GP_RANKED = 3;

  function gdHome(g, cap) {
    if (g.tie) return 0;
    return Math.max(-cap, Math.min(cap, g.hg - g.ag));
  }

  // games: [{home, away, hg, ag, ot, so, tie}]
  // opts.init: {team: rating} warm start (must itself be GP-mean 7 to keep the pin; used for simulations)
  function solve(games, opts) {
    const o = Object.assign({ cap: CAP, start: START, tol: 1e-10, maxIter: 100000, init: null }, opts || {});
    const idx = new Map(), T = [];
    const team = (name) => {
      let i = idx.get(name);
      if (i === undefined) {
        i = T.length; idx.set(name, i);
        T.push({ team: name, gp: 0, w: 0, l: 0, t: 0, otw: 0, otl: 0, gf: 0, ga: 0, gd: 0, opp: [] });
      }
      return T[i];
    };
    for (const g of games) {
      const d = gdHome(g, o.cap);
      const h = team(g.home), a = team(g.away);
      const sides = [[h, a, d, g.hg, g.ag], [a, h, -d, g.ag, g.hg]];
      for (const [me, opp, dd, gf, ga] of sides) {
        me.gp++; me.gf += gf; me.ga += ga; me.gd += dd; me.opp.push(idx.get(opp.team));
        if (g.tie || dd === 0) me.t++;
        else if (dd > 0) { me.w++; if (g.ot) me.otw++; }
        else { me.l++; if (g.ot) me.otl++; }
      }
    }
    const n = T.length;
    const perf = new Float64Array(n);
    let R = new Float64Array(n), N = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      perf[i] = T[i].gd / T[i].gp;
      R[i] = o.init && o.init[T[i].team] != null ? o.init[T[i].team] : o.start;
    }
    if (o.init) { // re-pin the GP-weighted mean (games added since the warm start change the weights)
      let ws = 0, w = 0;
      for (let i = 0; i < n; i++) { ws += T[i].gp * R[i]; w += T[i].gp; }
      const shift = o.start - ws / w;
      for (let i = 0; i < n; i++) R[i] += shift;
    }
    let iter = 0;
    for (; iter < o.maxIter; iter++) {
      let delta = 0;
      for (let i = 0; i < n; i++) {
        const opp = T[i].opp;
        let s = 0;
        for (let k = 0; k < opp.length; k++) s += R[opp[k]];
        const v = 0.5 * R[i] + 0.5 * (perf[i] + s / opp.length);
        const dv = Math.abs(v - R[i]);
        if (dv > delta) delta = dv;
        N[i] = v;
      }
      const tmp = R; R = N; N = tmp;
      if (delta < o.tol) break;
    }
    const out = {};
    for (let i = 0; i < n; i++) {
      const t = T[i];
      let s = 0;
      for (const k of t.opp) s += R[k];
      const r = {
        team: t.team, gp: t.gp, w: t.w, l: t.l, t: t.t, otw: t.otw, otl: t.otl, gf: t.gf, ga: t.ga,
        gmperf: perf[i], sched: s / t.gp, total: R[i], otadj: OT_ADJ * t.otl / t.gp,
      };
      r.raw = r.total + r.otadj;
      r.awp = (r.w + r.l) ? AWP_WEIGHT * r.w / (r.w + r.l) : 0;
      out[t.team] = r;
    }
    Object.defineProperty(out, "_iterations", { value: iter, enumerable: false });
    return out;
  }

  // Returns {region: [rows sorted, rank set on ranked rows]}
  function rank(teams, regions, penalties, notGoodStanding, minGp) {
    penalties = penalties || {};
    const ngs = new Set(notGoodStanding || []);
    const mg = minGp == null ? MIN_GP_RANKED : minGp;
    const out = {};
    for (const name in teams) {
      const r = teams[name];
      r.penalty = penalties[name] || 0;
      r.final = r.raw + r.awp - r.penalty;
      r.region = regions[name] || null;
      r.status = ngs.has(name) ? "not_good_standing" : (r.gp < mg ? "min_games" : "ranked");
      (out[r.region || "Unassigned"] = out[r.region || "Unassigned"] || []).push(r);
    }
    for (const reg in out) {
      out[reg].sort((a, b) =>
        ((a.status !== "ranked") - (b.status !== "ranked")) || (b.final - a.final) || (b.raw - a.raw) || (b.sched - a.sched));
      let k = 0;
      for (const r of out[reg]) r.rank = r.status === "ranked" ? ++k : null;
    }
    return out;
  }

  root.M2Engine = { CAP, START, OT_ADJ, AWP_WEIGHT, MIN_GP_RANKED, gdHome, solve, rank };
})(typeof window !== "undefined" ? window : globalThis);
