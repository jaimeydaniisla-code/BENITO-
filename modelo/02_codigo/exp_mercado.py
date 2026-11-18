"""Mercado-implícito vs modelo: ¿qué estimación de probabilidad es mejor? (walk-forward, sin fuga)
Mercado = cuotas de APERTURA (B365 / media) sin margen (proporcional) -> se ajustan lambdas para reproducir 1X2 + O/U 2,5
y se derivan todos los demás mercados. Se compara con el modelo xG (lambdas del walk-forward) y con mezclas."""
import os, sys
import numpy as np, pandas as pd
from scipy.optimize import least_squares
from scipy.stats import poisson
os.environ['LALIGA_DATA'] = os.path.join(os.path.dirname(__file__), '..', '01_datos', 'historico') + os.sep
from matches import load_matches
K = np.arange(11)

def matrix(l1, l2, rho):
    M = np.outer(poisson.pmf(K, l1), poisson.pmf(K, l2))
    M[0, 0] *= 1 - l1 * l2 * rho; M[0, 1] *= 1 + l1 * rho; M[1, 0] *= 1 + l2 * rho; M[1, 1] *= 1 - rho
    return M / M.sum()

TOT = np.add.outer(K, K)
def mercados(M):
    d = {}
    pH, pD, pA = np.tril(M, -1).sum(), np.trace(M), np.triu(M, 1).sum()
    d['H'], d['D'], d['A'] = pH, pD, pA
    d['1X'], d['X2'], d['12'] = pH + pD, pD + pA, pH + pA
    d['DNB_H'], d['DNB_A'] = pH / (pH + pA), pA / (pH + pA)
    for L in (0.5, 1.5, 2.5, 3.5, 4.5):
        d[f'O{L}'] = M[TOT > L].sum()
    d['BTTS'] = M[1:, 1:].sum()
    hs, as_ = M.sum(1), M.sum(0)
    d['H>0.5'], d['H>1.5'], d['A>0.5'], d['A>1.5'] = 1 - hs[0], 1 - hs[:2].sum(), 1 - as_[0], 1 - as_[:2].sum()
    D = np.subtract.outer(K, K)
    d['AH-1.5_H'] = M[D >= 2].sum(); d['AH+1.5_H'] = M[D >= -1].sum(); d['AH+1.5_A'] = M[D <= 1].sum()
    return d

def real(r):
    h, a = int(r.FTHG), int(r.FTAG); t = h + a; d = {}
    d['H'], d['D'], d['A'] = h > a, h == a, h < a
    d['1X'], d['X2'], d['12'] = h >= a, h <= a, h != a
    d['DNB_H'], d['DNB_A'] = h > a, h < a
    for L in (0.5, 1.5, 2.5, 3.5, 4.5): d[f'O{L}'] = t > L
    d['BTTS'] = h > 0 and a > 0
    d['H>0.5'], d['H>1.5'], d['A>0.5'], d['A>1.5'] = h > 0, h > 1, a > 0, a > 1
    d['AH-1.5_H'] = h - a >= 2; d['AH+1.5_H'] = h - a >= -1; d['AH+1.5_A'] = a - h >= -1
    return d

def devig(o):
    ip = 1 / np.array(o, float); return ip / ip.sum()

def devig_pot(o):
    """Quita el margen con el método de la potencia (corrige el sesgo favorito/longshot; mejor logloss que el proporcional)."""
    q = 1 / np.array(o, float); lo, hi = 0.5, 3.0
    for _ in range(60):
        k = (lo + hi) / 2
        if (q ** k).sum() > 1: lo = k
        else: hi = k
    p = q ** k; return p / p.sum()

DV = devig_pot

def fit_market(oh, od, oa, oo, ou, rho, x0):
    p3 = DV([oh, od, oa]); po = DV([oo, ou])[0]
    def f(z):
        M = matrix(np.exp(z[0]), np.exp(z[1]), rho); mk = mercados(M)
        return [mk['H'] - p3[0], mk['D'] - p3[1], mk['O2.5'] - po]
    r = least_squares(f, np.log(x0), xtol=1e-6)
    return np.exp(r.x)

if __name__ == '__main__':
    m = load_matches(); wf = pd.read_pickle(os.path.join(os.path.dirname(__file__), '..', '03_experimentos', 'wf_lambdas.pkl'))
    m = m.loc[wf.index].join(wf)
    src = {'B365': ('B365H', 'B365D', 'B365A', 'B365>2.5', 'B365<2.5'), 'AvgO': ('AvgH', 'AvgD', 'AvgA', 'Avg>2.5', 'Avg<2.5'),
           'AvgC': ('AvgCH', 'AvgCD', 'AvgCA', 'AvgC>2.5', 'AvgC<2.5')}
    rows = []
    for i, r in m.iterrows():
        row = {'i': i, 'date': r.Date, 'season': r.season, 'real': real(r), 'model': mercados(matrix(r.l1, r.l2, r.rho))}
        for name, c in src.items():
            lam = fit_market(*[r[x] for x in c], r.rho, (r.l1, r.l2))
            row[name] = mercados(matrix(lam[0], lam[1], r.rho)); row[name + '_l'] = lam
            for w in (0.25, 0.5, 0.75):  # mezcla de lambdas (en log) mercado/modelo
                l = np.exp(w * np.log(lam) + (1 - w) * np.log([r.l1, r.l2]))
                row[f'{name}_mix{w}'] = mercados(matrix(l[0], l[1], r.rho))
        rows.append(row)
    pd.to_pickle(rows, os.path.join(os.path.dirname(__file__), '..', '03_experimentos', 'exp_rows_pot.pkl'))
    print('filas', len(rows))
