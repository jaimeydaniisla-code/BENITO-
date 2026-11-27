"""Modelo de conteo por equipo (córners, tarjetas, faltas...).

E[local]  = exp(c + h + gen[local] + con[visit] + arb[árbitro])
E[visit]  = exp(c +     gen[visit] + con[local] + arb[árbitro])
gen = tendencia a generar (córners a favor / tarjetas recibidas), con = lo que provoca en el rival.
Decaimiento temporal, L2 separada para equipos y árbitros. Ajuste solo con partidos anteriores (assert).
Distribución: Binomial Negativa por equipo con dispersión estimada en entrenamiento, y para el total
un parámetro de dispersión propio (puede ser < 1: total menos disperso que Poisson por la correlación negativa).
"""
import numpy as np
from scipy.optimize import minimize, minimize_scalar
from scipy.stats import nbinom, poisson

KMAX = 40


def count_pmf(mu, disp):
    """disp = var/mean. disp<=1.02 -> Poisson (o binomial si <1), >1 -> NB."""
    k = np.arange(KMAX + 1)
    if disp > 1.02:
        r = mu / (disp - 1)
        p = r / (r + mu)
        return nbinom.pmf(k, r, p)
    if disp < 0.98:
        # binomial con la misma media y var = disp*mu  (n entero aproximado)
        from scipy.stats import binom
        q = 1 - disp
        n = max(int(round(mu / q)), int(np.ceil(mu)) + 1)
        return binom.pmf(k, n, mu / n)
    return poisson.pmf(k, mu)


class CountModel:
    def __init__(self, xi=0.003, reg_team=3.0, reg_ref=5.0, use_ref=True):
        self.xi, self.reg_team, self.reg_ref, self.use_ref = xi, reg_team, reg_ref, use_ref

    def fit(self, train, ref_date, hcol, acol):
        days = (ref_date - train.Date).dt.days.values.astype(float)
        assert days.min() > 0, 'FUGA'
        w = np.exp(-self.xi * days)
        teams = sorted(set(train.HomeTeam) | set(train.AwayTeam))
        refs = sorted(set(train.Referee.dropna()))
        ti = {t: i for i, t in enumerate(teams)}; ri = {r: i for i, r in enumerate(refs)}
        n, nr = len(teams), len(refs)
        hi = train.HomeTeam.map(ti).values; ai = train.AwayTeam.map(ti).values
        rr = train.Referee.map(ri).fillna(-1).astype(int).values
        has = rr >= 0
        x = train[hcol].values.astype(float); y = train[acol].values.astype(float)
        R1, R2 = self.reg_team, self.reg_ref if self.use_ref else 1e6

        def f(p):
            g, cn, rf, c, h = p[:n], p[n:2 * n], p[2 * n:2 * n + nr], p[-2], p[-1]
            re = np.where(has, rf[np.clip(rr, 0, None)], 0.0)
            e1 = c + h + g[hi] + cn[ai] + re; e2 = c + g[ai] + cn[hi] + re
            l1, l2 = np.exp(e1), np.exp(e2)
            ll = x * e1 - l1 + y * e2 - l2
            g1, g2 = w * (x - l1), w * (y - l2)
            obj = -(w * ll).sum() + R1 * (g @ g + cn @ cn) + R2 * (rf @ rf)
            gg = -(np.bincount(hi, g1, n) + np.bincount(ai, g2, n)) + 2 * R1 * g
            gc = -(np.bincount(ai, g1, n) + np.bincount(hi, g2, n)) + 2 * R1 * cn
            gr = -np.bincount(rr[has], (g1 + g2)[has], nr) + 2 * R2 * rf
            return obj, np.concatenate([gg, gc, gr, [-(g1.sum() + g2.sum()), -g1.sum()]])

        p0 = np.zeros(2 * n + nr + 2); p0[-2] = np.log(max(x.mean(), 0.1))
        r = minimize(f, p0, jac=True, method='L-BFGS-B', options={'maxiter': 3000})
        self.p, self.ti, self.ri, self.n, self.nr, self.ok = r.x, ti, ri, n, nr, r.success
        # dispersión (var/mean) ponderada de residuos, por equipo y del total
        l1, l2 = self._rates_idx(hi, ai, rr)
        self.disp_team = float(np.sum(w * (((x - l1) ** 2) / l1 + ((y - l2) ** 2) / l2)) / (2 * w.sum()))
        self.disp_total = float(np.sum(w * ((x + y - l1 - l2) ** 2) / (l1 + l2)) / w.sum())
        return self

    def _rates_idx(self, hi, ai, rr):
        p, n, nr = self.p, self.n, self.nr
        g, cn, rf, c, h = p[:n], p[n:2 * n], p[2 * n:2 * n + nr], p[-2], p[-1]
        re = np.where(rr >= 0, rf[np.clip(rr, 0, None)], 0.0)
        return np.exp(c + h + g[hi] + cn[ai] + re), np.exp(c + g[ai] + cn[hi] + re)

    def rates(self, home, away, referee=None):
        p, n, nr = self.p, self.n, self.nr
        g, cn, rf, c, h = p[:n], p[n:2 * n], p[2 * n:2 * n + nr], p[-2], p[-1]
        get = lambda arr, t: arr[self.ti[t]] if t in self.ti else 0.0
        re = rf[self.ri[referee]] if (self.use_ref and referee in self.ri) else 0.0
        return (np.exp(c + h + get(g, home) + get(cn, away) + re), np.exp(c + get(g, away) + get(cn, home) + re))

    def ref_effect(self, referee):
        return float(np.exp(self.p[2 * self.n + self.ri[referee]])) if referee in self.ri else 1.0

    def dists(self, home, away, referee=None):
        l1, l2 = self.rates(home, away, referee)
        return dict(lam_h=l1, lam_a=l2, pmf_h=count_pmf(l1, self.disp_team), pmf_a=count_pmf(l2, self.disp_team),
                    pmf_tot=count_pmf(l1 + l2, self.disp_total))
