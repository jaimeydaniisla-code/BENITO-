import os, numpy as np, pandas as pd
rows = pd.read_pickle(os.path.join(os.path.dirname(__file__), '..', '03_experimentos', 'exp_rows_pot.pkl'))
def ll(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6); return -(y * np.log(p) + (1 - y) * np.log(1 - p))
def table(sel, keys, mk):
    out = {}
    for k in keys:
        y = np.array([r['real'][k] for r in sel], float)
        out[k] = {s: ll(np.array([r[s][k] for r in sel]), y).mean() for s in mk}
    return pd.DataFrame(out).T
mk = ['model', 'B365', 'B365_mix0.5', 'B365_mix0.25', 'AvgO', 'AvgC']
keys = ['H', 'D', 'A', '1X', 'X2', 'DNB_H', 'DNB_A', 'O0.5', 'O1.5', 'O2.5', 'O3.5', 'O4.5', 'BTTS', 'H>0.5', 'H>1.5', 'A>0.5', 'A>1.5', 'AH-1.5_H', 'AH+1.5_H', 'AH+1.5_A']
pd.set_option('display.width', 200)
for name, sel in (('VALIDACIÓN 21-23', [r for r in rows if r['season'] in (2021, 2022)]), ('TEST 23-26', [r for r in rows if r['season'] >= 2023])):
    print('\n', name, len(sel)); t = table(sel, keys, mk); print(t.round(4)); print('media', t.mean().round(4).to_dict())
