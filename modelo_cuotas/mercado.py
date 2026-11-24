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


def margenes(m):
    """Margen de bwin por mercado (suma de 1/cuota - 1) en las parejas principales."""
    bw, H, A, out = m.get('bw') or {}, m['h'], m['a'], {}
    def mg(*ks):
        return round(sum(1 / bw[k] for k in ks) - 1, 3) if all(bw.get(k, 0) > 1 for k in ks) else None
    out['1X2'] = mg(f'Gana {H}', 'Empate', f'Gana {A}')
    out['Goles'] = mg('Goles: más de 2,5', 'Goles: menos de 2,5')
    out['Ambos marcan'] = mg('Ambos marcan: Sí', 'Ambos marcan: No')
    for nm in ('Córners', 'Tarjetas'):
        ls = sorted({k.split('de ')[-1] for k in bw if k.startswith(nm + ': más de ') and bw.get(nm + ': menos de ' + k.split('de ')[-1])},
                    key=lambda x: abs(1 / bw[nm + ': más de ' + x] - 1 / bw[nm + ': menos de ' + x]))
        if ls: out[nm] = mg(nm + ': más de ' + ls[0], nm + ': menos de ' + ls[0])
    return {k: v for k, v in out.items() if v is not None}


def justas(m):
    """Probabilidad justa (sin margen) de cada selección según Pinnacle, emparejando sus dos caras (o las tres del 1X2)."""
    pn, H, A, out = m.get('pin') or {}, m['h'], m['a'], {}
    ks = (f'Gana {H}', 'Empate', f'Gana {A}')
    if all(pn.get(k, 0) > 1 for k in ks):
        pH, pD, pA = devig_pot([pn[k] for k in ks])
        out.update({ks[0]: pH, 'Empate': pD, ks[2]: pA, f'{H} o empate': pH + pD, f'Empate o {A}': pD + pA, 'No hay empate': pH + pA,
                    f'{H} (empate no válido)': pH / (pH + pA), f'{A} (empate no válido)': pA / (pH + pA)})
    for k, v in pn.items():
        if ': más de ' in k:
            k2 = k.replace(': más de ', ': menos de ')
            if pn.get(k2, 0) > 1 and v > 1:
                p1, p2 = devig_pot([v, pn[k2]]); out[k] = p1; out[k2] = p2
    if pn.get('Ambos marcan: Sí', 0) > 1 and pn.get('Ambos marcan: No', 0) > 1:
        p1, p2 = devig_pot([pn['Ambos marcan: Sí'], pn['Ambos marcan: No']]); out['Ambos marcan: Sí'] = p1; out['Ambos marcan: No'] = p2
    return {k: round(float(v), 4) for k, v in out.items()}


def objetivos_pin(m):
    """(pH, pD, pA, pOver, línea) sin margen a partir de Pinnacle (referencia más fiable), o None."""
    pn, H, A = m.get('pin') or {}, m['h'], m['a']
    ks = (f'Gana {H}', 'Empate', f'Gana {A}')
    if not all(pn.get(k, 0) > 1 for k in ks): return None
    for L in (2.5, 3.5, 1.5):
        ko, ku = f'Goles: más de {c(L)}', f'Goles: menos de {c(L)}'
        if pn.get(ko, 0) > 1 and pn.get(ku, 0) > 1:
            p3 = devig_pot([pn[k] for k in ks])
            return p3[0], p3[1], p3[2], devig_pot([pn[ko], pn[ku]])[0], L
    return None


def objetivos(m):
    """(pH, pD, pA, pOver2.5) sin margen: de Pinnacle si está; si no, de las cuotas bwin del partido; o None si faltan."""
    m.pop('mkp', None); m.pop('pj', None)
    if m.get('bw'): m['mg'] = margenes(m)
    if m.get('pin'):
        pj = justas(m)
        if pj: m['pj'] = pj
    op = objetivos_pin(m)
    if op: m['mkp'] = 1; m.pop('mkf', None); return op
    bw, H, A = m.get('bw') or {}, m['h'], m['a']
    k1, k2, k3 = f'{H} o empate', f'Empate o {A}', 'No hay empate'
    if not all(bw.get(k, 0) > 1 for k in (k1, k2, k3)):
        fd = m.get('fd')  # respaldo gratuito: 1X2 y más/menos 2,5 de football-data
        if not fd: return None
        p3 = devig_pot(fd[:3]); m['mkf'] = 1
        return p3[0], p3[1], p3[2], devig_pot(fd[3:5])[0], 2.5
    m.pop('mkf', None)
    linea = None  # línea de goles totales con las dos caras cotizadas (2,5 es la validada; si falta, 3,5 o 1,5)
    for L in (2.5, 3.5, 1.5):
        ko, ku = f'Goles: más de {c(L)}', f'Goles: menos de {c(L)}'
        if bw.get(ko, 0) > 1 and bw.get(ku, 0) > 1: linea = L; break
    if linea is None: return None
    q = np.array([1 / bw[k1], 1 / bw[k2], 1 / bw[k3]])
    a, b, cc = q * 2 / q.sum()  # 1X, X2, 12 sumando 2
    p3 = np.array([1 - b, 1 - cc, 1 - a])  # H, D, A
    if (p3 <= 0.01).any(): return None
    return p3[0], p3[1], p3[2], devig_pot([bw[ko], bw[ku]])[0], linea


def ajustar_lambdas(obj, x0):
    pH, pD, pA, pO, L = obj

    def f(z):
        M = matrix(np.exp(z[0]), np.exp(z[1]))
        return [np.tril(M, -1).sum() - pH, np.trace(M) - pD, M[TOT > L].sum() - pO]
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
    g0 = m.get('g') if (m.get('g') and None not in m['g']) else [1.4, 1.1]
    if not m.get('mk') and 'm1x2' not in m and m.get('g') and None not in m['g']:
        M0 = matrix(m['g'][0], m['g'][1])   # 1X2 de nuestro modelo (forma, xG, localía) antes de ajustar al mercado: segunda opinión
        m['m1x2'] = [round(float(np.tril(M0, -1).sum()), 4), round(float(np.trace(M0)), 4), round(float(np.triu(M0, 1).sum()), 4)]
    m['p1x2'] = [round(float(obj[0]), 4), round(float(obj[1]), 4), round(float(obj[2]), 4)]   # 1X2 justo del mercado (Pinnacle si lo hay)
    lam, err = ajustar_lambdas(obj, g0)
    if err > 0.03: return False  # el mercado no encaja en la matriz: mejor no tocar
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
    # "Más córners": mercado de 3 resultados. bwin da local y visitante; el empate (≈10 % de los partidos) se toma del modelo.
    H, A = m['h'], m['a']; kh, ka = f'Más córners: {H}', f'Más córners: {A}'
    if bw.get(kh, 0) > 1 and bw.get(ka, 0) > 1:
        sh = [s for s in m['s'] if s[0] == kh]; sa = [s for s in m['s'] if s[0] == ka]
        ph = sh[0][2] if sh else None; pa = sa[0][2] if sa else None
        if ph is not None or pa is not None:
            emp = 1 - ph - pa if (ph is not None and pa is not None) else 0.10
            emp = min(max(emp, 0.05), 0.2)
            q = (1 / bw[kh]) / (1 / bw[kh] + 1 / bw[ka])
            if sh: sh[0][2] = round(float(w * q * (1 - emp) + (1 - w) * sh[0][2]), 3); n += 1
            if sa: sa[0][2] = round(float(w * (1 - q) * (1 - emp) + (1 - w) * sa[0][2]), 3); n += 1
    if n: m['s'].sort(key=lambda x: -x[2]); m['mkc'] = 1
    return n
