"""Segunda División (SP2): analiza un partido y elige la selección más probable con cuota bwin >= 1,50.

Uso:
    from analizar_partido import analizar, analizar_jornada
    T, pick, info = analizar('Andorra', 'Burgos', fecha='2026-10-26',
        cuotas={'1X2: Local': 1.95, '1X2: Empate': 3.30, '1X2: Visitante': 3.80,
                'Goles: Más de 2.5': 2.00, 'Goles: Menos de 2.5': 1.70, ...},
        arbitro_tarjetas_pp=5.66,                       # tarjetas/partido del árbitro (opcional, no validado)
        jugadores=[('Jordi Cano', 'L', 75), ('Jon Karrikaburu', 'V', 75)])   # (nombre FBref, L/V, minutos esperados)

Nombres de equipo: los de football-data (p. ej. 'Andorra', 'Burgos', 'Sp Gijon', 'Castellon').
Las claves de `cuotas` deben coincidir con la columna 'mercado' (imprimir T primero).

Modelos y validación (ver 03_resultados/informe_validacion_SP2.md):
  - Goles/1X2: Dixon-Coles (ξ=0,001, L2=20). Peor que el mercado (logloss 1,047 vs 1,019). Con cuotas 1X2 de bwin se
    mezcla (pesos validados 0,144·modelo + 1,049·mercado). Con cuotas O/U 2,5 de bwin se reescalan las λ para casar.
  - Córners: CountModel (ξ=0,001, L2=50): ≈ media de la liga (sin mejora en test).
  - Tarjetas: CountModel (ξ=0,003, L2=20): mejora pequeña y significativa sobre la media (test −0,011).
    SP2 no trae árbitro: el ajuste por árbitro es opcional, encogido al 50 % y NO validado.
  - Jugadores: tasas FBref 25/26+26/27 por 90', encogidas hacia la media de su posición (900'),
    escaladas por las λ del partido. Calibración 25/26→26/27: goles pred/real 0,97; tiros a puerta 1,05; amarillas 1,02.
    Sin validación partido a partido ni contra cuotas.
"""
import os, glob, sys
import numpy as np, pandas as pd
from scipy.stats import poisson
from scipy.optimize import brentq

AQUI = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, AQUI)
import dc
from countmodel import CountModel

DATOS = os.path.join(AQUI, '..', '01_datos')
CUOTA_MIN = 1.50
CFG_GOLES = dict(xi=0.001, reg=20)
PESOS_MEZCLA = (0.144, 1.049)
CFG_CORNERS = dict(xi=0.001, reg_team=50, use_ref=False)
CFG_TARJETAS = dict(xi=0.003, reg_team=20, use_ref=False)
K_JUG = 900  # minutos de "prior" de posición
PRIOR_POS = {'FW': dict(g=0.331, s=0.987, y=0.220, a=0.106), 'MF': dict(g=0.137, s=0.487, y=0.252, a=0.116),
             'DF': dict(g=0.036, s=0.152, y=0.264, a=0.048), 'GK': dict(g=0.0, s=0.001, y=0.061, a=0.001)}
FIAB = {'1X2': 'media (mezcla con mercado)', 'Doble oportunidad': 'media (mezcla con mercado)',
        'Empate no válido': 'media (mezcla con mercado)', 'Goles': 'media (calibrado a bwin O/U 2,5)',
        'Ambos marcan': 'baja-media', 'Goles equipo': 'media', 'Hándicap': 'media', 'Córners': 'baja (≈ media liga)',
        'Córners equipo': 'baja', 'Más córners': 'baja-media', 'Tarjetas': 'baja-media',
        'Tarjetas equipo': 'baja-media', 'Jugador': 'baja (sin validar partido a partido)'}


def cargar_partidos():
    temp = {'11': '2020/21', '10': '2021/22', '9': '2022/23', '8': '2023/24', '7': '2024/25', '6': '2025/26', '5': '2026/27'}
    dfs = []
    for f in glob.glob(os.path.join(DATOS, 'SP2_*.csv')):
        k = os.path.basename(f)[4:-4]
        d = pd.read_csv(f, encoding='utf-8-sig'); d['Season'] = temp.get(k, k); dfs.append(d)
    a = pd.concat(dfs, ignore_index=True)
    a['Date'] = pd.to_datetime(a['Date'], dayfirst=True)
    a['HK'] = a.HY + a.HR; a['AK'] = a.AY + a.AR; a['Referee'] = np.nan
    return a.sort_values('Date').reset_index(drop=True)


def cargar_jugadores():
    j = pd.concat([pd.read_csv(os.path.join(DATOS, f)) for f in ['fbref_jugadores_2025_26.csv', 'fbref_jugadores_2026_27.csv']])
    g = j.groupby('jugador').agg(min=('min', 'sum'), goles=('goles', 'sum'), pk=('pk', 'sum'), sot=('tiros_puerta', 'sum'),
                                 amar=('amarillas', 'sum'), asist=('asist', 'sum'), pos=('pos', 'last'), equipo=('equipo', 'last'))
    return g


def _mat(lam, mu, rho):
    g = np.arange(dc.MAXG + 1)
    X = np.outer(poisson.pmf(g, lam), poisson.pmf(g, mu))
    X[0, 0] *= 1 - lam * mu * rho; X[0, 1] *= 1 + lam * rho; X[1, 0] *= 1 + mu * rho; X[1, 1] *= 1 - rho
    return X / X.sum()


def _lines(pmf, lines, label):
    cdf = np.cumsum(pmf); out = []
    for L in lines:
        u = cdf[int(np.floor(L))]
        out += [(f'{label}: Más de {L}', 1 - u), (f'{label}: Menos de {L}', u)]
    return out


def analizar(local, visitante, fecha=None, cuotas=None, arbitro_tarjetas_pp=None, jugadores=None):
    ref = pd.Timestamp(fecha) if fecha else pd.Timestamp.today().normalize()
    cuotas = cuotas or {}
    a = cargar_partidos(); tr = a[a.Date < ref]
    assert tr.Date.max() < ref, 'FUGA'
    avisos = [f'{t}: sin historial en SP2' for t in (local, visitante) if t not in set(tr.HomeTeam)]
    g = dc.fit(tr, ref, CFG_GOLES['xi'], CFG_GOLES['reg'])
    M0, lam0, mu0 = dc.score_matrix(g, local, visitante); rho = g['p'][-1]
    lam, mu = lam0, mu0
    tot = np.add.outer(np.arange(dc.MAXG + 1), np.arange(dc.MAXG + 1))
    if 'Goles: Más de 2.5' in cuotas and 'Goles: Menos de 2.5' in cuotas:
        po = (1 / cuotas['Goles: Más de 2.5']); pu = 1 / cuotas['Goles: Menos de 2.5']; po = po / (po + pu)
        k = brentq(lambda k: _mat(lam0 * k, mu0 * k, rho)[tot > 2].sum() - po, 0.3, 3.0)
        lam, mu = lam0 * k, mu0 * k
    M = _mat(lam, mu, rho)
    pH, pD, pA = np.tril(M, -1).sum(), np.trace(M), np.triu(M, 1).sum()
    k3 = ['1X2: Local', '1X2: Empate', '1X2: Visitante']
    if all(x in cuotas for x in k3):
        q = np.array([1 / cuotas[x] for x in k3]); q /= q.sum()
        z = PESOS_MEZCLA[0] * np.log([pH, pD, pA]) + PESOS_MEZCLA[1] * np.log(q)
        pH, pD, pA = np.exp(z) / np.exp(z).sum()
    R = [('1X2', '1X2: Local', pH), ('1X2', '1X2: Empate', pD), ('1X2', '1X2: Visitante', pA),
         ('Doble oportunidad', 'DO: 1X', pH + pD), ('Doble oportunidad', 'DO: X2', pD + pA), ('Doble oportunidad', 'DO: 12', pH + pA),
         ('Empate no válido', 'DNB: Local', pH / (pH + pA)), ('Empate no válido', 'DNB: Visitante', pA / (pH + pA))]
    ptot = np.array([M[tot == s].sum() for s in range(2 * dc.MAXG + 1)])
    R += [('Goles',) + r for r in _lines(ptot, [0.5, 1.5, 2.5, 3.5, 4.5], 'Goles')]
    bt = M[1:, 1:].sum(); R += [('Ambos marcan', 'Ambos marcan: Sí', bt), ('Ambos marcan', 'Ambos marcan: No', 1 - bt)]
    for nm, pm in [('Local', M.sum(1)), ('Visitante', M.sum(0))]:
        R += [('Goles equipo',) + r for r in _lines(pm, [0.5, 1.5, 2.5], f'Goles {nm}')]
    dif = tot * 0; I = np.arange(dc.MAXG + 1); dif = I[:, None] - I[None, :]
    R += [('Hándicap', 'Hándicap Local -1,5', M[dif >= 2].sum()), ('Hándicap', 'Hándicap Visitante +1,5', M[dif <= 1].sum()),
          ('Hándicap', 'Hándicap Visitante -1,5', M[dif <= -2].sum()), ('Hándicap', 'Hándicap Local +1,5', M[dif >= -1].sum()),
          ('Goles equipo', 'Local gana sin encajar', M[1:, 0].sum()), ('Goles equipo', 'Visitante gana sin encajar', M[0, 1:].sum())]
    cm = CountModel(**CFG_CORNERS).fit(tr, ref, 'HC', 'AC'); dcn = cm.dists(local, visitante)
    R += [('Córners',) + r for r in _lines(dcn['pmf_tot'], [7.5, 8.5, 9.5, 10.5, 11.5, 12.5], 'Córners')]
    for nm, pm in [('Local', dcn['pmf_h']), ('Visitante', dcn['pmf_a'])]:
        R += [('Córners equipo',) + r for r in _lines(pm, [3.5, 4.5, 5.5, 6.5], f'Córners {nm}')]
    J = np.outer(dcn['pmf_h'], dcn['pmf_a'])
    R += [('Más córners', 'Más córners: Local', np.tril(J, -1).sum()), ('Más córners', 'Más córners: Empate', np.trace(J)),
          ('Más córners', 'Más córners: Visitante', np.triu(J, 1).sum())]
    km = CountModel(**CFG_TARJETAS).fit(tr, ref, 'HK', 'AK'); lk_h, lk_a = km.rates(local, visitante)
    f_arb = 1.0
    if arbitro_tarjetas_pp:
        base = tr[tr.Date >= ref - pd.Timedelta(days=365)]; media = (base.HK + base.AK).mean()
        f_arb = 1 + 0.5 * (arbitro_tarjetas_pp / media - 1)
    from countmodel import count_pmf
    pk_tot = count_pmf((lk_h + lk_a) * f_arb, km.disp_total)
    R += [('Tarjetas',) + r for r in _lines(pk_tot, [2.5, 3.5, 4.5, 5.5, 6.5], 'Tarjetas')]
    for nm, l_ in [('Local', lk_h), ('Visitante', lk_a)]:
        R += [('Tarjetas equipo',) + r for r in _lines(count_pmf(l_ * f_arb, km.disp_team), [0.5, 1.5, 2.5], f'Tarjetas {nm}')]
    jug_tab = None
    if jugadores:
        JG = cargar_jugadores(); filas = []
        team_avg = {}
        for lado, eq_l in (('L', local), ('V', visitante)):
            h = tr[(tr.Season == tr.Season.max())]
            gf = pd.concat([h[h.HomeTeam == eq_l].FTHG, h[h.AwayTeam == eq_l].FTAG])
            team_avg[lado] = gf.mean() if len(gf) >= 3 else (h.FTHG.mean() + h.FTAG.mean()) / 2
        for nombre, lado, mins in jugadores:
            if nombre not in JG.index:
                avisos.append(f'Jugador sin datos FBref: {nombre}'); continue
            r = JG.loc[nombre]; pr = PRIOR_POS.get(str(r.pos)[:2], PRIOR_POS['MF'])
            esc = (lam if lado == 'L' else mu) / team_avg[lado]
            sh = lambda x, p: (x + p * K_JUG / 90) / ((r['min'] + K_JUG) / 90)
            lg = sh(r.goles, pr['g']) * esc * mins / 90; ls = sh(r.sot, pr['s']) * esc * mins / 90
            ly = sh(r.amar, pr['y']) * f_arb * mins / 90; la_ = sh(r.asist, pr['a']) * esc * mins / 90
            filas.append(dict(jugador=nombre, lado=lado, min_esp=mins, min_muestra=int(r['min']),
                              p_gol=1 - np.exp(-lg), p_2goles=1 - np.exp(-lg) * (1 + lg), p_1SoT=1 - np.exp(-ls),
                              p_2SoT=1 - np.exp(-ls) * (1 + ls), p_asist=1 - np.exp(-la_), p_tarjeta=1 - np.exp(-ly)))
            for k_, nm_ in [('p_gol', 'marca'), ('p_1SoT', '1+ tiros a puerta'), ('p_2SoT', '2+ tiros a puerta'), ('p_asist', 'asistencia'), ('p_2goles', '2+ goles')]:
                R.append(('Jugador', f'{nombre}: {nm_}', filas[-1][k_]))
        jug_tab = pd.DataFrame(filas)
    T = pd.DataFrame(R, columns=['tipo', 'mercado', 'p'])
    T['fiabilidad'] = T.tipo.map(FIAB)
    T['cuota_justa'] = 1 / T.p
    T['cuota_bwin'] = T.mercado.map(cuotas)
    T['EV_%'] = (T.p * T.cuota_bwin - 1) * 100
    info = dict(lambdas_modelo=(round(lam0, 2), round(mu0, 2)), lambdas_finales=(round(lam, 2), round(mu, 2)),
                corners_esp=(round(dcn['lam_h'], 2), round(dcn['lam_a'], 2)),
                tarjetas_esp=(round(lk_h * f_arb, 2), round(lk_a * f_arb, 2)), factor_arbitro=round(f_arb, 3),
                ultimo_dato=str(tr.Date.max().date()), avisos=avisos, jugadores=jug_tab)
    no_en_T = [k for k in cuotas if k not in set(T.mercado)]
    if no_en_T: info['avisos'].append(f'Cuotas sin mercado modelado: {no_en_T}')
    cand = T[T.cuota_bwin >= CUOTA_MIN].sort_values('p', ascending=False)
    pick = cand.iloc[0].to_dict() if len(cand) else None
    return T.sort_values('p', ascending=False).reset_index(drop=True), pick, info


ORDEN_FIAB = {'media (mezcla con mercado)': 3, 'media (calibrado a bwin O/U 2,5)': 3, 'media': 2, 'baja-media': 1}


def analizar_jornada(partidos, fecha=None):
    """partidos: lista de dicts {local, visitante, cuotas, arbitro_tarjetas_pp?, fecha?}.
    Una selección por partido; recomendación = mayor prob. entre EV >= 0, si no la más probable (sin valor)."""
    F = []
    for p in partidos:
        T, pick, info = analizar(p['local'], p['visitante'], p.get('fecha', fecha), p.get('cuotas'), p.get('arbitro_tarjetas_pp'))
        if pick:
            F.append(dict(partido=f"{p['local']} - {p['visitante']}", seleccion=pick['mercado'], p=pick['p'],
                          cuota_justa=pick['cuota_justa'], cuota_bwin=pick['cuota_bwin'], EV_pct=pick['EV_%'],
                          fiabilidad=pick['fiabilidad'], orden=ORDEN_FIAB.get(pick['fiabilidad'], 0)))
    R = pd.DataFrame(F).sort_values(['p', 'orden'], ascending=False) if F else pd.DataFrame()
    if R.empty: return R, None
    cv = R[R.EV_pct >= 0]; rec = (cv if len(cv) else R).iloc[0].to_dict()
    rec['aviso'] = None if len(cv) else 'Ninguna selección con EV >= 0: es la más probable, pero sin valor.'
    return R.reset_index(drop=True), rec
