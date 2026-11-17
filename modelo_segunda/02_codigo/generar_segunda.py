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


import difflib, unicodedata


def nz(t):
    return unicodedata.normalize('NFKD', str(t)).encode('ascii', 'ignore').decode().lower().replace('.', '').strip()


ALIAS = {'sporting gijon': 'sp gijon', 'real sporting': 'sp gijon', 'deportivo la coruna': 'la coruna', 'ad ceuta': 'ceuta', 'cd castellon': 'castellon',
         'real zaragoza': 'zaragoza', 'real valladolid': 'valladolid', 'cd leganes': 'leganes', 'ud las palmas': 'las palmas', 'ud almeria': 'almeria',
         'cd mirandes': 'mirandes', 'cadiz cf': 'cadiz', 'real sociedad b': 'sociedad b', 'athletic club b': 'ath bilbao', 'real racing club': 'santander',
         'racing santander': 'santander', 'racing de santander': 'santander', 'granada cf': 'granada', 'malaga cf': 'malaga', 'ud ibiza': 'ibiza', 'fc andorra': 'andorra',
         'burgos cf': 'burgos', 'real oviedo': 'oviedo', 'albacete balompie': 'albacete', 'cultural leonesa': 'cultural leonesa', 'eldense': 'eldense', 'huesca': 'huesca'}


def fm_get(u):
    import re
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'})
    h = urllib.request.urlopen(req, timeout=40).read().decode('utf-8', 'ignore')
    return json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S).group(1))['props']['pageProps']


def fm_calendario(equipos, hoy):
    """Calendario de Segunda desde FotMob. Devuelve filas con equipos ya mapeados a los nombres de football-data."""
    allm = fm_get('https://www.fotmob.com/leagues/140/overview/laliga2')['fixtures']['allMatches']
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
    if sin: print('AVISO FotMob Segunda sin casar:', sorted(sin)[:6])
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
        if bl or bv: ali += f" · Bajas: {BONITO.get(f['h'], f['h'])}: {bl or '—'}; {BONITO.get(f['a'], f['a'])}: {bv or '—'}"
    return ref, ali


def main():
    descargar_sp2()
    ahora = dt.datetime.now(MAD); hoy = pd.Timestamp(ahora.date())
    app = json.load(open(DATOS, encoding='utf-8')); lig = app.setdefault('ligas', {})
    hist0 = pd.read_csv(SP2_FILE, encoding='utf-8-sig').dropna(subset=['FTHG'])
    equipos = sorted(set(hist0.HomeTeam) | set(hist0.AwayTeam))
    try:
        fx = fm_calendario(equipos, hoy)
    except Exception as e:
        print('AVISO FotMob calendario Segunda:', repr(e)[:150]); return
    hist = hist0
    ult = pd.to_datetime(hist.Date, dayfirst=True).max()
    meta = {'act': ahora.strftime('%d/%m/%Y %H:%M'), 'datos': ult.strftime('%d/%m/%Y')}
    if not fx:
        print('Sin partidos próximos de Segunda en FotMob'); lig['segunda'] = {'nombre': 'Segunda', 'jor': [], 'meta': meta}
    else:
        import functools
        ap.cargar_partidos = functools.lru_cache(maxsize=None)(ap.cargar_partidos)
        _fit, _c = ap.dc.fit, {}
        ap.dc.fit = lambda tr, ref, xi, reg: _c.setdefault((len(tr), ref, xi, reg), _fit(tr, ref, xi, reg))
        _CM, _c2 = ap.CountModel, {}

        class CM(_CM):
            def fit(self, tr, ref, a, b):
                k = (len(tr), ref, a, b, repr(sorted(self.__dict__.items())))
                if k in _c2:
                    self.__dict__.update(_c2[k]); return self
                super().fit(tr, ref, a, b); _c2[k] = dict(self.__dict__); return self
        ap.CountModel = CM
        rondas = []
        for r in fx:
            if r['ronda'] not in rondas: rondas.append(r['ronda'])
        jor, narb, nali = [], 0, 0
        for ronda in rondas[:3]:
            ms = []
            for r in [x for x in fx if x['ronda'] == ronda]:
                h, a = BONITO.get(r['h'], r['h']), BONITO.get(r['a'], r['a'])
                try:
                    T, pick, info = ap.analizar(r['h'], r['a'], hoy)
                except Exception as e:
                    print('AVISO modelo', r['h'], r['a'], repr(e)[:120]); continue
                arb, ali = fm_detalle(r, ahora)
                narb += bool(arb); nali += bool(ali)
                ms.append({'h': h, 'a': a, 'd': r['ko'].strftime('%Y-%m-%d'), 't': r['ko'].strftime('%H:%M'), 'arb': arb, 'ali': ali,
                           'g': [float(x) for x in info['lambdas_finales']], 'c': [float(x) for x in info['corners_esp']], 'k': [float(x) for x in info['tarjetas_esp']],
                           's': seleccion(T, h, a)})
            if ms:
                try: jn = int(ronda)
                except Exception: jn = len(jor) + 1
                jor.append({'j': jn, 'ms': ms})
        lig['segunda'] = {'nombre': 'Segunda', 'jor': jor, 'meta': meta}
        print(f'Segunda: {sum(len(j["ms"]) for j in jor)} partidos en {len(jor)} jornadas; {narb} con árbitro, {nali} con alineación/bajas. Datos hasta {ult.date()}')
    json.dump(app, open(DATOS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    main()
