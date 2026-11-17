"""Segunda División: calendario (football-data.co.uk/fixtures.csv) + modelo SP2 -> datos.json (ligas.segunda)."""
import os, sys, io, json, re, datetime as dt, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import pandas as pd
import analizar_partido as ap
try:
    from zoneinfo import ZoneInfo
    MAD, UK = ZoneInfo('Europe/Madrid'), ZoneInfo('Europe/London')
except Exception:
    MAD = UK = dt.timezone.utc
DATOS = os.path.join(ROOT, 'datos.json')
SP2_FILE = os.path.join(ROOT, 'modelo_segunda', '01_datos', 'SP2_5.csv')
PMIN, PMAX = 0.42, 0.93
BONITO = {'Sp Gijon': 'Sporting', 'Ath Bilbao': 'Athletic B', 'Sociedad B': 'Real Sociedad B', 'La Coruna': 'Deportivo'}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read()


def descargar_sp2():
    try:
        raw = get('https://www.football-data.co.uk/mmz4281/2627/SP2.csv')
        tmp = SP2_FILE + '.tmp'; open(tmp, 'wb').write(raw)
        n_new = len(pd.read_csv(tmp, encoding='utf-8-sig').dropna(subset=['FTHG']))
        n_old = len(pd.read_csv(SP2_FILE, encoding='utf-8-sig').dropna(subset=['FTHG']))
        if n_new >= n_old:
            os.replace(tmp, SP2_FILE); print(f'SP2 descargado: {n_new} partidos (antes {n_old})')
        else:
            os.remove(tmp)
    except Exception as e:
        print('AVISO SP2:', repr(e)[:150])


def coma(x):
    return str(x).replace('.', ',')


def seleccion(T, h, a):
    fijo = {'1X2: Local': (f'Gana {h}', 'res', 2), '1X2: Visitante': (f'Gana {a}', 'res', 2),
            'DO: 1X': (f'{h} o empate', 'res', 2), 'DO: X2': (f'Empate o {a}', 'res', 2), 'DO: 12': ('No hay empate', 'res', 2),
            'DNB: Local': (f'{h} (empate no válido)', 'res', 2), 'DNB: Visitante': (f'{a} (empate no válido)', 'res', 2),
            'Ambos marcan: Sí': ('Ambos marcan: Sí', 'gol', 1), 'Ambos marcan: No': ('Ambos marcan: No', 'gol', 1),
            'Hándicap Local -1,5': (f'{h} gana por 2 o más', 'res', 2), 'Hándicap Visitante -1,5': (f'{a} gana por 2 o más', 'res', 2),
            'Hándicap Visitante +1,5': (f'{a} +1,5 (no pierde por 2)', 'res', 2), 'Hándicap Local +1,5': (f'{h} +1,5 (no pierde por 2)', 'res', 2),
            'Local gana sin encajar': (f'{h} gana sin encajar', 'gol', 2), 'Visitante gana sin encajar': (f'{a} gana sin encajar', 'gol', 2),
            'Más córners: Local': (f'Más córners: {h}', 'cor', 2), 'Más córners: Visitante': (f'Más córners: {a}', 'cor', 2)}
    cat = {'Goles': 'gol', 'Córners': 'cor', 'Tarjetas': 'tar'}; ft = {'Goles': 1, 'Córners': 0, 'Tarjetas': 1}; fe = {'Goles': 2, 'Córners': 2, 'Tarjetas': 1}
    out = []
    for _, r in T.iterrows():
        p = float(r.p)
        if p < PMIN or p > PMAX:
            continue
        m = r.mercado
        if m in fijo:
            t, c, f = fijo[m]
        else:
            g = re.match(r'^(Goles|Córners|Tarjetas)( Local| Visitante)?: (Más|Menos) de ([\d.]+)$', m)
            if not g:
                continue
            k, eq, mm, L = g.groups(); nom = {' Local': h, ' Visitante': a}.get(eq)
            t = f'{k}{" " + nom if nom else ""}: {mm.lower()} de {coma(L)}'; c, f = cat[k], (fe[k] if nom else ft[k])
        out.append([t, c, round(p, 3), f])
    out.sort(key=lambda s: -s[2]); return out


def main():
    descargar_sp2()
    ahora = dt.datetime.now(MAD); hoy = pd.Timestamp(ahora.date())
    app = json.load(open(DATOS, encoding='utf-8')); lig = app.setdefault('ligas', {})
    try:
        fx = pd.read_csv(io.BytesIO(get('https://www.football-data.co.uk/fixtures.csv')), encoding='latin-1')
        fx.columns = [str(c).replace('\ufeff', '').replace('ï»¿', '').strip() for c in fx.columns]
        print('fixtures:', len(fx), 'filas; ligas:', sorted(fx.Div.dropna().unique())[:12])
        fx = fx[fx.Div == 'SP2'].dropna(subset=['HomeTeam', 'AwayTeam']).copy()
        print('SP2 en fixtures:', len(fx), 'fechas:', sorted(fx.Date.astype(str).unique())[:6])
    except Exception as e:
        print('AVISO fixtures.csv:', repr(e)[:150]); return
    fx['F'] = pd.to_datetime(fx.Date, dayfirst=True); fx = fx[fx.F >= hoy].sort_values(['F', 'Time'])
    hist = pd.read_csv(SP2_FILE, encoding='utf-8-sig').dropna(subset=['FTHG'])
    jug = max(pd.concat([hist.HomeTeam, hist.AwayTeam]).value_counts().max(), 0)
    ult = pd.to_datetime(hist.Date, dayfirst=True).max()
    if fx.empty:
        print('Sin partidos próximos de SP2 en fixtures.csv'); lig['segunda'] = {'nombre': 'Segunda', 'jor': [], 'meta': {'act': ahora.strftime('%d/%m/%Y %H:%M'), 'datos': ult.strftime('%d/%m/%Y')}}
    else:
        # jornadas: grupos de fechas separados por más de 3 días
        grupos, prev, n = [], None, 0
        for _, r in fx.iterrows():
            if prev is None or (r.F - prev).days > 3:
                n += 1; grupos.append([])
            grupos[-1].append(r); prev = r.F
        jor = []
        for gi, g in enumerate(grupos[:3]):
            ms = []
            for r in g:
                t = ''
                if isinstance(r.get('Time'), str) and ':' in r.Time:
                    hh, mm = map(int, r.Time.split(':')[:2])
                    t = dt.datetime(r.F.year, r.F.month, r.F.day, hh, mm, tzinfo=UK).astimezone(MAD).strftime('%H:%M')
                h, a = BONITO.get(r.HomeTeam, r.HomeTeam), BONITO.get(r.AwayTeam, r.AwayTeam)
                try:
                    T, pick, info = ap.analizar(r.HomeTeam, r.AwayTeam, hoy)
                except Exception as e:
                    print('AVISO modelo', r.HomeTeam, r.AwayTeam, repr(e)[:120]); continue
                ms.append({'h': h, 'a': a, 'd': r.F.strftime('%Y-%m-%d'), 't': t, 'arb': None, 'ali': None,
                           'g': list(info['lambdas_finales']), 'c': list(info['corners_esp']), 'k': list(info['tarjetas_esp']),
                           's': seleccion(T, h, a)})
            if ms:
                jor.append({'j': jug + 1 + gi, 'ms': ms})
        lig['segunda'] = {'nombre': 'Segunda', 'jor': jor, 'meta': {'act': ahora.strftime('%d/%m/%Y %H:%M'), 'datos': ult.strftime('%d/%m/%Y')}}
        print(f'Segunda: {sum(len(j["ms"]) for j in jor)} partidos en {len(jor)} jornadas. Datos hasta {ult.date()}')
    json.dump(app, open(DATOS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    main()
