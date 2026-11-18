"""Córners y tarjetas: calibración walk-forward de las selecciones tipo pick (totales y por equipo) frente a la media de la liga."""
import os, numpy as np, pandas as pd
os.environ['LALIGA_DATA'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '01_datos', 'historico') + os.sep
from matches import load_matches
from countmodel import CountModel, count_pmf
CFGS = {'cor': (dict(xi=0.003, reg_team=15, reg_ref=5, use_ref=False), 'HC', 'AC', [7.5, 8.5, 9.5, 10.5, 11.5, 12.5], [3.5, 4.5, 5.5, 6.5]),
        'tar': (dict(xi=0.003, reg_team=40, reg_ref=40, use_ref=False), 'HK', 'AK', [2.5, 3.5, 4.5, 5.5, 6.5], [0.5, 1.5, 2.5, 3.5])}
df = load_matches(); df['Referee'] = np.nan
def pm(mu, d): return count_pmf(mu, d)
def over(pmf, L): return 1 - np.cumsum(pmf)[int(np.floor(L))]
res = {}
for cat, (cfg, hc, ac, TL, EL) in CFGS.items():
    test = df[df.season >= 2022].copy(); test['wk'] = test.Date.dt.to_period('W-MON')
    m = CountModel(**cfg); rows = []
    for wk, g in test.groupby('wk'):
        ref = g.Date.min(); tr = df[df.Date < ref]; m.fit(tr, ref, hc, ac)
        w = np.exp(-m.xi * (ref - tr.Date).dt.days.values)
        bh, ba = np.sum(w * tr[hc]) / w.sum(), np.sum(w * tr[ac]) / w.sum()
        for i, r in g.iterrows():
            l1, l2 = m.rates(r.HomeTeam, r.AwayTeam)
            for sh, tag in ((1.0, 'mod'), (0.5, 'mix50')):  # mezcla log-lambda con la media de la liga
                a1, a2 = np.exp(sh * np.log(l1) + (1 - sh) * np.log(bh)), np.exp(sh * np.log(l2) + (1 - sh) * np.log(ba))
                for L in TL:
                    rows.append((tag, 'tot', L, over(pm(a1 + a2, m.disp_total), L), r[hc] + r[ac] > L, r.season))
                for L in EL:
                    rows.append((tag, 'eq', L, over(pm(a1, m.disp_team), L), r[hc] > L, r.season)); rows.append((tag, 'eq', L, over(pm(a2, m.disp_team), L), r[ac] > L, r.season))
            for L in TL: rows.append(('base', 'tot', L, over(pm(bh + ba, m.disp_total), L), r[hc] + r[ac] > L, r.season))
            for L in EL:
                rows.append(('base', 'eq', L, over(pm(bh, m.disp_team), L), r[hc] > L, r.season)); rows.append(('base', 'eq', L, over(pm(ba, m.disp_team), L), r[ac] > L, r.season))
    R = pd.DataFrame(rows, columns=['tag', 'tipo', 'L', 'p', 'y', 'season']); R['y'] = R.y.astype(float)
    res[cat] = R
    ll = lambda s: -(s.y * np.log(np.clip(s.p, 1e-6, 1 - 1e-6)) + (1 - s.y) * np.log(np.clip(1 - s.p, 1e-6, 1 - 1e-6))).mean()
    print(f'\n== {cat} (partidos test: {len(test)}) logloss por tipo')
    for t in ('tot', 'eq'):
        print(' ', t, {tag: round(ll(R[(R.tag == tag) & (R.tipo == t)]), 4) for tag in ('base', 'mod', 'mix50')})
    # calibración como pick: probabilidad de la selección (over o under, la más probable)
    for tag in ('mod', 'base'):
        S = R[R.tag == tag].copy(); S['pick'] = np.where(S.p >= 0.5, S.p, 1 - S.p); S['hit'] = np.where(S.p >= 0.5, S.y, 1 - S.y)
        print(f' calibración picks ({tag}): predicho -> real (n)')
        for a, b in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)):
            s = S[(S.pick >= a) & (S.pick < b)]
            if len(s): print(f'   {a:.1f}-{min(b,1):.1f}: {s.pick.mean():.3f} -> {s.hit.mean():.3f} (n={len(s)})')
