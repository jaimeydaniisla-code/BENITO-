"""Dixon-Coles con decaimiento temporal y penalización L2. Ajuste walk-forward sin fuga."""
import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

MAXG = 10


class DC:
    def __init__(self, xi=0.0005, reg=5.0):
        self.xi, self.reg = xi, reg

    def fit(self, train, ref_date):
        teams = sorted(set(train.HomeTeam) | set(train.AwayTeam))
        self.teams = teams
        idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        hi = train.HomeTeam.map(idx).values
        ai = train.AwayTeam.map(idx).values
        x = train.FTHG.values.astype(float)
        y = train.FTAG.values.astype(float)
        days = (ref_date - train.Date).dt.days.values.astype(float)
        assert days.min() > 0, 'FUGA: partido de entrenamiento no anterior a la fecha de referencia'
        w = np.exp(-self.xi * days)
        m00 = (x == 0) & (y == 0); m01 = (x == 0) & (y == 1)
        m10 = (x == 1) & (y == 0); m11 = (x == 1) & (y == 1)
        reg = self.reg

        def f(p):
            att, de, c, h, rho = p[:n], p[n:2 * n], p[2 * n], p[2 * n + 1], p[2 * n + 2]
            e1 = c + h + att[hi] + de[ai]
            e2 = c + att[ai] + de[hi]
            l1, l2 = np.exp(e1), np.exp(e2)
            ll = x * e1 - l1 + y * e2 - l2
            g1 = x - l1; g2 = y - l2; gr = np.zeros_like(x)
            t = np.ones_like(x)
            t[m00] = 1 - l1[m00] * l2[m00] * rho
            t[m01] = 1 + l1[m01] * rho
            t[m10] = 1 + l2[m10] * rho
            t[m11] = 1 - rho
            if np.any(t <= 0):
                return 1e10, np.zeros_like(p)
            ll = ll + np.log(t)
            q = l1[m00] * l2[m00]
            g1[m00] += -q * rho / t[m00]; g2[m00] += -q * rho / t[m00]; gr[m00] = -q / t[m00]
            g1[m01] += l1[m01] * rho / t[m01]; gr[m01] = l1[m01] / t[m01]
            g2[m10] += l2[m10] * rho / t[m10]; gr[m10] = l2[m10] / t[m10]
            gr[m11] = -1 / t[m11]
            obj = -(w * ll).sum() + reg * (att @ att + de @ de)
            wg1, wg2 = w * g1, w * g2
            gatt = -(np.bincount(hi, wg1, n) + np.bincount(ai, wg2, n)) + 2 * reg * att
            gde = -(np.bincount(ai, wg1, n) + np.bincount(hi, wg2, n)) + 2 * reg * de
            gc = -(wg1.sum() + wg2.sum()); gh = -wg1.sum(); grho = -(w * gr).sum()
            return obj, np.concatenate([gatt, gde, [gc, gh, grho]])

        p0 = getattr(self, '_warm', None)
        if p0 is None or len(p0) != 2 * n + 3:
            p0 = np.concatenate([np.zeros(2 * n), [0.3, 0.25, -0.05]])
        bounds = [(None, None)] * (2 * n + 2) + [(-0.3, 0.3)]
        r = minimize(f, p0, jac=True, method='L-BFGS-B', bounds=bounds, options={'maxiter': 2000})
        self.p, self._warm, self.ok = r.x, r.x, r.success
        self.idx, self.n = idx, n
        return self

    def rates(self, home, away):
        p, n = self.p, self.n
        att, de, c, h = p[:n], p[n:2 * n], p[2 * n], p[2 * n + 1]
        a_h = att[self.idx[home]] if home in self.idx else 0.0
        d_h = de[self.idx[home]] if home in self.idx else 0.0
        a_a = att[self.idx[away]] if away in self.idx else 0.0
        d_a = de[self.idx[away]] if away in self.idx else 0.0
        return np.exp(c + h + a_h + d_a), np.exp(c + a_a + d_h)

    def score_matrix(self, home, away):
        l1, l2 = self.rates(home, away)
        rho = self.p[-1]
        g = np.arange(MAXG + 1)
        M = np.outer(poisson.pmf(g, l1), poisson.pmf(g, l2))
        M[0, 0] *= 1 - l1 * l2 * rho; M[0, 1] *= 1 + l1 * rho
        M[1, 0] *= 1 + l2 * rho; M[1, 1] *= 1 - rho
        return M / M.sum(), l1, l2


def probs_1x2(M):
    return np.array([np.tril(M, -1).sum(), np.trace(M), np.triu(M, 1).sum()])
