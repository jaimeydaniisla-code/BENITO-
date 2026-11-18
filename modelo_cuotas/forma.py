"""Estadísticas reales de cada equipo (últimos 6 partidos: goles, córners, tarjetas a favor y en contra; racha; como local/visitante)
a partir de los CSV de football-data que ya usa el robot. Añade m['st'] a cada partido de datos.json. Solo datos reales, sin modelo."""
import os, glob, json, unicodedata, difflib
import warnings
import pandas as pd
warnings.filterwarnings('ignore')
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
DATOS = os.path.join(ROOT, 'datos.json')
FILES = {'primera': ['modelo/01_datos/historico/SP1_*.csv', 'modelo/01_datos/SP1_*.csv'],
         'premier': ['modelo_premier/01_datos/E0_*.csv'], 'segunda': ['modelo_segunda/01_datos/SP2_*.csv']}
ALIAS = {'athletic': 'ath bilbao', 'atletico': 'ath madrid', 'deportivo': 'la coruna', 'espanyol': 'espanol', 'racing': 'santander',
         'rayo': 'vallecano', 'real sociedad': 'sociedad', 'real sociedad b': 'sociedad b', 'sporting': 'sp gijon', 'nottm forest': "nott'm forest"}
N = 6


def nz(t):
    return unicodedata.normalize('NFKD', str(t)).encode('ascii', 'ignore').decode().lower().replace('.', '').replace('-', ' ').strip()


def cargar(pats):
    fs = [f for p in pats for f in glob.glob(os.path.join(ROOT, p))]
    al = []
    for f in fs:
        d = pd.read_csv(f, encoding='utf-8-sig').dropna(subset=['HomeTeam', 'FTHG'])
        d['Date'] = pd.to_datetime(d.Date, dayfirst=True, errors='coerce'); al.append(d)
    d = pd.concat(al, ignore_index=True).dropna(subset=['Date']).drop_duplicates(['Date', 'HomeTeam', 'AwayTeam']).sort_values('Date')
    for c in ('HC', 'AC', 'HY', 'AY', 'HR', 'AR'): d[c] = d[c].fillna(0)
    d['HK'] = d.HY + d.HR; d['AK'] = d.AY + d.AR
    return d.reset_index(drop=True)


def filas(d):
    """Una fila por equipo y partido: GF, GC, CF, CC, TF, TC, local(bool), resultado."""
    h = pd.DataFrame({'t': d.HomeTeam, 'f': d.Date, 'gf': d.FTHG, 'gc': d.FTAG, 'cf': d.HC, 'cc': d.AC, 'tf': d.HK, 'tc': d.AK, 'loc': True})
    a = pd.DataFrame({'t': d.AwayTeam, 'f': d.Date, 'gf': d.FTAG, 'gc': d.FTHG, 'cf': d.AC, 'cc': d.HC, 'tf': d.AK, 'tc': d.HK, 'loc': False})
    x = pd.concat([h, a]).sort_values('f'); x['r'] = (x.gf > x.gc).map({True: 'G', False: 'P'}).where(x.gf != x.gc, 'E')
    return x


def resumen(x):
    if not len(x): return None
    return [len(x)] + [round(float(x[c].mean()), 1) for c in ('gf', 'gc', 'cf', 'cc', 'tf', 'tc')]


def buscar(nombre, equipos):
    k = ALIAS.get(nz(nombre), nz(nombre)); m = {nz(e): e for e in equipos}
    if k in m: return m[k]
    mejor = difflib.get_close_matches(k, list(m), n=1, cutoff=0.75)
    return m[mejor[0]] if mejor else None


def main():
    app = json.load(open(DATOS, encoding='utf-8')); tot = sin = 0
    for liga, pats in FILES.items():
        L = app.get('ligas', {}).get(liga)
        if not L: continue
        D = cargar(pats); x = filas(D); equipos = set(x.t)
        reciente = x.tail(380 * 2)  # media de liga: ~ última temporada
        lg = [round(float(reciente[c].mean()), 1) for c in ('gf', 'cf', 'tf')]
        for J in L['jor']:
            for m in J['ms']:
                st = {'lg': lg}
                for lado, nom, loc in (('h', m['h'], True), ('a', m['a'], False)):
                    e = buscar(nom, equipos)
                    if not e: continue
                    t = x[x.t == e]; v = t[t['loc'] == loc]
                    st[lado] = {'r': ''.join(t.tail(5).r), 'u': resumen(t.tail(N)), 'v': resumen(v.tail(N))}
                tot += 1
                if 'h' in st and 'a' in st: m['st'] = st
                else: sin += 1; print('  sin estadísticas:', liga, m['h'], m['a'])
        # resultados reales de los últimos 30 días (con los nombres de la app) para marcar solas las apuestas del registro
        c2a = {}
        for J in L['jor']:
            for m in J['ms']:
                for n in (m['h'], m['a']):
                    e = buscar(n, equipos)
                    if e: c2a[e] = n
        rec = D[D.Date >= pd.Timestamp.now().normalize() - pd.Timedelta(days=30)]
        L['res'] = [[r.Date.strftime('%Y-%m-%d'), c2a[r.HomeTeam], c2a[r.AwayTeam], int(r.FTHG), int(r.FTAG), int(r.HC), int(r.AC), int(r.HK), int(r.AK)]
                    for r in rec.itertuples() if r.HomeTeam in c2a and r.AwayTeam in c2a]
    json.dump(app, open(DATOS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('estadísticas añadidas a', tot - sin, 'de', tot, 'partidos')


if __name__ == '__main__':
    main()
