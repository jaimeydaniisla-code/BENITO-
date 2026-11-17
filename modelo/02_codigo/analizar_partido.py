"""La Liga (SP1): probabilidades de todos los mercados modelados y selección más probable con cuota bwin >= CUOTA_MIN.

    from analizar_partido import analizar, analizar_jornada
    tabla, pick, info = analizar('Real Madrid', 'Barcelona', fecha='2026-11-01',
                                 cuotas={'1X2: Local': 2.10, 'Goles: Más de 2.5': 1.80})

Validación walk-forward (ver 03_resultados/INFORME_PRIMERA.md):
  - Goles (Dixon-Coles entrenado con xG de Understat 2019-26): test 2023-26 logloss 0,973 vs 0,954 del cierre
    -> peor que el mercado. Mezclar con bwin EMPEORA (peso óptimo 0): si das las 3 cuotas 1X2, p_final = mercado.
  - Córners y tarjetas: mejora pequeña sobre la media de la liga. SP1 no trae árbitro -> sin efecto árbitro.
"""
import numpy as np
import pandas as pd
from matches import load_matches, promoted_in
from dcx import DCX, probs_1x2, MAXG
from backtest_counts import prep
from countmodel import CountModel

# Nombres habituales -> nombres de football-data
ALIAS = {'Atlético': 'Ath Madrid', 'Atletico': 'Ath Madrid', 'Atlético de Madrid': 'Ath Madrid', 'Athletic': 'Ath Bilbao',
         'Athletic Club': 'Ath Bilbao', 'Real Sociedad': 'Sociedad', 'Rayo': 'Vallecano', 'Rayo Vallecano': 'Vallecano',
         'Espanyol': 'Espanol', 'Deportivo': 'La Coruna', 'Deportivo de La Coruña': 'La Coruna', 'Dépor': 'La Coruna',
         'Racing': 'Santander', 'Racing de Santander': 'Santander', 'Málaga': 'Malaga', 'Alavés': 'Alaves',
         'Celta de Vigo': 'Celta', 'Real Betis': 'Betis', 'Atlético Madrid': 'Ath Madrid'}


def nombre(t):
    return ALIAS.get(t, t)


CUOTA_MIN = 1.50
CFG_GOLES = dict(xi=0.0005, reg=3.0, w=0.0, promo_att=-0.15, promo_def=0.15)  # 100 % xG Understat
CFG_CORNERS = dict(xi=0.003, reg_team=15, reg_ref=5, use_ref=False)
CFG_TARJETAS = dict(xi=0.003, reg_team=40, reg_ref=40, use_ref=False)  # sin datos de árbitro
PESO_MODELO_MEZCLA = 0.0  # validado: cualquier peso > 0 empeora el logloss frente a bwin

FIAB = {'1X2': 'media (con cuotas = mercado; el modelo no bate a bwin)', 'Doble oportunidad': 'media', 'Empate no válido': 'media',
        'Goles': 'baja-media (no bate al mercado en O/U 2,5)', 'Ambos marcan': 'baja-media (sin cuotas históricas)',
        'Goles equipo': 'media', 'Hándicap': 'media', 'Córners': 'baja (≈ media de la liga)',
        'Córners equipo': 'media', 'Más córners': 'media (bien calibrado)', 'Tarjetas': 'baja-media (sin árbitro)',
        'Tarjetas equipo': 'baja-media (sin árbitro)'}


def _fit_all(fecha):
    ref = pd.Timestamp(fecha)
    m = load_matches(); m = m[m.Date < ref]
    season = ref.year if ref.month >= 7 else ref.year - 1
    g = DCX(**CFG_GOLES).fit(m, ref, promoted=promoted_in(m, season))
    d = prep(); d = d[d.Date < ref]
    c = CountModel(**CFG_CORNERS).fit(d, ref, 'HC', 'AC')
    k = CountModel(**CFG_TARJETAS).fit(d, ref, 'HK', 'AK')
    return g, c, k, m, d


def _lines(pmf, lines, label, fiab):
    cdf = np.cumsum(pmf); out = []
    for L in lines:
        under = cdf[int(np.floor(L))]
        out += [(fiab, f'{label}: Más de {L}', 1 - under), (fiab, f'{label}: Menos de {L}', under)]
    return out


def analizar(local, visitante, arbitro=None, fecha=None, cuotas=None, alineacion_local=None, alineacion_visit=None, minutos=None):
    """alineacion_local / alineacion_visit: listas de nombres de titulares -> añade mercados de jugador (sin validar)."""
    local, visitante = nombre(local), nombre(visitante)
    fecha = fecha or pd.Timestamp.today().normalize()
    g, c, k, m, d = _fit_all(fecha)
    for t in (local, visitante):
        if t not in g.idx:
            print(f'AVISO: {t} sin historial en el modelo de goles')
    M, lh, la = g.score_matrix(local, visitante)
    pH, pD, pA = probs_1x2(M)
    rows = [('1X2', '1X2: Local', pH), ('1X2', '1X2: Empate', pD), ('1X2', '1X2: Visitante', pA),
            ('Doble oportunidad', 'DO: 1X', pH + pD), ('Doble oportunidad', 'DO: X2', pD + pA), ('Doble oportunidad', 'DO: 12', pH + pA),
            ('Empate no válido', 'DNB: Local', pH / (pH + pA)), ('Empate no válido', 'DNB: Visitante', pA / (pH + pA))]
    tot = np.array([np.fliplr(M).diagonal(MAXG - i).sum() for i in range(2 * MAXG + 1)])
    rows += [('Goles',) + r[1:] for r in _lines(tot, [0.5, 1.5, 2.5, 3.5, 4.5], 'Goles', '')]
    btts = M[1:, 1:].sum()
    rows += [('Ambos marcan', 'Ambos marcan: Sí', btts), ('Ambos marcan', 'Ambos marcan: No', 1 - btts)]
    ph_, pa_ = M.sum(1), M.sum(0)
    for name, pm in [('Local', ph_), ('Visitante', pa_)]:
        rows += [('Goles equipo',) + r[1:] for r in _lines(pm, [0.5, 1.5, 2.5], f'Goles {name}', '')]
    diff = {dd: sum(M[i, j] for i in range(MAXG + 1) for j in range(MAXG + 1) if i - j == dd) for dd in range(-MAXG, MAXG + 1)}
    rows += [('Hándicap', 'Hándicap Local -1,5 (gana por 2+)', sum(v for kk, v in diff.items() if kk >= 2)),
             ('Hándicap', 'Hándicap Visitante +1,5', sum(v for kk, v in diff.items() if kk <= 1)),
             ('Hándicap', 'Hándicap Visitante -1,5 (gana por 2+)', sum(v for kk, v in diff.items() if kk <= -2)),
             ('Hándicap', 'Hándicap Local +1,5', sum(v for kk, v in diff.items() if kk >= -1)),
             ('Goles equipo', 'Local gana sin encajar', M[1:, 0].sum()), ('Goles equipo', 'Visitante gana sin encajar', M[0, 1:].sum())]
    dc = c.dists(local, visitante, arbitro)
    rows += [('Córners',) + r[1:] for r in _lines(dc['pmf_tot'], [7.5, 8.5, 9.5, 10.5, 11.5, 12.5], 'Córners', '')]
    for name, pm in [('Local', dc['pmf_h']), ('Visitante', dc['pmf_a'])]:
        rows += [('Córners equipo',) + r[1:] for r in _lines(pm, [3.5, 4.5, 5.5, 6.5], f'Córners {name}', '')]
    J = np.outer(dc['pmf_h'], dc['pmf_a'])
    rows += [('Más córners', 'Más córners: Local', np.tril(J, -1).sum()), ('Más córners', 'Más córners: Empate', np.trace(J)),
             ('Más córners', 'Más córners: Visitante', np.triu(J, 1).sum())]
    dk = k.dists(local, visitante, arbitro)
    rows += [('Tarjetas',) + r[1:] for r in _lines(dk['pmf_tot'], [1.5, 2.5, 3.5, 4.5, 5.5, 6.5], 'Tarjetas', '')]
    for name, pm in [('Local', dk['pmf_h']), ('Visitante', dk['pmf_a'])]:
        rows += [('Tarjetas equipo',) + r[1:] for r in _lines(pm, [0.5, 1.5, 2.5, 3.5], f'Tarjetas {name}', '')]
    T = pd.DataFrame(rows, columns=['tipo', 'mercado', 'p_modelo'])
    T['fiabilidad'] = T.tipo.map(FIAB)
    no_encontrados = []
    if alineacion_local or alineacion_visit:
        from jugadores import tasas, mercados_jugador
        PJ, TJ = tasas()
        for eq, lst, lam, ck in [(local, alineacion_local, lh, None), (visitante, alineacion_visit, la, None)]:
            if not lst:
                continue
            dkk = k.dists(local, visitante)
            ck = dkk['lam_h'] if eq == local else dkk['lam_a']
            R, nf = mercados_jugador(PJ, TJ, lst, eq, lam, ck, minutos)
            T = pd.concat([T, R], ignore_index=True); no_encontrados += nf
    # mezcla con mercado 1X2 si hay las tres cuotas bwin
    T['p_final'] = T.p_modelo
    cuotas = cuotas or {}
    k3 = ['1X2: Local', '1X2: Empate', '1X2: Visitante']
    if all(x in cuotas for x in k3):
        q = np.array([1 / cuotas[x] for x in k3]); q /= q.sum()
        pm = np.array([pH, pD, pA])
        z = PESO_MODELO_MEZCLA * np.log(pm) + (1 - PESO_MODELO_MEZCLA) * np.log(q); b = np.exp(z) / np.exp(z).sum()
        for x, v in zip(k3, b):
            T.loc[T.mercado == x, 'p_final'] = v
        bH, bD, bA = b
        T.loc[T.mercado == 'DO: 1X', 'p_final'] = bH + bD; T.loc[T.mercado == 'DO: X2', 'p_final'] = bD + bA
        T.loc[T.mercado == 'DO: 12', 'p_final'] = bH + bA
        T.loc[T.mercado == 'DNB: Local', 'p_final'] = bH / (bH + bA); T.loc[T.mercado == 'DNB: Visitante', 'p_final'] = bA / (bH + bA)
    T['cuota_justa'] = 1 / T.p_final
    T['cuota_bwin'] = T.mercado.map(cuotas)
    T['EV_%'] = (T.p_final * T.cuota_bwin - 1) * 100
    info = dict(lambda_goles=(round(lh, 2), round(la, 2)), rho=round(g.rho, 3),
                corners_esperados=(round(dc['lam_h'], 2), round(dc['lam_a'], 2)),
                tarjetas_esperadas=(round(dk['lam_h'], 2), round(dk['lam_a'], 2)),
                arbitro=f'{arbitro}: no se usa (SP1 no trae árbitro)' if arbitro else None,
                jugadores_no_encontrados=no_encontrados or None,
                ultimo_partido_goles=str(m.Date.max().date()), ultimo_partido_corners_tarjetas=str(d.Date.max().date()))
    cand = T[T.cuota_bwin >= CUOTA_MIN].sort_values('p_final', ascending=False)
    pick = cand.iloc[0].to_dict() if len(cand) else None
    return T.sort_values('p_final', ascending=False).reset_index(drop=True), pick, info


FIAB_ORDEN = {'media (bien calibrado)': 3, 'media': 2, 'media (con cuotas = mercado; el modelo no bate a bwin)': 2,
              'baja-media (no bate al mercado en O/U 2,5)': 1, 'baja-media (sin árbitro)': 1,
              'baja-media (sin cuotas históricas)': 1, 'baja (≈ media de la liga)': 0, 'baja (sin validar)': 0}


def analizar_jornada(partidos, fecha=None):
    """partidos: lista de dicts {local, visitante, arbitro (opcional), cuotas (dict)}.
    Devuelve una fila por partido con su mejor selección (más probable con cuota >= CUOTA_MIN)
    y la recomendación de la jornada: mayor probabilidad entre las que tienen EV >= 0;
    si ninguna tiene EV >= 0, la más probable avisando de que no hay valor."""
    filas = []
    for p in partidos:
        T, pick, info = analizar(p['local'], p['visitante'], p.get('arbitro'), fecha, p.get('cuotas'))
        if pick is None:
            filas.append(dict(partido=f"{p['local']} - {p['visitante']}", seleccion=None))
            continue
        filas.append(dict(partido=f"{p['local']} - {p['visitante']}", arbitro=p.get('arbitro'), tipo=pick['tipo'],
                          seleccion=pick['mercado'], p_final=pick['p_final'], cuota_justa=pick['cuota_justa'],
                          cuota_bwin=pick['cuota_bwin'], EV_pct=pick['EV_%'], fiabilidad=pick['fiabilidad'],
                          fiab_orden=FIAB_ORDEN.get(pick['fiabilidad'], 0)))
    R = pd.DataFrame(filas).dropna(subset=['seleccion']).sort_values(['p_final', 'fiab_orden'], ascending=False)
    con_valor = R[R.EV_pct >= 0]
    rec = (con_valor if len(con_valor) else R).iloc[0].to_dict() if len(R) else None
    if rec is not None:
        rec['aviso'] = None if len(con_valor) else 'Ninguna selección de la jornada tiene EV >= 0: es la más probable, pero sin valor.'
    return R.reset_index(drop=True), rec
