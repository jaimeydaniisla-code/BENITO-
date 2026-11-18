"""Cuotas de bwin.es vía OddsPapi (clave ODDSPAPI_KEY). Pocas peticiones: solo partidos de los próximos N días.
Guarda cuotas.json y aplica 'bw' a datos.json. Uso: python generar_cuotas.py [--aplicar-solo]"""
import os, sys, json, difflib, unicodedata, datetime as dt, urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
try:
    import mercado
except Exception as e:  # sin numpy/scipy solo se pierden los ajustes, no las cuotas
    mercado = None
    print('sin ajuste al mercado:', e)
ROOT = os.path.abspath(os.path.join(HERE, '..'))
DATOS, CUOTAS = os.path.join(ROOT, 'datos.json'), os.path.join(ROOT, 'cuotas.json')
KEY = os.environ.get('ODDSPAPI_KEY', '').strip()
try:
    from zoneinfo import ZoneInfo; MAD = ZoneInfo('Europe/Madrid')
except Exception:
    MAD = dt.timezone.utc
TORNEOS = {'primera': 8, 'segunda': 54, 'premier': 17}          # OddsPapi tournamentId (selecciones: se pide aparte con --selecciones ID)
DIAS = int(os.environ.get('CUOTAS_DIAS', '4'))
MAXPET = int(os.environ.get('CUOTAS_MAXPET', '40'))
HORAS = float(os.environ.get('CUOTAS_HORAS', '0') or 0)       # >0: solo partidos que empiezan dentro de N horas (cuota casi de cierre)
HIST = os.path.join(HERE, 'historico_cuotas.jsonl')            # una línea por partido y consulta (apertura, evolución y cierre)
CONT = os.path.join(HERE, 'peticiones.json')                   # peticiones usadas por mes (plan gratuito de OddsPapi: 250/mes)
LIMITE_MES = int(os.environ.get('CUOTAS_LIMITE_MES', '235'))
BASE_MES = {'2026-11': 100}                                    # estimación de lo gastado antes de llevar la cuenta
usadas = 0


def get(path, **p):
    global usadas
    import time
    u = 'https://api.oddspapi.io/v4' + path + '?' + urllib.parse.urlencode({'apiKey': KEY, **p})
    for intento in range(4):
        time.sleep(2.5 * (intento + 1))
        usadas += 1
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'benitooo'}), timeout=40).read().decode())
        except urllib.error.HTTPError as e:
            if e.code != 429 or intento == 3: raise
            print('  429, reintento', intento + 1)


def nz(t):
    return unicodedata.normalize('NFKD', str(t)).encode('ascii', 'ignore').decode().lower().replace('.', '').replace('-', ' ').strip()


def sim(a, b):
    a, b = nz(a), nz(b)
    if a in b or b in a: return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def c(L):
    return str(L).replace('.', ',')


def etiquetas(cat, mk, H, A):
    """Convierte los mercados de bwin a las etiquetas de la app. Devuelve {etiqueta: cuota}."""
    out = {}
    for mid, v in mk.items():
        m = cat.get(int(mid)) or cat.get(mid)
        if not m or m.get('period') != 'fulltime' or m.get('playerProp'): continue
        nom = {o['outcomeId']: o['outcomeName'] for o in m.get('outcomes', [])}
        pr = {}
        for oid, o in v['outcomes'].items():
            try: p = float(list(o['players'].values())[0]['price'])
            except Exception: continue
            if p > 1.0 and list(o['players'].values())[0].get('active', True): pr[nom.get(int(oid))] = p
        t, hc = m.get('marketType'), float(m.get('handicap') or 0)
        if t == '1x2' and 'Full Time' in m['marketName']:
            if '1' in pr: out[f'Gana {H}'] = pr['1']
            if '2' in pr: out[f'Gana {A}'] = pr['2']
        elif t == 'doublechance':
            if '1X' in pr: out[f'{H} o empate'] = pr['1X']
            if '2X' in pr: out[f'Empate o {A}'] = pr['2X']
            if '12' in pr: out['No hay empate'] = pr['12']
        elif t == 'drawnobet':
            if '1' in pr: out[f'{H} (empate no válido)'] = pr['1']
            if '2' in pr: out[f'{A} (empate no válido)'] = pr['2']
        elif t == 'totals' and 'Over Under Full Time' in m['marketName']:
            if 'Over' in pr: out[f'Goles: más de {c(hc)}'] = pr['Over']
            if 'Under' in pr: out[f'Goles: menos de {c(hc)}'] = pr['Under']
        elif t in ('teamtotals-team1', 'teamtotals-team2') and m['marketName'].startswith('Over Under Team') and 'Half' not in m['marketName']:
            eq = H if t.endswith('1') else A
            if 'Over' in pr: out[f'Goles {eq}: más de {c(hc)}'] = pr['Over']
            if 'Under' in pr: out[f'Goles {eq}: menos de {c(hc)}'] = pr['Under']
        elif t in ('totals-corners', 'totals-bookings') and abs(hc % 1 - 0.5) < 1e-9:
            nm = 'Córners' if 'corners' in t else 'Tarjetas'
            if 'Over' in pr: out[f'{nm}: más de {c(hc)}'] = pr['Over']
            if 'Under' in pr: out[f'{nm}: menos de {c(hc)}'] = pr['Under']
        elif t in ('teamtotals-corners-team1', 'teamtotals-corners-team2', 'teamtotals-bookings-team1', 'teamtotals-bookings-team2') and abs(hc % 1 - 0.5) < 1e-9:
            nm = 'Córners' if 'corners' in t else 'Tarjetas'; eq = H if t.endswith('1') else A
            if 'Over' in pr: out[f'{nm} {eq}: más de {c(hc)}'] = pr['Over']
            if 'Under' in pr: out[f'{nm} {eq}: menos de {c(hc)}'] = pr['Under']
        elif t == '1x2-corners':
            if '1' in pr: out[f'Más córners: {H}'] = pr['1']
            if '2' in pr: out[f'Más córners: {A}'] = pr['2']
        elif t == 'bothteamsscore':
            if 'Yes' in pr: out['Ambos marcan: Sí'] = pr['Yes']
            if 'No' in pr: out['Ambos marcan: No'] = pr['No']
        elif t == 'spreads' and abs(hc) == 1.5:
            if hc == -1.5:
                if '1' in pr: out[f'{H} gana por 2 o más'] = pr['1']
                if '2' in pr: out[f'{A} +1,5 (no pierde por 2)'] = pr['2']
            else:
                if '1' in pr: out[f'{H} +1,5 (no pierde por 2)'] = pr['1']
                if '2' in pr: out[f'{A} gana por 2 o más'] = pr['2']
        elif t in ('wintonil-team1', 'wintonil-team2'):
            if 'Yes' in pr: out[f'{H if t.endswith("1") else A} gana sin encajar'] = pr['Yes']
    return out


def catalogo():
    """Diagnóstico: lista los mercados de córners/tarjetas de bwin que hay en el catálogo (1 petición)."""
    r = get('/markets', sportId=10); r = r.get('data', r) if isinstance(r, dict) else r
    for m in r:
        n = (m.get('marketName') or '') + ' ' + (m.get('marketType') or '')
        if any(w in n.lower() for w in ('corner', 'card', 'booking')) and m.get('period') == 'fulltime':
            print(m.get('marketId'), '|', m.get('marketName'), '|', m.get('marketType'), '| hc', m.get('handicap'), '|', [o.get('outcomeName') for o in m.get('outcomes', [])])


def pedir():
    if not KEY:
        print('Sin ODDSPAPI_KEY'); return
    app = json.load(open(DATOS, encoding='utf-8')); ahora = dt.datetime.now(MAD)
    mes = ahora.strftime('%Y-%m')
    try: cont = json.load(open(CONT))
    except Exception: cont = {}
    gastado = cont.get(mes, BASE_MES.get(mes, 0))
    if gastado >= LIMITE_MES:
        print(f'Límite mensual de peticiones alcanzado ({gastado}/{LIMITE_MES}): no se piden cuotas'); return
    global MAXPET
    MAXPET = min(MAXPET, LIMITE_MES - gastado)
    cat = {m['marketId']: m for m in (lambda r: r.get('data', r) if isinstance(r, dict) else r)(get('/markets', sportId=10))}
    try: cu = json.load(open(CUOTAS, encoding='utf-8'))
    except Exception: cu = {}
    for liga, tid in TORNEOS.items():
        jor = app.get('ligas', {}).get(liga, {}).get('jor', [])
        ms = [m for j in jor for m in j['ms'] if ahora.date().isoformat() <= m['d'] <= (ahora + dt.timedelta(days=DIAS)).date().isoformat()]
        if HORAS > 0:
            def ko(m):
                return dt.datetime.fromisoformat(m['d'] + 'T' + (m.get('t') or '23:59')).replace(tzinfo=MAD)
            ms = [m for m in ms if ahora <= ko(m) <= ahora + dt.timedelta(hours=HORAS)]
        if not ms: print(liga, ': sin partidos en la ventana'); continue
        try:
            fx = get('/fixtures', tournamentId=tid, **{'from': ahora.strftime('%Y-%m-%d'), 'to': (ahora + dt.timedelta(days=DIAS + 1)).strftime('%Y-%m-%d')})
        except Exception as e:
            print(liga, 'fixtures error', repr(e)[:80]); continue
        fx = fx.get('data', fx) if isinstance(fx, dict) else fx
        n = sin = 0
        for m in ms:
            if usadas >= MAXPET: print('Tope de peticiones alcanzado'); break
            mejor, bs = None, 0
            for f in fx:
                ko = dt.datetime.fromisoformat(f['startTime'].replace('Z', '+00:00')).astimezone(MAD)
                if ko.date().isoformat() != m['d'] or not f.get('hasOdds'): continue
                s = sim(m['h'], f.get('participant1Name', '')) + sim(m['a'], f.get('participant2Name', ''))
                if s > bs: mejor, bs = f, s
            if not mejor or bs < 1.2:
                sin += 1; print('  sin casar:', liga, m['h'], m['a'], m['d'], round(bs, 2)); continue
            try:
                d = get('/odds', fixtureId=mejor['fixtureId'], bookmakers='bwin.es')
                mk = d['bookmakerOdds']['bwin.es']['markets']
            except Exception as e:
                print('  sin cuotas:', m['h'], m['a'], repr(e)[:80]); continue
            et = etiquetas(cat, mk, m['h'], m['a'])
            if et:
                cu[f"{liga}|{m['d']}|{m['h']}|{m['a']}"] = {'act': ahora.strftime('%d/%m %H:%M'), 'bw': et}; n += 1
                with open(HIST, 'a', encoding='utf-8') as fh:
                    fh.write(json.dumps({'t': ahora.isoformat(timespec='minutes'), 'liga': liga, 'd': m['d'], 'hora': m.get('t'), 'h': m['h'], 'a': m['a'], 'bw': et},
                                        ensure_ascii=False, separators=(',', ':')) + '\n')
        print(f'{liga}: {n} partidos con cuotas, {sin} sin casar')
    json.dump(cu, open(CUOTAS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('peticiones usadas en esta pasada:', usadas)
    cont[mes] = gastado + usadas; json.dump(cont, open(CONT, 'w'))
    print(f'peticiones del mes (estimadas): {cont[mes]}/{LIMITE_MES}')


def aplicar():
    cu = json.load(open(CUOTAS, encoding='utf-8')) if os.path.exists(CUOTAS) else {}
    app = json.load(open(DATOS, encoding='utf-8')); k = aj = 0
    for liga, L in app.get('ligas', {}).items():
        for j in L['jor']:
            for m in j['ms']:
                v = cu.get(f"{liga}|{m['d']}|{m['h']}|{m['a']}")
                if v:
                    m['bw'] = v['bw']; m['bwact'] = v['act']; k += 1
                try:
                    if mercado and mercado.ajustar(m): aj += 1
                    if mercado and m.get('bw'): mercado.mezclar_conteos(m)
                except Exception as e:
                    print('ajuste al mercado falló en', m['h'], m['a'], e)
    json.dump(app, open(DATOS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('cuotas bwin aplicadas a', k, 'partidos;', aj, 'con probabilidades ajustadas al mercado')


if __name__ == '__main__':
    if '--catalogo' in sys.argv: catalogo(); sys.exit(0)
    if '--aplicar-solo' not in sys.argv: pedir()
    aplicar()
