"""Modelo de fuerzas tipo Dixon-Coles entrenado sobre un objetivo mezcla goles/xG.

objetivo_local  = w*goles_local + (1-w)*xG_local   (cuasi-verosimilitud de Poisson, admite valores no enteros)
log(lambda_local) = c + h + ataque_local + defensa_visitante ; log(lambda_visit) = c + ataque_visit + defensa_local
Penalización L2 hacia un centro por equipo (0, o un 'prior de ascendido' para equipos recién ascendidos).
rho de Dixon-Coles se estima después, sobre los goles reales, con las lambdas fijas.
Todo se ajusta solo con partidos anteriores a la fecha de referencia (assert de no fuga).
"""
import numpy as np
from scipy.optimize import minimize, minimize_scalar
from scipy.stats import poisson

MAXG = 10


class DCX:
    def __init__(self, xi=0.002, reg=3.0, w=0.5, promo_att=0.0, promo_def=0.0):
        self.xi, self.reg, self.w = xi, reg, w
        self.promo_att, self.promo_def = promo_att, promo_def

    def fit(self, train, ref_date, promoted=()):
        teams = sorted(set(train.HomeTeam) | set(train.AwayTeam) | set(promoted))
        idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        hi = train.HomeTeam.map(idx).values
        ai = train.AwayTeam.map(idx).values
        days = (ref_date - train.Date).dt.days.values.astype(float)
        assert days.min() > 0, 'FUGA: datos de entrenamiento no anteriores a la fecha de referencia'
        wt = np.exp(-self.xi * days)
        gx, gy = train.FTHG.values.astype(float), train.FTAG.values.astype(float)
        xgx, xgy = train.xG_h.values.astype(float), train.xG_a.values.astype(float)
        x = self.w * gx + (1 - self.w) * xgx
        y = self.w * gy + (1 - self.w) * xgy
        ca = np.zeros(n); cd = np.zeros(n)
        for t in promoted:
            ca[idx[t]] = self.promo_att; cd[idx[t]] = self.promo_def
        reg = self.reg

        def f(p):
            att, de, c, h = p[:n], p[n:2 * n], p[2 * n], p[2 * n + 1]
            e1 = c + h + att[hi] + de[ai]; e2 = c + att[ai] + de[hi]
            l1, l2 = np.exp(e1), np.exp(e2)
            ll = x * e1 - l1 + y * e2 - l2
            g1 = wt * (x - l1); g2 = wt * (y - l2)
            da, dd = att - ca, de - cd
            obj = -(wt * ll).sum() + reg * (da @ da + dd @ dd)
            gatt = -(np.bincount(hi, g1, n) + np.bincount(ai, g2, n)) + 2 * reg * da
            gde = -(np.bincount(ai, g1, n) + np.bincount(hi, g2, n)) + 2 * reg * dd
            return obj, np.concatenate([gatt, gde, [-(g1.sum() + g2.sum()), -g1.sum()]])

        p0 = np.concatenate([ca, cd, [0.3, 0.2]])
        r = minimize(f, p0, jac=True, method='L-BFGS-B', options={'maxiter': 3000})
        self.p, self.ok, self.idx, self.n = r.x, r.success, idx, n
        # rho sobre goles reales
        att, de, c, h = self.p[:n], self.p[n:2 * n], self.p[2 * n], self.p[2 * n + 1]
        l1 = np.exp(c + h + att[hi] + de[ai]); l2 = np.exp(c + att[ai] + de[hi])
        m00 = (gx == 0) & (gy == 0); m01 = (gx == 0) & (gy == 1); m10 = (gx == 1) & (gy == 0); m11 = (gx == 1) & (gy == 1)

        def nll(rho):
            t = np.ones_like(l1)
            t[m00] = 1 - l1[m00] * l2[m00] * rho; t[m01] = 1 + l1[m01] * rho
            t[m10] = 1 + l2[m10] * rho; t[m11] = 1 - rho
            if np.any(t <= 0):
                return 1e10
            return -(wt * np.log(t)).sum()
        self.rho = minimize_scalar(nll, bounds=(-0.25, 0.25), method='bounded').x
        return self

    def rates(self, home, away):
        p, n = self.p, self.n
        att, de, c, h = p[:n], p[n:2 * n], p[2 * n], p[2 * n + 1]
        g = lambda arr, t: arr[self.idx[t]] if t in self.idx else 0.0
        return np.exp(c + h + g(att, home) + g(de, away)), np.exp(c + g(att, away) + g(de, home))

    def score_matrix(self, home, away):
        l1, l2 = self.rates(home, away)
        rho = self.rho
        k = np.arange(MAXG + 1)
        M = np.outer(poisson.pmf(k, l1), poisson.pmf(k, l2))
        M[0, 0] *= 1 - l1 * l2 * rho; M[0, 1] *= 1 + l1 * rho
        M[1, 0] *= 1 + l2 * rho; M[1, 1] *= 1 - rho
        return M / M.sum(), l1, l2


def probs_1x2(M):
    return np.array([np.tril(M, -1).sum(), np.trace(M), np.triu(M, 1).sum()])
