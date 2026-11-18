"""Directo y alineaciones: robot ligero (cada ~10 min). Solo trabaja si hay partidos de la app cerca de su hora (de 100 min antes a 3 h después).
Lee FotMob (marcador, minuto, alineaciones, árbitro) y escribe envivo.json, un fichero pequeño aparte de datos.json.
No usa claves ni el cupo de OddsPapi."""
import os, re, json, unicodedata, difflib, datetime as dt, urllib.request
try:
    from zoneinfo import ZoneInfo; MAD = ZoneInfo('Europe/Madrid')
except Exception:
    MAD = dt.timezone(dt.timedelta(hours=1))
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
DATOS, SALIDA = os.path.join(ROOT, 'datos.json'), os.path.join(ROOT, 'envivo.json')
LIGAS = {'primera': (87, 'laliga'), 'segunda': (140, 'laliga2'), 'premier': (47, 'premier-league')}
ANTES, DESPUES = 100, 180   # minutos antes y después de la hora de inicio en los que se vigila un partido
ALIAS = {'athletic club': 'athletic', 'athletic': 'ath bilbao', 'real betis': 'betis', 'celta vigo': 'celta', 'rayo vallecano': 'vallecano', 'rayo': 'vallecano',
         'atletico madrid': 'ath madrid', 'atletico': 'ath madrid', 'deportivo la coruna': 'la coruna', 'deportivo': 'la coruna', 'racing santander': 'santander', 'racing': 'santander',
         'deportivo alaves': 'alaves', 'rcd espanyol': 'espanol', 'espanyol': 'espanol', 'ud las palmas': 'las palmas', 'sevilla fc': 'sevilla', 'real sociedad': 'sociedad',
         'real sociedad b': 'sociedad b', 'sporting gijon': 'sp gijon', 'real sporting': 'sp gijon', 'sporting': 'sp gijon', 'ad ceuta': 'ceuta', 'cd castellon': 'castellon',
         'real valladolid': 'valladolid', 'cd leganes': 'leganes', 'ud almeria': 'almeria', 'cadiz cf': 'cadiz', 'athletic club b': 'ath bilbao b', 'real racing club': 'santander',
         'granada cf': 'granada', 'malaga cf': 'malaga', 'fc andorra': 'andorra', 'burgos cf': 'burgos', 'real oviedo': 'oviedo', 'albacete balompie': 'albacete',
         'celta fortuna': 'celta b', 'manchester united': 'man united', 'manchester city': 'man city', 'newcastle united': 'newcastle', 'tottenham hotspur': 'tottenham',
         'nottingham forest': "nott'm forest", 'wolverhampton wanderers': 'wolves', 'brighton & hove albion': 'brighton', 'west ham united': 'west ham', 'leeds united': 'leeds',
         'hull city': 'hull', 'ipswich town': 'ipswich', 'leicester city': 'leicester', 'coventry city': 'coventry', 'afc bournemouth': 'bournemouth'}


def nz(t):
    return unicodedata.normalize('NFKD', str(t)).encode('ascii', 'ignore').decode().lower().replace('.', '').replace('-', ' ').strip()


def clave(n):
    k = nz(n)
    for _ in range(3):
        k2 = ALIAS.get(k, k)
        if k2 == k: break
        k = k2
    return k


def fm_get(u):
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'})
    h = urllib.request.urlopen(req, timeout=40).read().decode('utf-8', 'ignore')
    return json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S).group(1))['props']['pageProps']


def alineacion(g, H, A):
    L = g.get('lineup') or {}
    if not (L.get('homeTeam') and L.get('awayTeam')): return None
    tipo = L.get('lineupType')
    baj = lambda t: ', '.join(x['name'].split(' ')[-1] for x in (t.get('unavailable') or [])[:5])
    fh, fa = L['homeTeam'].get('formation') or '?', L['awayTeam'].get('formation') or '?'
    ok = fh != '?' and fa != '?' and L['homeTeam'].get('starters') and L['awayTeam'].get('starters')
    etq = 'confirmadas' if (tipo not in ('predicted', 'lastStarting11', None) and ok) else 'NO oficiales (probables)'
    txt = f'{etq}: {fh} / {fa}' if ok else 'sin confirmar'
    bl, bv = baj(L['homeTeam']), baj(L['awayTeam'])
    if bl or bv: txt += f' · Bajas: {H}: {bl or "—"}; {A}: {bv or "—"}'
    return txt


def main():
    ahora = dt.datetime.now(MAD)
    app = json.load(open(DATOS, encoding='utf-8'))
    try: previo = json.load(open(SALIDA, encoding='utf-8'))
    except Exception: previo = {}
    cerca = {}
    for liga in LIGAS:
        for J in app.get('ligas', {}).get(liga, {}).get('jor', []):
            for m in J['ms']:
                if m.get('t') and abs((dt.datetime.fromisoformat(m['d']).date() - ahora.date()).days) <= 1:
                    ko = dt.datetime.fromisoformat(m['d'] + 'T' + m['t']).replace(tzinfo=MAD)
                    if ko - dt.timedelta(minutes=ANTES) <= ahora <= ko + dt.timedelta(minutes=DESPUES):
                        cerca.setdefault(liga, []).append((m, ko))
    if not cerca:
        print('Sin partidos cerca de su hora: nada que hacer'); return
    ayer = (ahora.date() - dt.timedelta(days=1)).isoformat()
    p = {k: dict(v) for k, v in (previo.get('p') or {}).items() if k.split('|')[1] >= ayer}   # se conserva el marcador final hasta el día siguiente
    for liga, lst in cerca.items():
        lid, slug = LIGAS[liga]
        try: allm = fm_get(f'https://www.fotmob.com/leagues/{lid}/overview/{slug}')['fixtures']['allMatches']
        except Exception as e: print('AVISO FotMob liga', liga, repr(e)[:100]); continue
        for m, ko in lst:
            kh, ka = clave(m['h']), clave(m['a']); f = None; best = 0
            for x in allm:
                try: u = dt.datetime.fromisoformat(x['status']['utcTime'].replace('Z', '+00:00')).astimezone(MAD)
                except Exception: continue
                if abs((u - ko).total_seconds()) > 36 * 3600: continue
                s = difflib.SequenceMatcher(None, kh, clave(x['home']['name'])).ratio() + difflib.SequenceMatcher(None, ka, clave(x['away']['name'])).ratio()
                if s > best: f, best = x, s
            if not f or best < 1.5: print('  sin casar:', liga, m['h'], m['a'], round(best, 2)); continue
            st = f.get('status', {}); e = {}
            if st.get('started') or st.get('finished'):
                lt = st.get('liveTime') or {}
                e['e'] = 'f' if st.get('finished') else 'j'
                e['sc'] = st.get('scoreStr') or ''
                mn = lt.get('short') if isinstance(lt, dict) else None
                if mn and e['e'] == 'j': e['min'] = mn
            if ko - ahora <= dt.timedelta(minutes=ANTES) and not st.get('finished'):
                try:
                    g = fm_get('https://www.fotmob.com' + f['pageUrl'].split('#')[0])['content']
                    ali = alineacion(g, m['h'], m['a'])
                    if ali: e['ali'] = ali
                    ref = ((g.get('matchFacts') or {}).get('infoBox') or {}).get('Referee') or {}
                    if ref.get('text'): e['arb'] = ref['text']
                except Exception as ex:
                    print('  AVISO partido:', m['h'], m['a'], repr(ex)[:80])
            if e: p.setdefault(f"{liga}|{m['d']}|{m['h']}|{m['a']}", {}).update(e)
    nuevo = {'p': p}
    if nuevo == {'p': previo.get('p', {})}:
        print('Sin cambios'); return
    nuevo['act'] = ahora.strftime('%d/%m %H:%M')
    json.dump(nuevo, open(SALIDA, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('envivo.json actualizado:', len(p), 'partidos')


if __name__ == '__main__':
    main()
