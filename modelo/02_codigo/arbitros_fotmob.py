"""Árbitro de cada partido de La Liga (SP1) desde FotMob (football-data no lo trae en España).
Guarda 01_datos/arbitros_fotmob.csv (Date, HomeTeam, AwayTeam con nombres de football-data, Referee).
Incremental: solo pide los partidos que faltan (máx. MAXP por pasada)."""
import os, sys, time, json, urllib.parse, datetime as dt
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import generar_datos as G   # fija LALIGA_DATA al histórico del repo
from generar_datos import fm_get, norm, casar, MAD
from data import load_sp1
OUT = os.path.join(HERE, '..', '01_datos', 'arbitros_fotmob.csv')
TEMPORADAS = [None] if os.environ.get('ARB_SOLO_ACTUAL') else ['2021/2022', '2022/2023', '2023/2024', '2024/2025', '2025/2026', None]   # None = temporada actual
MAXP = int(os.environ.get('ARB_MAXP', '1500'))


def partidos(temp):
    urls = ['https://www.fotmob.com/leagues/87/overview/laliga'] if temp is None else \
        [f'https://www.fotmob.com/leagues/87/overview/laliga?season={urllib.parse.quote(temp)}', f'https://www.fotmob.com/leagues/87/fixtures/laliga?season={urllib.parse.quote(temp)}']
    for u in urls:
        try:
            pp = fm_get(u); fx = pp.get('fixtures') or {}
            allm = fx.get('allMatches') or fx.get('allFixtures', {}).get('fixtures') or []
            fin = [f for f in allm if (f.get('status') or {}).get('finished')]
            if fin: print(temp or 'actual', u.split('/')[-1][:40], len(fin), 'terminados'); return fin
        except Exception as e:
            print('AVISO', u, repr(e)[:80])
    return []


def main():
    hist = load_sp1(); equipos = sorted(set(hist.HomeTeam) | set(hist.AwayTeam)); por = {norm(e): e for e in equipos}
    FIJO = {'atletico madrid': 'Ath Madrid', 'athletic club': 'Ath Bilbao', 'athletic bilbao': 'Ath Bilbao', 'rayo vallecano': 'Vallecano'}
    def mapa(n):
        f = FIJO.get(G.unicodedata.normalize('NFKD', n).encode('ascii', 'ignore').decode().lower().strip())
        if f in equipos: return f
        k = casar({x: x for x in por}, n)
        return por[k] if k else None
    prev = pd.read_csv(OUT, dtype={'id': str}) if os.path.exists(OUT) else pd.DataFrame(columns=['id', 'Date', 'HomeTeam', 'AwayTeam', 'Referee'])
    prev = prev.sort_values('Referee', na_position='first').drop_duplicates('id', keep='last')
    hechos = set(prev[prev.Referee.notna()].id.astype(str));   # los que no tienen árbitro se vuelven a intentar
    filas = []; n = 0
    for t in TEMPORADAS:
        for f in partidos(t):
            mid = str(f.get('id'))
            if mid in hechos or not f.get('pageUrl'): continue
            if n >= MAXP: break
            h, a = mapa(f['home']['name']), mapa(f['away']['name'])
            if not h or not a: continue
            try:
                g = fm_get('https://www.fotmob.com' + f['pageUrl'].split('#')[0])['content']
                ib = (g.get('matchFacts') or {}).get('infoBox') or {}
                ref = (ib.get('Referee') or {}).get('text')
                ref = ref or 'sin dato'   # FotMob no tiene árbitro en ~30 % de partidos antiguos: no se vuelve a pedir
            except Exception as e:
                print('AVISO partido', h, a, repr(e)[:60]); ref = None
            n += 1
            d = dt.datetime.fromisoformat(f['status']['utcTime'].replace('Z', '+00:00')).astimezone(MAD).strftime('%Y-%m-%d')
            filas.append({'id': mid, 'Date': d, 'HomeTeam': h, 'AwayTeam': a, 'Referee': ref})
            time.sleep(0.25)
    nuevo = pd.DataFrame(filas, columns=['id', 'Date', 'HomeTeam', 'AwayTeam', 'Referee'])
    out = pd.concat([prev, nuevo], ignore_index=True)
    out['id'] = out.id.astype(str)
    out = out.sort_values('Referee', na_position='first').drop_duplicates('id', keep='last').sort_values('Date')
    out.to_csv(OUT, index=False)
    print(f'Árbitros: {len(out)} partidos ({len(filas)} nuevos, {out.Referee.notna().sum()} con árbitro, {out.Referee.nunique()} árbitros distintos)')


if __name__ == '__main__':
    main()
