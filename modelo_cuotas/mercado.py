"""Probabilidades ajustadas al mercado (bwin).

Validado con backtest sin fuga (SP1 2021-2026, 2.019 partidos, ver modelo/03_experimentos y
resultados-backtest): una matriz de marcadores ajustada a 1X2 + más/menos 2,5 (cuotas sin margen, método
de la potencia) predice MEJOR que el modelo propio en casi todos los mercados, también en los que no
usa para ajustarse (ambos marcan, otras líneas de goles, goles por equipo, hándicap +-1,5):
logloss medio test 23-26: 0,525 (mercado) frente a 0,533 (modelo). Mezclar modelo y mercado queda siempre entre medias.
Si faltan las cuotas necesarias, el partido se queda con el modelo."""
import re
import numpy as np
from scipy.optimize import least_squares
from scipy.stats import poisson

K = np.arange(11)
TOT = np.add.outer(K, K)
DIF = np.subtract.outer(K, K)
RHO = -0.045  # media del rho estimado en el walk-forward (-0,047)


def c(x):
    return str(x).replace('.', ',')


def matrix(l1, l2, rho=RHO):
    M = np.outer(poisson.pmf(K, l1), poisson.pmf(K, l2))
    M[0, 0] *= 1 - l1 * l2 * rho; M[0, 1] *= 1 + l1 * rho; M[1, 0] *= 1 + l2 * rho; M[1, 1] *= 1 - rho
    return M / M.sum()


def devig_pot(o):
    q = 1 / np.array(o, float); lo, hi = 0.5, 3.0
    for _ in range(60):
        k = (lo + hi) / 2
        if (q ** k).sum() > 1: lo = k
        else: hi = k
    p = q ** k
    return p / p.sum()


def objetivos(m):
    """(pH, pD, pA, pOver2.5) sin margen a partir de las cuotas bwin del partido, o None si faltan."""
    bw, H, A = m.get('bw') or {}, m['h'], m['a']
    k1, k2, k3 = f'{H} o empate', f'Empate o {A}', 'No hay empate'
    ko, ku = 'Goles: más de 2,5', 'Goles: menos de 2,5'
    if not all(bw.get(k, 0) > 1 for k in (k1, k2, k3, ko, ku)): return None
    q = np.array([1 / bw[k1], 1 / bw[k2], 1 / bw[k3]])
    a, b, cc = q * 2 / q.sum()  # 1X, X2, 12 sumando 2
    p3 = np.array([1 - b, 1 - cc, 1 - a])  # H, D, A
    if (p3 <= 0.01).any(): return None
    return p3[0], p3[1], p3[2], devig_pot([bw[ko], bw[ku]])[0]


def ajustar_lambdas(obj, x0):
    pH, pD, pA, pO = obj

    def f(z):
        M = matrix(np.exp(z[0]), np.exp(z[1]))
        return [np.tril(M, -1).sum() - pH, np.trace(M) - pD, M[TOT > 2.5].sum() - pO]
    r = least_squares(f, np.log(x0), bounds=(np.log(0.1), np.log(6)), xtol=1e-8)
    return np.exp(r.x), float(np.abs(r.fun).max())


def etiquetas(M, H, A):
    """Todas las selecciones de goles y resultado con su probabilidad: [(etiqueta, categoria, p)]."""
    out = []
    pH, pD, pA = np.tril(M, -1).sum(), np.trace(M), np.triu(M, 1).sum()
    for L in (0.5, 1.5, 2.5, 3.5, 4.5):
        po = M[TOT > L].sum()
        out.append((f'Goles: más de {c(L)}', 'gol', po))
        if L > 0.5: out.append((f'Goles: menos de {c(L)}', 'gol', 1 - po))
    hs, as_ = M.sum(1), M.sum(0)
    for nom, d in ((H, hs), (A, as_)):
        for L in (0.5, 1.5, 2.5):
            po = d[int(L) + 1:].sum()
            out += [(f'Goles {nom}: más de {c(L)}', 'gol', po), (f'Goles {nom}: menos de {c(L)}', 'gol', 1 - po)]
    bt = M[1:, 1:].sum()
    out += [('Ambos marcan: Sí', 'gol', bt), ('Ambos marcan: No', 'gol', 1 - bt)]
    out += [(f'{H} gana sin encajar', 'gol', M[1:, 0].sum()), (f'{A} gana sin encajar', 'gol', M[0, 1:].sum())]
    out += [(f'Gana {H}', 'res', pH), (f'Gana {A}', 'res', pA),
            (f'{H} o empate', 'res', pH + pD), (f'Empate o {A}', 'res', pD + pA), ('No hay empate', 'res', pH + pA),
            (f'{H} (empate no válido)', 'res', pH / (pH + pA)), (f'{A} (empate no válido)', 'res', pA / (pH + pA)),
            (f'{H} +1,5 (no pierde por 2)', 'res', M[DIF >= -1].sum()), (f'{A} +1,5 (no pierde por 2)', 'res', M[DIF <= 1].sum()),
            (f'{H} gana por 2 o más', 'res', M[DIF >= 2].sum()), (f'{A} gana por 2 o más', 'res', M[DIF <= -2].sum())]
    return out


def ajustar(m, pmin=0.42, pmax=0.93):
    """Sustituye en el partido m las probabilidades de goles y resultado por las del mercado. Devuelve True si lo ha hecho."""
    obj = objetivos(m)
    if obj is None: return False
    lam, err = ajustar_lambdas(obj, m.get('g') or [1.4, 1.1])
    if err > 0.02: return False  # el mercado no encaja en la matriz: mejor no tocar
    M = matrix(lam[0], lam[1])
    fi = {}
    for lab, cat, p, f in m['s']:
        if cat in ('gol', 'res'): fi[lab] = f
    resto = [s for s in m['s'] if s[1] not in ('gol', 'res')]
    nuevo = []
    for lab, cat, p in etiquetas(M, m['h'], m['a']):
        f = fi.get(lab, 1 if cat == 'gol' and (lab.startswith('Goles:') or lab.startswith('Ambos')) else 2)
        if pmin <= p <= pmax: nuevo.append([lab, cat, round(float(p), 3), f])
    m['s'] = sorted(resto + nuevo, key=lambda s: -s[2])
    m['g'] = [round(float(lam[0]), 1), round(float(lam[1]), 1)]
    m['mk'] = 1
    return True


def mezclar_conteos(m, w=0.5):
    """Córners y tarjetas: donde bwin cotiza las dos caras de la línea, probabilidad = mitad modelo propio (calibrado en
    backtest, sin cuotas históricas para compararlo con el mercado) + mitad mercado sin margen. Devuelve nº de selecciones tocadas."""
    bw, n = m.get('bw') or {}, 0
    for s in m['s']:
        if s[1] not in ('cor', 'tar'): continue
        mo = re.match(r'^(.*): (más|menos) de (\d+,5)$', s[0])
        if not mo: continue
        otro = f"{mo.group(1)}: {'menos' if mo.group(2) == 'más' else 'más'} de {mo.group(3)}"
        if not (bw.get(s[0], 0) > 1 and bw.get(otro, 0) > 1): continue
        pm = devig_pot([bw[s[0]], bw[otro]])[0]
        s[2] = round(float(w * pm + (1 - w) * s[2]), 3); n += 1
    if n: m['s'].sort(key=lambda x: -x[2]); m['mkc'] = 1
    return n
