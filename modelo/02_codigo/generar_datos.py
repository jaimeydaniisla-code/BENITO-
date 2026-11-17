"""Robot de la app Benitooo: recalcula las probabilidades con el modelo y escribe datos.json.
Se ejecuta solo (GitHub Actions). Todo lo opcional falla en silencio: si algo no responde, se mantiene lo anterior.
  1) descarga el SP1 actual de football-data.co.uk (resultados nuevos)
  2) recalcula, con datos hasta hoy, los partidos que aún no se han jugado
  3) si hay clave APIFOOTBALL_KEY: horarios, árbitro designado y alineaciones (API-Football, plan gratis 100/día)
"""
import os, sys, json, re, functools, unicodedata, difflib, datetime as dt
import urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
os.environ['LALIGA_DATA'] = os.path.join(ROOT, 'modelo', '01_datos', 'historico') + os.sep
sys.path.insert(0, HERE)
import pandas as pd
import analizar_partido as ap
try:
    from zoneinfo import ZoneInfo
    MAD = ZoneInfo('Europe/Madrid')
except Exception:
    MAD = dt.timezone(dt.timedelta(hours=1))
ap._fit_all = functools.lru_cache(maxsize=2)(ap._fit_all)   # el modelo se ajusta una sola vez

SP1_URL = 'https://www.football-data.co.uk/mmz4281/2627/SP1.csv'
SP1_FILE = os.path.join(ROOT, 'modelo', '01_datos', 'SP1_2026-27.csv')
DATOS = os.path.join(ROOT, 'datos.json')
PMIN, PMAX = 0.42, 0.93   # rango de probabilidad que se lista (igual que la app anterior; por encima de 93 % la cuota es ~1,07 y no sirve)


def descargar_sp1():
    try:
        req = urllib.request.Request(SP1_URL, headers={'User-Agent': 'Mozilla/5.0'})
        raw = urllib.request.urlopen(req, timeout=60).read()
        tmp = SP1_FILE + '.tmp'
        open(tmp, 'wb').write(raw)
        n_new = len(pd.read_csv(tmp, encoding='utf-8-sig').dropna(subset=['FTHG']))
        n_old = len(pd.read_csv(SP1_FILE, encoding='utf-8-sig').dropna(subset=['FTHG']))
        if n_new >= n_old:
            os.replace(tmp, SP1_FILE); print(f'SP1 descargado: {n_new} partidos (antes {n_old})')
        else:
            os.remove(tmp); print('SP1 descargado con menos partidos: se mantiene el anterior')
    except Exception as e:
        print('AVISO: no se pudo descargar SP1:', repr(e)[:150])


def coma(x):
    return str(x).replace('.', ',')


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


# ---------------- API-Football (opcional) ----------------
KEY = os.environ.get('APIFOOTBALL_KEY', '').strip()
ALIAS_API = {'athletic club': 'athletic', 'real betis': 'betis', 'celta vigo': 'celta', 'rayo vallecano': 'rayo',
             'atletico madrid': 'atletico', 'deportivo la coruna': 'deportivo', 'racing santander': 'racing',
             'deportivo alaves': 'alaves', 'rcd espanyol': 'espanyol', 'ud las palmas': 'las palmas', 'santander': 'racing', 'atleti': 'atletico', 'dep la coruna': 'deportivo', 'la coruna': 'deportivo', 'sevilla fc': 'sevilla', 'alaves': 'alaves'}


def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower().strip()
    return ALIAS_API.get(s, s)


def api(path, **params):
    url = 'https://v3.football.api-sports.io/' + path + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'x-apisports-key': KEY, 'User-Agent': 'benitooo'})
    j = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    if j.get('errors'):
        raise RuntimeError(str(j['errors'])[:200])
    return j.get('response', [])


def casar(ours, name):
    n = norm(name); best = difflib.get_close_matches(n, list(ours), n=1, cutoff=0.6)
    return ours[best[0]] if best else None


def aplicar_api(jor, ahora):
    if not KEY:
        print('Sin APIFOOTBALL_KEY: horarios, árbitro y alineaciones se mantienen.'); return
    try:
        fx = api('fixtures', league=140, season=2026)
    except Exception as e:
        print('AVISO API fixtures:', repr(e)[:200]); return
    idx = {}
    for j in jor:
        for m in j['ms']:
            idx[(norm(m['h']), norm(m['a']))] = m
    ours = {k[0]: k[0] for k in idx} | {k[1]: k[1] for k in idx}
    nlin = 0
    for f in fx:
        h = casar(ours, f['teams']['home']['name']); a = casar(ours, f['teams']['away']['name'])
        m = idx.get((h, a)) if h and a else None
        if not m:
            continue
        ko = dt.datetime.fromisoformat(f['fixture']['date']).astimezone(MAD)
        m['d'], m['t'] = ko.strftime('%Y-%m-%d'), ko.strftime('%H:%M')
        ref = (f['fixture'].get('referee') or '').split(',')[0].strip()
        if ref:
            m['arb'] = ref
        ventana = ko - dt.timedelta(minutes=120) <= ahora <= ko + dt.timedelta(minutes=15)
        if ventana and not m.get('ali'):
            try:
                L = api('fixtures/lineups', fixture=f['fixture']['id'])
                if len(L) == 2 and all(x.get('startXI') for x in L):
                    fh = L[0].get('formation') or '?'; fa = L[1].get('formation') or '?'
                    m['ali'] = f'confirmadas: {fh} / {fa}'; nlin += 1
            except Exception as e:
                print('AVISO API lineups:', repr(e)[:150])
    print(f'API-Football: {len(fx)} partidos leídos, {nlin} alineaciones nuevas')


# ---------------- football-data.org (plan gratis): horarios y árbitro ----------------
FDTOKEN = os.environ.get('FOOTBALLDATA_TOKEN', '').strip()


def fdorg(path):
    req = urllib.request.Request('https://api.football-data.org/v4/' + path,
                                 headers={'X-Auth-Token': FDTOKEN, 'User-Agent': 'benitooo'})
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode())


def aplicar_fdorg(jor, ahora):
    if not FDTOKEN:
        print('Sin FOOTBALLDATA_TOKEN.'); return
    try:
        res = fdorg('competitions/PD/matches')
    except Exception as e:
        print('AVISO football-data.org:', repr(e)[:200]); return
    ms = res.get('matches', [])
    idx = {}
    for j in jor:
        for m in j['ms']:
            idx[(norm(m['h']), norm(m['a']))] = m
    ours = {k[0]: k[0] for k in idx} | {k[1]: k[1] for k in idx}
    ok = con_arb = 0; sin = []
    for f in ms:
        def n(t):
            return casar(ours, t.get('shortName') or '') or casar(ours, t.get('name') or '')
        h, a = n(f['homeTeam']), n(f['awayTeam'])
        m = idx.get((h, a)) if h and a else None
        if not m:
            sin.append((f['homeTeam'].get('shortName'), f['awayTeam'].get('shortName'))); continue
        ok += 1; m['_fd'] = 1
        ko = dt.datetime.fromisoformat(f['utcDate'].replace('Z', '+00:00')).astimezone(MAD)
        if f.get('status') in ('SCHEDULED', 'TIMED'):
            m['d'], m['t'] = ko.strftime('%Y-%m-%d'), ko.strftime('%H:%M')
        refs = [r.get('name') for r in f.get('referees', []) if r.get('name') and r.get('type', 'REFEREE') == 'REFEREE']
        if refs:
            m['arb'] = refs[0]; con_arb += 1
    nomatch = [(m['h'], m['a'], m['d']) for j in jor for m in j['ms'] if not m.get('_fd')]
    print(f'football-data.org: {len(ms)} partidos leídos, {ok} casados con la app, {con_arb} con árbitro. Sin casar: {sin[:4]}')
    print('DIAG nuestros sin casar:', nomatch[:12], '| equipos API:', sorted({f['homeTeam'].get('shortName') for f in ms}))
    for j in jor:
        for m in j['ms']:
            m.pop('_fd', None)
    prox = [f for f in ms if f.get('status') in ('SCHEDULED', 'TIMED')][:1]
    if prox:
        try:
            d = fdorg(f"matches/{prox[0]['id']}")
            print('DIAGNÓSTICO detalle partido, claves:', sorted(d.keys()), '| lineups:', bool(d.get('homeTeam', {}).get('lineup')), '| referees:', d.get('referees'))
        except Exception as e:
            print('AVISO detalle:', repr(e)[:150])


# ---------------- FotMob (datos de su propia web, uso ligero): árbitro, alineaciones y bajas ----------------
def fm_get(u):
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'})
    h = urllib.request.urlopen(req, timeout=40).read().decode('utf-8', 'ignore')
    return json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S).group(1))['props']['pageProps']


def aplicar_fotmob(jor, ahora, liga_id=87, slug='laliga', horas=120):
    try:
        allm = fm_get(f'https://www.fotmob.com/leagues/{liga_id}/overview/{slug}')['fixtures']['allMatches']
    except Exception as e:
        print('AVISO FotMob liga:', repr(e)[:150]); return
    idx = {}
    for j in jor:
        for m in j['ms']:
            idx[(norm(m['h']), norm(m['a']))] = m
    ours = {k[0]: k[0] for k in idx} | {k[1]: k[1] for k in idx}
    nm = narb = nali = 0
    for f in allm:
        st = f.get('status', {})
        if st.get('finished') or st.get('cancelled'):
            continue
        h, a = casar(ours, f['home']['name']), casar(ours, f['away']['name'])
        m = idx.get((h, a)) if h and a else None
        if not m:
            continue
        nm += 1
        ko = dt.datetime.fromisoformat(st['utcTime'].replace('Z', '+00:00')).astimezone(MAD)
        if ko > ahora + dt.timedelta(hours=horas):
            continue
        try:
            g = fm_get('https://www.fotmob.com' + f['pageUrl'].split('#')[0])['content']
        except Exception as e:
            print('AVISO FotMob partido:', m['h'], m['a'], repr(e)[:100]); continue
        ref = ((g.get('matchFacts') or {}).get('infoBox') or {}).get('Referee') or {}
        if ref.get('text'):
            m['arb'] = ref['text']; narb += 1
        L = g.get('lineup') or {}
        if L.get('homeTeam') and L.get('awayTeam'):
            tipo = L.get('lineupType')
            baj = lambda t: ', '.join(x['name'].split(' ')[-1] for x in (t.get('unavailable') or [])[:5])
            fh, fa = L['homeTeam'].get('formation') or '?', L['awayTeam'].get('formation') or '?'
            ok_f = fh != '?' and fa != '?' and L['homeTeam'].get('starters') and L['awayTeam'].get('starters')
            etq = 'confirmadas' if (tipo not in ('predicted', 'lastStarting11', None) and ok_f) else 'NO oficiales (probables)'
            txt = f'{etq}: {fh} / {fa}' if ok_f else 'sin confirmar'
            bl, bv = baj(L['homeTeam']), baj(L['awayTeam'])
            if bl or bv:
                txt += f" · Bajas: {m['h']}: {bl or '—'}; {m['a']}: {bv or '—'}"
            m['ali'] = txt; nali += 1
    print(f'FotMob: {nm} partidos casados, {narb} con árbitro, {nali} con alineación/bajas (ventana {horas} h)')


def main():
    descargar_sp1()
    app = json.load(open(DATOS, encoding='utf-8'))
    if 'ligas' not in app:                      # formato antiguo: solo Primera
        app = {'ligas': {'primera': {'nombre': 'Primera', 'jor': app['jor'], 'meta': app.get('meta', {})}}}
    app['ligas'].setdefault('selecciones', {'nombre': 'Selecciones', 'jor': [], 'meta': {},
                                            'aviso': 'Selecciones: todavía no hay modelo ni calendario conectado.'})
    jor = app['ligas']['primera']['jor']
    ahora = dt.datetime.now(MAD)
    hoy = pd.Timestamp(ahora.date())
    aplicar_api(jor, ahora)
    aplicar_fdorg(jor, ahora)
    aplicar_fotmob(jor, ahora)
    n = 0
    for j in jor:
        for m in j['ms']:
            if pd.Timestamp(m['d']) < hoy:
                continue                      # ya jugado: no se recalcula
            T, pick, info = ap.analizar(m['h'], m['a'], None, hoy)
            m['s'] = seleccion(T, m['h'], m['a'])
            m['g'] = [info['lambda_goles'][0], info['lambda_goles'][1]]
            m['c'] = [info['corners_esperados'][0], info['corners_esperados'][1]]
            m['k'] = [info['tarjetas_esperadas'][0], info['tarjetas_esperadas'][1]]
            n += 1
    ult = pd.read_csv(SP1_FILE, encoding='utf-8-sig').dropna(subset=['FTHG'])
    ult = pd.to_datetime(ult.Date, dayfirst=True).max()
    app['ligas']['primera']['meta'] = {'act': ahora.strftime('%d/%m/%Y %H:%M'), 'datos': ult.strftime('%d/%m/%Y')}
    json.dump(app, open(DATOS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f'datos.json actualizado: {n} partidos recalculados. Datos hasta {app["ligas"]["primera"]["meta"]["datos"]}')


if __name__ == '__main__':
    main()
