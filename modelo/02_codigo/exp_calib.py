import os, numpy as np, pandas as pd
rows = pd.read_pickle(os.path.join(os.path.dirname(__file__), '..', '03_experimentos', 'exp_rows.pkl'))
sel = [r for r in rows if r['season'] >= 2022]
keys = [k for k in sel[0]['real'] if k not in ('H','D','A','AH+1.5_A','DNB_A','X2')]
bins = [0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
for src in ('model', 'B365'):
    P, Y = [], []
    for r in sel:
        for k in keys: P.append(r[src][k]); Y.append(r['real'][k])
    P, Y = np.array(P), np.array(Y, float)
    print(f'\n{src}: predicho -> acertado (n)  [todos los mercados, 2022-26]')
    for a, b in zip(bins[:-1], bins[1:]):
        s = (P >= a) & (P < b)
        print(f'  {a:.1f}-{min(b,1):.2f}: predicho {P[s].mean():.3f} -> real {Y[s].mean():.3f} (n={s.sum()})')
# devig
from exp_mercado import devig
import sys
sys.path.insert(0,'.')
from matches import load_matches
m = load_matches(); m = m[m.Date >= '2021-08-01']
y = m.res.values
def power(o):
    q = 1 / np.array(o, float); lo, hi = 0.5, 3
    for _ in range(60):
        k = (lo + hi) / 2
        if (q ** k).sum() > 1: lo = k
        else: hi = k
    p = q ** k; return p / p.sum()
for name, fn in (('proporcional', devig), ('potencia', power)):
    for lab, cols in (('B365', ['B365H','B365D','B365A']), ('Avg', ['AvgH','AvgD','AvgA'])):
        P = np.array([fn(r) for r in m[cols].values]); print(name, lab, 'logloss 1X2', round(-np.mean(np.log(P[np.arange(len(y)), y])), 4))
