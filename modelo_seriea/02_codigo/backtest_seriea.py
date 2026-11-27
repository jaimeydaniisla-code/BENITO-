"""Backtest Serie A sin mirar el futuro (reajuste semanal, solo datos anteriores), temporadas 2023-24 en adelante.
- 1X2: logloss del modelo (DC con goles) vs cuota de cierre media del mercado (AvgC*, si no Avg*/B365*).
- Más/menos 2,5 goles: logloss modelo vs mercado de cierre.
- Córners y tarjetas: logloss modelo vs media de la liga (no hay cuotas históricas de córners/tarjetas).
Escribe el resumen en ../03_resultados/backtest.json"""
import os, json
import numpy as np
import pandas as pd
from matches import load_matches, promoted_in
from dcx import DCX, probs_1x2, MAXG
from backtest_counts import prep, run, evaluate
from analizar_partido import CFG_GOLES, CFG_CORNERS, CFG_TARJETAS

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '03_resultados')


def col(df, *names):
    for n in names:
        if all(c in df and df[c].notna().mean() > 0.9 for c in n): return n
    return None


def goles(first=2023):
    m = load_matches(); test = m[m.season >= first].copy(); test['wk'] = test.Date.dt.to_period('W-MON')
    c1 = col(m, ('AvgCH', 'AvgCD', 'AvgCA'), ('AvgH', 'AvgD', 'AvgA'), ('B365H', 'B365D', 'B365A'))
    c2 = col(m, ('AvgC>2.5', 'AvgC<2.5'), ('Avg>2.5', 'Avg<2.5'), ('B365>2.5', 'B365<2.5'))
    R = []
    for wk, g in test.groupby('wk', sort=True):
        ref = g.Date.min(); tr = m[m.Date < ref]
        mod = DCX(**CFG_GOLES).fit(tr, ref, promoted=promoted_in(m, g.season.iloc[0]))   # qué equipos juegan la temporada se sabe desde su inicio
        for _, r in g.iterrows():
            try: M, _, _ = mod.score_matrix(r.HomeTeam, r.AwayTeam)
            except Exception: continue
            pH, pD, pA = probs_1x2(M)
            tot = np.array([np.fliplr(M).diagonal(MAXG - i).sum() for i in range(2 * MAXG + 1)])
            po = 1 - tot[:3].sum()
            o = [r[c] for c in c1]; q = 1 / np.array(o, float); q = q / q.sum()
            o2 = [r[c] for c in c2]; q2 = 1 / np.array(o2, float); q2 = q2[0] / q2.sum()
            y = r.res; ov = (r.FTHG + r.FTAG) > 2.5
            R.append(dict(season=r.season, ll_mod=-np.log([pH, pD, pA][y]), ll_mkt=-np.log(q[y]),
                          ll2_mod=-np.log(po if ov else 1 - po), ll2_mkt=-np.log(q2 if ov else 1 - q2),
                          ll_base=-np.log([0.43, 0.27, 0.30][y])))
    R = pd.DataFrame(R)
    return {'partidos': len(R), 'cuotas': [c1, c2], '1X2_modelo': round(R.ll_mod.mean(), 4), '1X2_mercado': round(R.ll_mkt.mean(), 4),
            '1X2_sin_saber_nada': round(R.ll_base.mean(), 4), 'OU25_modelo': round(R.ll2_mod.mean(), 4), 'OU25_mercado': round(R.ll2_mkt.mean(), 4),
            'por_temporada': R.groupby('season')[['ll_mod', 'll_mkt']].mean().round(4).to_dict('index')}


def main():
    os.makedirs(OUT, exist_ok=True); res = {}
    d = prep()
    print('Partidos I1:', len(d), 'temporadas', sorted(d.season.unique()))
    for nombre, (h, a), cfg, lines in (('corners', ('HC', 'AC'), CFG_CORNERS, [8.5, 9.5, 10.5]), ('tarjetas', ('HK', 'AK'), CFG_TARJETAS, [3.5, 4.5, 5.5])):
        P = run(d, h, a, first=2023, **cfg); e = evaluate(P, lines); e['partidos'] = len(P)
        e['media_obs'] = round(float(P.obs_tot.mean()), 2)
        res[nombre] = {k: (round(float(v), 4) if isinstance(v, (float, np.floating)) else v) for k, v in e.items()}
        print(nombre, res[nombre])
    res['goles'] = goles(); print('goles', res['goles'])
    json.dump(res, open(os.path.join(OUT, 'backtest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
