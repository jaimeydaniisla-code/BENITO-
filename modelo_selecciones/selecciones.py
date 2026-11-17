"""Selecciones: Poisson bivariante Dixon-Coles con decaimiento, peso por tipo de partido, L2 y campo neutral."""
import numpy as np, pandas as pd
from scipy.optimize import minimize, minimize_scalar

PESO = [('Friendly', 0.5), ('Nations League', 0.8), ('qualification', 1.0), ('FIFA World Cup', 1.2), ('UEFA Euro', 1.2), ('Copa Am', 1.1), ('African Cup', 1.1), ('AFC Asian', 1.1)]


def peso_torneo(t):
    for k, v in PESO:
        if k in str(t):
            return v
    return 0.8


class Sel:
    def __init__(self, xi=0.0003, reg=2.0):
        self.xi, self.reg = xi, reg

    def fit(self, df, ref, desde='2014-01-01'):
        d = df[(df.date >= desde) & (df.date < ref)].dropna(subset=['home_score', 'away_score'])
        teams = sorted(set(d.home_team) | set(d.away_team)); idx = {t: i for i, t in enumerate(teams)}; n = len(teams)
        hi = d.home_team.map(idx).values; ai = d.away_team.map(idx).values
        days = (ref - d.date).dt.days.values.astype(float)
        wt = np.exp(-self.xi * days) * d.tournament.map(peso_torneo).values
        x = d.home_score.values.astype(float); y = d.away_score.values.astype(float)
        nh = (~d.neutral.astype(str).str.upper().eq('TRUE')).values.astype(float)
        reg = self.reg

        def f(p):
            att, de, c, h = p[:n], p[n:2 * n], p[2 * n], p[2 * n + 1]
            e1 = c + h * nh + att[hi] + de[ai]; e2 = c + att[ai] + de[hi]
            l1, l2 = np.exp(e1), np.exp(e2)
            g1 = wt * (x - l1); g2 = wt * (y - l2)
            obj = -(wt * (x * e1 - l1 + y * e2 - l2)).sum() + reg * (att @ att + de @ de)
            ga = -(np.bincount(hi, g1, n) + np.bincount(ai, g2, n)) + 2 * reg * att
            gd = -(np.bincount(ai, g1, n) + np.bincount(hi, g2, n)) + 2 * reg * de
            return obj, np.concatenate([ga, gd, [-(g1.sum() + g2.sum()), -(g1 * nh).sum()]])
        r = minimize(f, np.zeros(2 * n + 2) + np.r_[np.zeros(2 * n), 0.2, 0.2], jac=True, method='L-BFGS-B', options={'maxiter': 2000})
        self.p, self.idx, self.n = r.x, idx, n
        att, de, c, h = self.p[:n], self.p[n:2 * n], self.p[2 * n], self.p[2 * n + 1]
        l1 = np.exp(c + h * nh + att[hi] + de[ai]); l2 = np.exp(c + att[ai] + de[hi])
        m = {k: (x == a) & (y == b) for k, (a, b) in {'00': (0, 0), '01': (0, 1), '10': (1, 0), '11': (1, 1)}.items()}

        def nll(rho):
            t = np.ones_like(l1)
            t[m['00']] = 1 - l1[m['00']] * l2[m['00']] * rho; t[m['01']] = 1 + l1[m['01']] * rho
            t[m['10']] = 1 + l2[m['10']] * rho; t[m['11']] = 1 - rho
            return 1e10 if np.any(t <= 0) else -(wt * np.log(t)).sum()
        self.rho = minimize_scalar(nll, bounds=(-0.3, 0.1), method='bounded').x
        self.h, self.c, self.nteams = h, c, n
        self.ult = d.groupby('home_team').size().add(d.groupby('away_team').size(), fill_value=0)
        return self

    def lambdas(self, h, a, neutral):
        att, de = self.p[:self.n], self.p[self.n:2 * self.n]
        i, j = self.idx[h], self.idx[a]
        return float(np.exp(self.c + (0 if neutral else self.h) + att[i] + de[j])), float(np.exp(self.c + att[j] + de[i]))

    def matriz(self, l1, l2, K=12):
        from scipy.stats import poisson
        M = np.outer(poisson.pmf(range(K), l1), poisson.pmf(range(K), l2)); r = self.rho
        M[0, 0] *= 1 - l1 * l2 * r; M[0, 1] *= 1 + l1 * r; M[1, 0] *= 1 + l2 * r; M[1, 1] *= 1 - r
        return M / M.sum()


def mercados(M):
    K = M.shape[0]; i, j = np.indices(M.shape); tot = i + j; d = i - j
    pH, pD, pA = M[d > 0].sum(), M[d == 0].sum(), M[d < 0].sum()
    out = {'1X2: Local': pH, '1X2: Visitante': pA, 'DO: 1X': pH + pD, 'DO: X2': pD + pA, 'DO: 12': pH + pA,
           'DNB: Local': pH / (pH + pA), 'DNB: Visitante': pA / (pH + pA),
           'BTTS Sí': M[1:, 1:].sum(), 'BTTS No': 1 - M[1:, 1:].sum(),
           'H-1,5 L': M[d >= 2].sum(), 'H-1,5 V': M[d <= -2].sum(), 'H+1,5 V': 1 - M[d >= 2].sum(), 'H+1,5 L': 1 - M[d <= -2].sum(),
           'Local gana sin encajar': M[1:, 0].sum(), 'Visitante gana sin encajar': M[0, 1:].sum()}
    for L in (0.5, 1.5, 2.5, 3.5, 4.5):
        out[f'T>{L}'] = M[tot > L].sum()
        out[f'L>{L}'] = M[i > L].sum()
        out[f'V>{L}'] = M[j > L].sum()
    return out


def validar():
    """Walk-forward por bloques: ajusta con datos anteriores a cada trimestre y puntúa el siguiente (1X2, log-loss)."""
    d = pd.read_csv('resultados_selecciones.csv', parse_dates=['date']).dropna(subset=['home_score'])
    res = {}
    for xi in (0.0002, 0.0004, 0.0008):
        ll = []; base = []
        for ini in pd.date_range('2023-01-01', '2026-07-01', freq='6MS'):
            fin = ini + pd.DateOffset(months=6)
            te = d[(d.date >= ini) & (d.date < fin)]
            m = Sel(xi=xi).fit(d, ini)
            for r in te.itertuples():
                if r.home_team not in m.idx or r.away_team not in m.idx or m.ult.get(r.home_team, 0) < 8 or m.ult.get(r.away_team, 0) < 8:
                    continue
                M = m.matriz(*m.lambdas(r.home_team, r.away_team, str(r.neutral).upper() == 'TRUE'))
                mk = mercados(M); dd = r.home_score - r.away_score
                p = mk['1X2: Local'] if dd > 0 else (1 - mk['1X2: Local'] - mk['1X2: Visitante'] if dd == 0 else mk['1X2: Visitante'])
                ll.append(-np.log(max(p, 1e-9))); base.append(-np.log(1 / 3))
        res[xi] = (np.mean(ll), len(ll), np.mean(base)); print('xi', xi, 'logloss 1X2 %.4f' % np.mean(ll), 'n', len(ll), '(azar 1,0986)', flush=True)
    return res


if __name__ == '__main__':
    validar()
