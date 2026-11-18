"""Walk-forward semanal del modelo xG (DCX) sobre SP1 desde 2021-08: guarda lambdas y rho por partido (sin fuga)."""
import os, pickle, sys
import numpy as np, pandas as pd
os.environ['LALIGA_DATA'] = os.path.join(os.path.dirname(__file__), '..', '01_datos', 'historico') + os.sep
from matches import load_matches, promoted_in
from dcx import DCX
CFG = dict(xi=0.0005, reg=3.0, w=0.0, promo_att=-0.15, promo_def=0.15)
m = load_matches()
start = pd.Timestamp('2021-08-01')
t = m[m.Date >= start].copy()
wk = t.Date.dt.to_period('W-SUN').dt.start_time
out = {}
for w, g in t.groupby(wk):
    ref = w
    tr = m[m.Date < ref]
    season = ref.year if ref.month >= 7 else ref.year - 1
    mod = DCX(**CFG).fit(tr, ref, promoted=promoted_in(m, season))
    for i, r in g.iterrows():
        l1, l2 = mod.rates(r.HomeTeam, r.AwayTeam)
        out[i] = (l1, l2, mod.rho)
res = pd.DataFrame(out, index=['l1', 'l2', 'rho']).T
res.to_pickle(os.path.join(os.path.dirname(__file__), '..', '03_experimentos', 'wf_lambdas.pkl'))
print(len(res), res.describe().round(3))
