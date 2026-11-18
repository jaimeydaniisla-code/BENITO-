"""Cuotas gratuitas de football-data.co.uk/fixtures.csv (ronda actual: bwin y media del mercado, 1X2 y más/menos 2,5).
Respaldo para los partidos sin cuotas de OddsPapi (límite mensual, ventana de 4 días, Segunda). Añade m['fd'] = [local, empate, visitante, más2.5, menos2.5, fuente]."""
import os, sys, io, json, urllib.request
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from forma import buscar
ROOT = os.path.abspath(os.path.join(HERE, '..')); DATOS = os.path.join(ROOT, 'datos.json')
DIV = {'primera': 'SP1', 'segunda': 'SP2', 'premier': 'E0'}


def bajar():
    for url in ('https://football-data.co.uk/fixtures.csv', 'https://www.football-data.co.uk/fixtures.csv'):
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=40).read()
            if len(raw) > 500: return pd.read_csv(io.BytesIO(raw), encoding='utf-8-sig', on_bad_lines='skip')
        except Exception as e:
            print('fixtures.csv:', url, repr(e)[:80])
    return None


def tomar(r, cols, pref):
    for p in pref:
        v = [r.get(c) for c in cols[p]]
        if all(pd.notna(x) and float(x) > 1 for x in v): return [float(x) for x in v], p
    return None, None


def main():
    d = bajar()
    if d is None: print('sin fixtures.csv'); return
    d['f'] = pd.to_datetime(d.Date, dayfirst=True, errors='coerce').dt.strftime('%Y-%m-%d')
    app = json.load(open(DATOS, encoding='utf-8')); n = 0
    c1 = {'bwin': ['BWH', 'BWD', 'BWA'], 'media': ['AvgH', 'AvgD', 'AvgA'], 'b365': ['B365H', 'B365D', 'B365A']}
    c2 = {'media': ['Avg>2.5', 'Avg<2.5'], 'b365': ['B365>2.5', 'B365<2.5']}
    for liga, dv in DIV.items():
        L = app.get('ligas', {}).get(liga); s = d[d.Div == dv]
        if not L or not len(s): continue
        eq = set(s.HomeTeam) | set(s.AwayTeam)
        for J in L['jor']:
            for m in J['ms']:
                m.pop('fd', None)
                h, a = buscar(m['h'], eq), buscar(m['a'], eq)
                if not h or not a: continue
                r = s[(s.HomeTeam == h) & (s.AwayTeam == a) & (s.f >= m['d']) & (s.f <= m['d'])]
                if not len(r): continue
                r = r.iloc[0]
                t1, f1 = tomar(r, c1, ('bwin', 'media', 'b365')); t2, f2 = tomar(r, c2, ('media', 'b365'))
                if t1 and t2: m['fd'] = t1 + t2 + [f1]; n += 1
    json.dump(app, open(DATOS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('cuotas de football-data añadidas a', n, 'partidos')


if __name__ == '__main__':
    main()
