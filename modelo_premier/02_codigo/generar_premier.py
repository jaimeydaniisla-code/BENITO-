"""Premier League -> datos.json (ligas.premier). Calendario, árbitro y alineaciones desde FotMob; modelo DCX (xG) + conteos."""
import os, sys, json, re, datetime as dt, functools, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import pandas as pd
import analizar_partido as ap
try:
    from zoneinfo import ZoneInfo; MAD = ZoneInfo('Europe/Madrid')
except Exception:
    MAD = dt.timezone.utc
DATOS = os.path.join(ROOT, 'datos.json'); E0_FILE = os.path.join(ROOT, 'modelo_premier', '01_datos', 'E0_2026-27.csv')
PMIN, PMAX = 0.42, 0.93


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read()


def descargar_e0():
    try:
        raw = get('https://www.football-data.co.uk/mmz4281/2627/E0.csv'); tmp = E0_FILE + '.tmp'; open(tmp, 'wb').write(raw)
        n_new = len(pd.read_csv(tmp, encoding='utf-8-sig').dropna(subset=['FTHG'])); n_old = len(pd.read_csv(E0_FILE, encoding='utf-8-sig').dropna(subset=['FTHG']))
        if n_new >= n_old: os.replace(tmp, E0_FILE); print(f'E0 descargado: {n_new} partidos (antes {n_old})')
        else: os.remove(tmp)
    except Exception as e:
        print('AVISO E0:', repr(e)[:150])


def coma(x):
    return str(x).replace('.', ',')

import difflib, unicodedata


def nz(t):
    return unicodedata.normalize('NFKD', str(t)).encode('ascii', 'ignore').decode().lower().replace('.', '').strip()


ALIAS = {'manchester united': 'man united', 'manchester city': 'man city', 'newcastle united': 'newcastle', 'tottenham hotspur': 'tottenham',
         'nottingham forest': "nott'm forest", 'wolverhampton wanderers': 'wolves', 'brighton & hove albion': 'brighton', 'west ham united': 'west ham',
         'leeds united': 'leeds', 'hull city': 'hull', 'ipswich town': 'ipswich', 'leicester city': 'leicester', 'norwich city': 'norwich', 'coventry city': 'coventry',
         'afc bournemouth': 'bournemouth', 'sheffield united': 'sheffield utd', 'west bromwich albion': 'west brom', 'luton town': 'luton'}


def fm_get(u):
    import re
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'})
    h = urllib.request.urlopen(req, timeout=40).read().decode('utf-8', 'ignore')
    return json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S).group(1))['props']['pageProps']


def fm_calendario(equipos, hoy):
    """Calendario de Premier desde FotMob. Devuelve filas con equipos ya mapeados a los nombres de football-data."""
    allm = fm_get('https://www.fotmob.com/leagues/47/overview/premier-league')['fixtures']['allMatches']
    por = {nz(e): e for e in equipos}
    def mapa(n):
        k = ALIAS.get(nz(n), nz(n))
        if k in por: return por[k]
        b = difflib.get_close_matches(k, list(por), n=1, cutoff=0.6)
        return por[b[0]] if b else None
    out, sin = [], set()
    for f in allm:
        st = f.get('status', {})
        if st.get('finished') or st.get('cancelled'): continue
        ko = dt.datetime.fromisoformat(st['utcTime'].replace('Z', '+00:00')).astimezone(MAD)
        if pd.Timestamp(ko.date()) < hoy: continue
        h, a = mapa(f['home']['name']), mapa(f['away']['name'])
        if not h or not a:
            sin.add((f['home']['name'], f['away']['name'])); continue
        out.append({'h': h, 'a': a, 'ko': ko, 'ronda': f.get('round'), 'url': f['pageUrl'].split('#')[0]})
    if sin: print('AVISO FotMob Premier sin casar:', sorted(sin)[:6])
    return sorted(out, key=lambda r: r['ko'])


def fm_detalle(f, ahora, horas=120):
    if f['ko'] > ahora + dt.timedelta(hours=horas): return None, None
    try:
        g = fm_get('https://www.fotmob.com' + f['url'])['content']
    except Exception as e:
        print('AVISO FotMob partido', f['h'], f['a'], repr(e)[:90]); return None, None
    ref = (((g.get('matchFacts') or {}).get('infoBox') or {}).get('Referee') or {}).get('text') or None
    L = g.get('lineup') or {}; ali = None
    if L.get('homeTeam') and L.get('awayTeam'):
        baj = lambda t: ', '.join(x['name'].split(' ')[-1] for x in (t.get('unavailable') or [])[:5])
        fh, fa = L['homeTeam'].get('formation') or '?', L['awayTeam'].get('formation') or '?'
        ok = fh != '?' and fa != '?' and L['homeTeam'].get('starters') and L['awayTeam'].get('starters')
        ali = (f"{'confirmadas' if (L.get('lineupType') not in ('predicted', 'lastStarting11', None) and ok) else 'NO oficiales (probables)'}: {fh} / {fa}") if ok else 'sin confirmar'
        bl, bv = baj(L['homeTeam']), baj(L['awayTeam'])
        if bl or bv: ali += f" · Bajas: {f['h']}: {bl or '—'}; {f['a']}: {bv or '—'}"
    return ref, ali



def seleccion(T, h, a):
    """Convierte la tabla del modelo en la lista de selecciones de la app: [texto, categoría, prob, fiabilidad]."""
    out = []
    fijo = {'1X2: Local': (f'Gana {h}', 'res', 2), '1X2: Visitante': (f'Gana {a}', 'res', 2),
            'DO: 1X': (f'{h} o empate', 'res', 2), 'DO: X2': (f'Empate o {a}', 'res', 2), 'DO: 12': ('No hay empate', 'res', 2),
            'DNB: Local': (f'{h} (empate no válido)', 'res', 2), 'DNB: Visitante': (f'{a} (empate no válido)', 'res', 2),
            'Ambos marcan: Sí': ('Ambos marcan: Sí', 'gol', 1), 'Ambos marcan: No': ('Ambos marcan: No', 'gol', 1),
            'Hándicap Local -1,5 (gana por 2+)': (f'{h} gana por 2 o más', 'res', 2),
            'Hándicap Visitante -1,5 (gana por 2+)': (f'{a} gana por 2 o más', 'res', 2),
            'Hándicap Visitante +1,5': (f'{a} +1,5 (no pierde por 2)', 'res', 2),
            'Hándicap Local +1,5': (f'{h} +1,5 (no pierde por 2)', 'res', 2),
            'Local gana sin encajar': (f'{h} gana sin encajar', 'gol', 2), 'Visitante gana sin encajar': (f'{a} gana sin encajar', 'gol', 2),
            'Más córners: Local': (f'Más córners: {h}', 'cor', 2), 'Más córners: Visitante': (f'Más córners: {a}', 'cor', 2)}
    cat = {'Goles': 'gol', 'Córners': 'cor', 'Tarjetas': 'tar'}
    fia_tot = {'Goles': 1, 'Córners': 0, 'Tarjetas': 1}
    fia_eq = {'Goles': 2, 'Córners': 2, 'Tarjetas': 1}
    for _, r in T.iterrows():
        p = float(r.p_final)
        if p < PMIN or p > PMAX:
            continue
        m = r.mercado
        if m in fijo:
            t, c, f = fijo[m]
        else:
            g = re.match(r'^(Goles|Córners|Tarjetas)( Local| Visitante)?: (Más|Menos) de ([\d.]+)$', m)
            if not g:
                continue
            k, eq, mm, L = g.groups()
            nom = {' Local': h, ' Visitante': a}.get(eq)
            t = f'{k}{" " + nom if nom else ""}: {mm.lower()} de {coma(L)}'
            c, f = cat[k], (fia_eq[k] if nom else fia_tot[k])
        out.append([t, c, round(p, 3), f])
    out.sort(key=lambda s: -s[2])
    return out


def main():
    descargar_e0()
    ahora = dt.datetime.now(MAD); hoy = pd.Timestamp(ahora.date())
    app = json.load(open(DATOS, encoding='utf-8')); lig = app.setdefault('ligas', {})
    hist = ap.load_matches(); ult = hist.Date.max()
    equipos = sorted(set(hist.HomeTeam) | set(hist.AwayTeam))
    meta = {'act': ahora.strftime('%d/%m/%Y %H:%M'), 'datos': ult.strftime('%d/%m/%Y')}
    try:
        fx = fm_calendario(equipos, hoy)
    except Exception as e:
        print('AVISO FotMob calendario Premier:', repr(e)[:150]); return
    if not fx:
        lig['premier'] = {'nombre': 'Premier', 'jor': [], 'meta': meta}; print('Sin partidos próximos de Premier'); json.dump(app, open(DATOS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':')); return
    rondas = []
    for r in fx:
        if r['ronda'] not in rondas: rondas.append(r['ronda'])
    jor, narb, nali = [], 0, 0
    for ronda in rondas[:3]:
        ms = []
        for r in [x for x in fx if x['ronda'] == ronda]:
            arb, ali = fm_detalle(r, ahora)
            try:
                T, pick, info = ap.analizar(r['h'], r['a'], None, hoy)   # árbitro solo informativo (nombres de FotMob ≠ football-data)
            except Exception as e:
                print('AVISO modelo', r['h'], r['a'], repr(e)[:120]); continue
            narb += bool(arb); nali += bool(ali)
            ms.append({'h': r['h'], 'a': r['a'], 'd': r['ko'].strftime('%Y-%m-%d'), 't': r['ko'].strftime('%H:%M'), 'arb': arb, 'ali': ali,
                       'g': [float(x) for x in info['lambda_goles']], 'c': [float(x) for x in info['corners_esperados']], 'k': [float(x) for x in info['tarjetas_esperadas']],
                       's': seleccion(T, r['h'], r['a'])})
        if ms:
            try: jn = int(ronda)
            except Exception: jn = len(jor) + 1
            jor.append({'j': jn, 'ms': ms})
    lig['premier'] = {'nombre': 'Premier', 'jor': jor, 'meta': meta}
    print(f'Premier: {sum(len(j["ms"]) for j in jor)} partidos en {len(jor)} jornadas; {narb} con árbitro, {nali} con alineación. Datos hasta {ult.date()}')
    json.dump(app, open(DATOS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    main()
