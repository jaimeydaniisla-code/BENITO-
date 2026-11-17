"""Selecciones -> datos.json (ligas.selecciones). Lee partidos_proximos.csv, descarga resultados y calcula."""
import os, sys, json, datetime as dt, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from selecciones import Sel, mercados
try:
    from zoneinfo import ZoneInfo; MAD = ZoneInfo('Europe/Madrid')
except Exception:
    MAD = dt.timezone.utc
CSV = os.path.join(HERE, 'resultados_selecciones.csv'); DATOS = os.path.join(ROOT, 'datos.json')
PMIN, PMAX = 0.42, 0.93
ES = {'Denmark': 'Dinamarca', 'Norway': 'Noruega', 'Spain': 'España', 'England': 'Inglaterra', 'Germany': 'Alemania', 'Netherlands': 'Países Bajos',
      'France': 'Francia', 'Italy': 'Italia', 'Portugal': 'Portugal', 'Belgium': 'Bélgica', 'Croatia': 'Croacia', 'Turkey': 'Turquía', 'Switzerland': 'Suiza',
      'Austria': 'Austria', 'Poland': 'Polonia', 'Sweden': 'Suecia', 'Scotland': 'Escocia', 'Czech Republic': 'Rep. Checa', 'Brazil': 'Brasil',
      'Argentina': 'Argentina', 'Uruguay': 'Uruguay', 'Colombia': 'Colombia', 'Mexico': 'México', 'United States': 'EE. UU.', 'Japan': 'Japón', 'Hungary': 'Hungría', 'Northern Ireland': 'Irlanda del Norte', 'Ukraine': 'Ucrania', 'Georgia': 'Georgia', 'Israel': 'Israel', 'Bosnia and Herzegovina': 'Bosnia', 'Romania': 'Rumanía', 'Republic of Ireland': 'Irlanda', 'Kosovo': 'Kosovo', 'Wales': 'Gales', 'South Korea': 'Corea del Sur'}


def descargar():
    try:
        raw = urllib.request.urlopen(urllib.request.Request('https://raw.githubusercontent.com/martj42/international_results/master/results.csv', headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read()
        tmp = CSV + '.tmp'; open(tmp, 'wb').write(raw)
        if len(pd.read_csv(tmp)) >= len(pd.read_csv(CSV)):
            os.replace(tmp, CSV)
        else:
            os.remove(tmp)
    except Exception as e:
        print('AVISO resultados:', repr(e)[:120])


def seleccion(mk, h, a):
    H, A = ES.get(h, h), ES.get(a, a); c = lambda L: str(L).replace('.', ',')
    d = {'1X2: Local': (f'Gana {H}', 'res', 2), '1X2: Visitante': (f'Gana {A}', 'res', 2), 'DO: 1X': (f'{H} o empate', 'res', 2), 'DO: X2': (f'Empate o {A}', 'res', 2),
         'DO: 12': ('No hay empate', 'res', 2), 'DNB: Local': (f'{H} (empate no válido)', 'res', 2), 'DNB: Visitante': (f'{A} (empate no válido)', 'res', 2),
         'BTTS Sí': ('Ambos marcan: Sí', 'gol', 1), 'BTTS No': ('Ambos marcan: No', 'gol', 1), 'H-1,5 L': (f'{H} gana por 2 o más', 'res', 2),
         'H-1,5 V': (f'{A} gana por 2 o más', 'res', 2), 'H+1,5 V': (f'{A} +1,5 (no pierde por 2)', 'res', 2), 'H+1,5 L': (f'{H} +1,5 (no pierde por 2)', 'res', 2),
         'Local gana sin encajar': (f'{H} gana sin encajar', 'gol', 2), 'Visitante gana sin encajar': (f'{A} gana sin encajar', 'gol', 2)}
    out = []
    for k, p in mk.items():
        if k in d:
            t, cat, f = d[k]
        else:
            q, L = k[0], float(k[2:]); nom = {'T': '', 'L': f'{H}: ', 'V': f'{A}: '}[q]
            for mm, pp in (('más', p), ('menos', 1 - p)):
                if PMIN <= pp <= PMAX:
                    out.append([('Goles: ' if q == 'T' else 'Goles ' + nom) + f'{mm} de {c(L)}', 'gol', round(float(pp), 3), 1 if q == 'T' else 2])
            continue
        if PMIN <= p <= PMAX:
            out.append([t, cat, round(float(p), 3), f])
    out.sort(key=lambda s: -s[2]); return out


def main():
    descargar()
    ahora = dt.datetime.now(MAD); hoy = pd.Timestamp(ahora.date())
    res = pd.read_csv(CSV, parse_dates=['date']); ult = res.date.max()
    fx = pd.read_csv(os.path.join(HERE, 'partidos_proximos.csv'), parse_dates=['fecha']).dropna(subset=['local', 'visitante'])
    fx = fx[fx.fecha >= hoy].sort_values('fecha')
    app = json.load(open(DATOS, encoding='utf-8')); lig = app.setdefault('ligas', {})
    meta = {'act': ahora.strftime('%d/%m/%Y %H:%M'), 'datos': ult.strftime('%d/%m/%Y')}
    aviso = 'Modelo de selecciones sin validar contra bwin y sin córners ni tarjetas. Calendario manual: se añaden partidos en partidos_proximos.csv.'
    if fx.empty:
        lig['selecciones'] = {'nombre': 'Selecciones', 'jor': [], 'meta': meta, 'aviso': 'No hay partidos de selecciones próximos cargados (la ventana FIFA acaba el 17/11; siguiente en marzo).'}
    else:
        m = Sel().fit(res, hoy + pd.Timedelta(days=1))
        grupos, prev = [], None
        for _, r in fx.iterrows():
            if prev is None or (r.fecha - prev).days > 3:
                grupos.append([])
            grupos[-1].append(r); prev = r.fecha
        jor = []
        for gi, g in enumerate(grupos[:3]):
            ms = []
            for r in g:
                h, a = r.local, r.visitante
                if h not in m.idx or a not in m.idx or m.ult.get(h, 0) < 8 or m.ult.get(a, 0) < 8:
                    print('AVISO selección sin datos suficientes:', h, a); continue
                neu = str(r.neutral).upper() == 'TRUE'; l1, l2 = m.lambdas(h, a, neu); M = m.matriz(l1, l2)
                ms.append({'h': ES.get(h, h), 'a': ES.get(a, a), 'd': r.fecha.strftime('%Y-%m-%d'), 't': '' if pd.isna(r.hora) else str(r.hora),
                           'arb': None, 'ali': None, 'g': [round(l1, 2), round(l2, 2)], 'c': [None, None], 'k': [None, None], 's': seleccion(mercados(M), h, a)})
            if ms:
                jor.append({'j': gi + 1, 'ms': ms})
        lig['selecciones'] = {'nombre': 'Selecciones', 'jor': jor, 'meta': meta, 'aviso': aviso}
        print('Selecciones:', sum(len(j['ms']) for j in jor), 'partidos; rho', round(m.rho, 3), 'datos hasta', ult.date())
    json.dump(app, open(DATOS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    main()
