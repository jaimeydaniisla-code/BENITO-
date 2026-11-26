"""Champions League -> datos.json (ligas.champions).
Calendario y resultados: FotMob (liga 42). Probabilidades base: ratings Elo de clubelo.com si responde (se guarda la última copia buena en elo.json);
cuando hay cuotas de bwin, modelo_cuotas/generar_cuotas.py --aplicar-solo sustituye goles y resultado por las del mercado (validado como mejor).
Sin validar contra cuotas históricas: todo lo que sale del Elo se marca como poco fiable."""
import os, re, sys, json, difflib, unicodedata, datetime as dt, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(ROOT, 'modelo_selecciones'))
import numpy as np
from scipy.optimize import brentq
from selecciones import Sel, mercados
from generar_selecciones import seleccion
try:
    from zoneinfo import ZoneInfo; MAD = ZoneInfo('Europe/Madrid')
except Exception:
    MAD = dt.timezone(dt.timedelta(hours=1))
DATOS, ELO = os.path.join(ROOT, 'datos.json'), os.path.join(HERE, 'elo.json')
VENTAJA, MU0, NPRIOR, RHO = 65.0, 2.8, 40, -0.045     # puntos Elo de ventaja local, goles medios a priori, peso del a priori (partidos), rho Dixon-Coles
ALIAS = {'bayern munchen': 'bayern', 'paris saint germain': 'paris sg', 'atletico madrid': 'atletico', 'manchester city': 'man city', 'manchester united': 'man united',
         'borussia dortmund': 'dortmund', 'psv eindhoven': 'psv', 'shakhtar donetsk': 'shakhtar', 'slavia prague': 'slavia praha', 'sporting cp': 'sporting',
         'rb leipzig': 'leipzig', 'vfb stuttgart': 'stuttgart', 'real betis': 'betis', 'fenerbahce': 'fenerbahce', 'bodo/glimt': 'bodoe glimt', 'bodo glimt': 'bodoe glimt',
         'club brugge': 'brugge', 'fc porto': 'porto', 'aek athens': 'aek', 'sabah fk': 'sabah', 'olympique marseille': 'marseille', 'tottenham hotspur': 'tottenham',
         'newcastle united': 'newcastle', 'eintracht frankfurt': 'frankfurt', 'bayer leverkusen': 'leverkusen', 'benfica': 'benfica', 'ac milan': 'milan', 'inter': 'inter'}


def nz(t):
    return unicodedata.normalize('NFKD', str(t)).encode('ascii', 'ignore').decode().lower().replace('.', '').replace('-', ' ').strip()


def fm_get(u):
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'})
    h = urllib.request.urlopen(req, timeout=40).read().decode('utf-8', 'ignore')
    return json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S).group(1))['props']['pageProps']


def ratings():
    """Elo de clubelo.com (CSV por fecha). Si falla, última copia guardada. Devuelve ({club: elo}, fecha) o ({}, None)."""
    for k in range(2):
        for atras in (0, 1, 2):
            f = (dt.date.today() - dt.timedelta(days=atras)).isoformat()
            try:
                txt = urllib.request.urlopen(urllib.request.Request('http://api.clubelo.com/' + f, headers={'User-Agent': 'Mozilla/5.0 (benitooo)'}), timeout=25).read().decode()
                clubs = {}
                for ln in txt.splitlines()[1:]:
                    z = ln.split(',')
                    if len(z) >= 5: clubs[z[1]] = float(z[4])
                if len(clubs) > 300:
                    json.dump({'fecha': f, 'clubs': clubs}, open(ELO, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
                    return clubs, f
            except Exception as e:
                print('AVISO clubelo', f, repr(e)[:80])
    try:
        d = json.load(open(ELO, encoding='utf-8')); print('Usando Elo guardado de', d['fecha']); return d['clubs'], d['fecha']
    except Exception:
        return {}, None


def elo_de(nombre, clubs, idx):
    k = nz(nombre); k = ALIAS.get(k, k)
    if k in idx: return clubs[idx[k]]
    b = difflib.get_close_matches(k, list(idx), n=1, cutoff=0.72)
    return clubs[idx[b[0]]] if b else None


def lambdas(dif, mu, sel):
    """Goles esperados (local, visitante) tales que P(gana)+½P(empata) = esperanza Elo, con total mu."""
    we = 1 / (1 + 10 ** (-dif / 400))
    def f(s):
        M = sel.matriz((mu + s) / 2, (mu - s) / 2); i, j = np.indices(M.shape)
        return M[i > j].sum() + 0.5 * M[i == j].sum() - we
    s = brentq(f, -mu + 0.5, mu - 0.5)
    return (mu + s) / 2, (mu - s) / 2


COMP = {'champions': (42, 'champions-league', 'Champions'), 'europa': (73, 'europa-league', 'Europa League')}


def main(clave='champions'):
    lid, slug, nombre = COMP[clave]
    ahora = dt.datetime.now(MAD)
    allm = fm_get(f'https://www.fotmob.com/leagues/{lid}/overview/{slug}')['fixtures']['allMatches']
    def ko(f): return dt.datetime.fromisoformat(f['status']['utcTime'].replace('Z', '+00:00')).astimezone(MAD)
    fin = [f for f in allm if f['status'].get('finished') and f['status'].get('scoreStr')]
    goles = [sum(int(x) for x in re.findall(r'\d+', f['status']['scoreStr'])) for f in fin]
    mu = (MU0 * NPRIOR + sum(goles)) / (NPRIOR + len(goles))
    res = []
    for f in fin:
        g = re.findall(r'\d+', f['status']['scoreStr'])
        if ko(f) >= ahora - dt.timedelta(days=30): res.append([ko(f).strftime('%Y-%m-%d'), f['home']['name'], f['away']['name'], int(g[0]), int(g[1])])
    pend = sorted([f for f in allm if not f['status'].get('finished') and not f['status'].get('cancelled')], key=lambda f: f['status']['utcTime'])
    rondas = []
    for f in pend:
        r = str(f.get('round'))
        if r not in rondas: rondas.append(r)
    rondas = rondas[:2]
    clubs, fecha = ratings(); idx = {nz(c): c for c in clubs}
    sel = Sel(); sel.rho = RHO
    jor, sin = [], set()
    for r in rondas:
        ms = []
        for f in pend:
            if str(f.get('round')) != r: continue
            h, a = f['home']['name'], f['away']['name']; k = ko(f)
            m = {'h': h, 'a': a, 'd': k.strftime('%Y-%m-%d'), 't': k.strftime('%H:%M'), 'arb': None, 'ali': None, 'g': [None, None], 'c': [None, None], 'k': [None, None], 's': []}
            eh, ea = elo_de(h, clubs, idx), elo_de(a, clubs, idx)
            if eh is None or ea is None:
                sin.add(h if eh is None else a)
            else:
                l1, l2 = lambdas(eh - ea + VENTAJA, mu, sel); M = sel.matriz(l1, l2)
                m['g'] = [round(l1, 2), round(l2, 2)]; m['s'] = [[lab, cat, p, 0] for lab, cat, p, _ in seleccion(mercados(M), h, a)]
                m['elo'] = [round(eh), round(ea)]
            ms.append(m)
        if ms: jor.append({'j': int(r) if r.isdigit() else r, 'ms': ms})
    if sin: print('AVISO sin Elo para:', sorted(sin))
    aviso = (nombre + ': sin cuotas de bwin las probabilidades salen de un Elo sin validar (poco fiables); con cuotas de bwin pasan a ser las del mercado. '
             'Sin córners ni tarjetas.' if clubs else 'Champions: no hay ratings (clubelo.com no responde) y aún no hay cuotas de bwin: solo calendario, resultados y directo.')
    app = json.load(open(DATOS, encoding='utf-8')); lig = app.setdefault('ligas', {})
    lig[clave] = {'nombre': nombre, 'jor': jor, 'res': res, 'aviso': aviso,
                        'meta': {'act': ahora.strftime('%d/%m/%Y %H:%M'), 'datos': ('Elo ' + dt.date.fromisoformat(fecha).strftime('%d/%m') if fecha else 'FotMob')}}
    json.dump(app, open(DATOS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(nombre + ':', sum(len(j['ms']) for j in jor), 'partidos en rondas', rondas, '| terminados', len(fin), '| goles/partido', round(sum(goles) / max(len(goles), 1), 2), '| mu', round(mu, 2), '| Elo', fecha)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'champions')
