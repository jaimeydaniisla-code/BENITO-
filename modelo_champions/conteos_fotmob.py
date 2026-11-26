"""Córners y tarjetas para competiciones UEFA (Champions / Europa League) con las estadísticas de FotMob de esta temporada.
Por equipo: córners a favor/en contra y tarjetas propias/del rival en los partidos ya jugados de la competición.
Medias encogidas hacia la media de la competición (K partidos ficticios) y Poisson independiente.
Muestra pequeña (4-6 partidos por equipo): se marca como poco fiable (fiabilidad 0). Si bwin cotiza la línea,
modelo_cuotas/generar_cuotas.py --aplicar-solo mezcla 50 % modelo + 50 % mercado sin margen.
Uso: python modelo_champions/conteos_fotmob.py europa"""
import os, re, sys, json, time, datetime as dt
import numpy as np
from scipy.stats import poisson
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
from generar_champions import COMP, fm_get
DATOS = os.path.join(ROOT, 'datos.json')
K = 4                      # partidos ficticios de la media de la competición (encogimiento)
PMIN, PMAX = 0.42, 0.93


def estad(content):
    v = {}
    for grp in (((content.get('stats') or {}).get('Periods') or {}).get('All') or {}).get('stats') or []:
        for it in grp.get('stats') or []:
            k, x = it.get('key'), it.get('stats')
            if k in ('corners', 'yellow_cards', 'red_cards') and k not in v and isinstance(x, list) and len(x) == 2:
                try: v[k] = [int(x[0]), int(x[1])]
                except Exception: pass
    if 'corners' not in v or 'yellow_cards' not in v: return None
    r = v.get('red_cards', [0, 0])
    return {'cor': v['corners'], 'tar': [v['yellow_cards'][0] + r[0], v['yellow_cards'][1] + r[1]]}


def coma(x):
    return str(x).replace('.', ',')


def main(clave):
    lid, slug, nombre = COMP[clave]
    cache_f = os.path.join(HERE, f'conteos_{clave}.json')
    try: cache = json.load(open(cache_f, encoding='utf-8'))
    except Exception: cache = {}
    allm = fm_get(f'https://www.fotmob.com/leagues/{lid}/overview/{slug}')['fixtures']['allMatches']
    nuevos = 0
    for f in allm:
        mid = str(f.get('id'))
        if not f['status'].get('finished') or mid in cache or not f.get('pageUrl'): continue
        try:
            e = estad(fm_get('https://www.fotmob.com' + f['pageUrl'].split('#')[0])['content'])
            if e: cache[mid] = {'h': f['home']['name'], 'a': f['away']['name'], **e}; nuevos += 1
            time.sleep(0.4)
        except Exception as ex:
            print('AVISO FotMob', f['home']['name'], f['away']['name'], repr(ex)[:80])
    json.dump(cache, open(cache_f, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    P = list(cache.values())
    if len(P) < 20:
        print(nombre, ': pocos partidos con estadísticas', len(P)); return
    # medias de la competición
    mch = np.mean([x['cor'][0] for x in P]); mca = np.mean([x['cor'][1] for x in P])
    mth = np.mean([x['tar'][0] for x in P]); mta = np.mean([x['tar'][1] for x in P])
    mc, mt = (mch + mca) / 2, (mth + mta) / 2
    eq = {}
    for x in P:
        for lado, yo, el in ((0, x['h'], x['a']), (1, x['a'], x['h'])):
            d = eq.setdefault(yo, {'n': 0, 'cf': 0, 'ca': 0, 'tf': 0, 'ta': 0})
            d['n'] += 1; d['cf'] += x['cor'][lado]; d['ca'] += x['cor'][1 - lado]; d['tf'] += x['tar'][lado]; d['ta'] += x['tar'][1 - lado]
    def r(t, k, m):
        d = eq.get(t)
        if not d: return 1.0, 0
        return (d[k] + K * m) / (d['n'] + K) / m, d['n']
    app = json.load(open(DATOS, encoding='utf-8')); L = app.get('ligas', {}).get(clave)
    if not L: print('sin', clave, 'en datos.json'); return
    hechos = 0
    for j in L.get('jor', []):
        for m in j['ms']:
            h, a = m['h'], m['a']
            ah, nh = r(h, 'cf', mc); da, na = r(a, 'ca', mc); aa, _ = r(a, 'cf', mc); dh, _ = r(h, 'ca', mc)
            if min(nh, na) < 2: continue
            lch, lca = mch * ah * da, mca * aa * dh
            th, _ = r(h, 'tf', mt); pa_, _ = r(a, 'ta', mt); ta_, _ = r(a, 'tf', mt); ph, _ = r(h, 'ta', mt)
            lth, lta = mth * th * pa_, mta * ta_ * ph
            sel = []
            def lineas(base, lam, lines, cat):
                for x in lines:
                    p = 1 - poisson.cdf(int(x), lam)
                    sel.append([f'{base}: más de {coma(x)}', cat, p, 0]); sel.append([f'{base}: menos de {coma(x)}', cat, 1 - p, 0])
            lineas('Córners', lch + lca, [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5], 'cor')
            lineas(f'Córners {h}', lch, [2.5, 3.5, 4.5, 5.5, 6.5], 'cor'); lineas(f'Córners {a}', lca, [2.5, 3.5, 4.5, 5.5, 6.5], 'cor')
            lineas('Tarjetas', lth + lta, [2.5, 3.5, 4.5, 5.5, 6.5], 'tar')
            lineas(f'Tarjetas {h}', lth, [0.5, 1.5, 2.5, 3.5], 'tar'); lineas(f'Tarjetas {a}', lta, [0.5, 1.5, 2.5, 3.5], 'tar')
            k = np.arange(30); M = np.outer(poisson.pmf(k, lch), poisson.pmf(k, lca)); i, jj = np.indices(M.shape)
            sel.append([f'Más córners: {h}', 'cor', float(M[i > jj].sum()), 0]); sel.append([f'Más córners: {a}', 'cor', float(M[i < jj].sum()), 0])
            sel = [[t, c, round(float(p), 3), f] for t, c, p, f in sel if PMIN <= p <= PMAX]
            m['s'] = [s for s in (m.get('s') or []) if s[1] not in ('cor', 'tar')] + sel
            m['s'].sort(key=lambda s: -s[2])
            m['c'] = [round(lch, 2), round(lca, 2)]; m['k'] = [round(lth, 2), round(lta, 2)]; m['nct'] = [nh, na]
            hechos += 1
    if hechos:
        L['aviso'] = re.sub(r'\s*Sin córners ni tarjetas\.', '', L.get('aviso') or '') + \
            f' Córners y tarjetas: estadísticas FotMob de esta {nombre} ({len(P)} partidos, 4-6 por equipo): POCO FIABLES.'
    json.dump(app, open(DATOS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f'{nombre}: {len(P)} partidos con estadísticas ({nuevos} nuevos) | córners/partido {mch + mca:.2f} | tarjetas/partido {mth + mta:.2f} | {hechos} partidos con córners y tarjetas')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'europa')
