"""Cuotas de bwin.es vía OddsPapi (clave ODDSPAPI_KEY). Pocas peticiones: solo partidos de los próximos N días.
Guarda cuotas.json y aplica 'bw' a datos.json. Uso: python generar_cuotas.py [--aplicar-solo]"""
import os, sys, time, json, difflib, unicodedata, datetime as dt, urllib.request, urllib.parse
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
TORNEOS = {'primera': 8, 'segunda': 54, 'premier': 17, 'champions': 7}          # OddsPapi tournamentId (selecciones: se pide aparte con --selecciones ID)
DIAS = int(os.environ.get('CUOTAS_DIAS', '4'))
LIGAS_PEDIR = [x for x in (os.environ.get('CUOTAS_LIGAS') or 'primera,segunda,premier,champions').split(',') if x.strip() in TORNEOS]   # con el lote de OddsPapi (1 petición) caben todas las ligas
MAXPET = int(os.environ.get('CUOTAS_MAXPET', '40'))
PIN = os.environ.get('CUOTAS_PIN', '') == '1'   # pedir también Pinnacle (referencia de probabilidad; +1 petición)
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
    a, b = nz(a or ''), nz(b or '')
    if not a or not b: return 0.0
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
            if 'X' in pr: out['Empate'] = pr['X']
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


def cuenta():
    """Contador real de OddsPapi (/v4/account es gratis). Devuelve (usadas, limite) o None."""
    try:
        u = 'https://api.oddspapi.io/v4/account?' + urllib.parse.urlencode({'apiKey': KEY})
        r = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'benitooo'}), timeout=30).read().decode())
        def busca(o, k):
            if isinstance(o, dict):
                if k in o and isinstance(o[k], (int, float)): return o[k]
                for v in o.values():
                    x = busca(v, k)
                    if x is not None: return x
            elif isinstance(o, list):
                for v in o:
                    x = busca(v, k)
                    if x is not None: return x
        u_, l_ = busca(r, 'request_count'), busca(r, 'request_limit')
        print('Contador real OddsPapi:', u_, '/', l_)
        return (int(u_), int(l_)) if u_ is not None and l_ is not None else None
    except Exception as e:
        print('AVISO contador real no disponible:', repr(e)[:80]); return None


PART = os.path.join(HERE, 'participantes.json')   # id -> nombre (OddsPapi solo da números en los lotes); se guarda solo lo usado


def nombres(fixtures):
    """Pone participant1Name/participant2Name a cada partido. Si falta algún equipo, 1 petición a /participants de ese deporte."""
    try: P = json.load(open(PART, encoding='utf-8'))
    except Exception: P = {}
    faltan = {}
    for f in fixtures:
        for k in ('participant1Id', 'participant2Id'):
            if f.get(k) is not None and str(f[k]) not in P: faltan.setdefault(f.get('sportId') or 10, set()).add(str(f[k]))
    for sid, ids in faltan.items():
        try:
            time.sleep(1.2); r = get('/participants', sportId=sid)
            if isinstance(r, list): r = {str(x.get('participantId')): x.get('name') for x in r}
            r = r.get('data', r) if isinstance(r, dict) and 'data' in r else r
            n = 0
            for i in ids:
                if r.get(i): P[i] = r[i]; n += 1
            print(f'Nombres de equipos: {n}/{len(ids)} nuevos (deporte {sid})')
        except Exception as e:
            print('AVISO nombres de equipos no disponibles:', repr(e)[:100])
    json.dump(P, open(PART, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    for f in fixtures:
        f['participant1Name'] = f.get('participant1Name') or P.get(str(f.get('participant1Id')))
        f['participant2Name'] = f.get('participant2Name') or P.get(str(f.get('participant2Id')))
    return fixtures


def lote(bookmaker, ids):
    """Cuotas de varias competiciones. OddsPapi admite como mucho 3 competiciones por petición: se trocea."""
    out, ok = [], False
    ids = [str(i) for i in ids]
    for n in range(0, len(ids), 3):
        if n: time.sleep(1.2)
        try:
            r = get('/odds-by-tournaments', tournamentIds=','.join(ids[n:n + 3]), bookmaker=bookmaker)
            r = r.get('data', r) if isinstance(r, dict) else r
            if isinstance(r, list): out += r; ok = True
        except Exception as e:
            print('AVISO lote', bookmaker, ids[n:n + 3], repr(e)[:100])
    if not ok: raise ValueError('lote sin respuesta')
    return nombres(out)


def pedir():
    if not KEY:
        print('Sin ODDSPAPI_KEY'); return
    app = json.load(open(DATOS, encoding='utf-8')); ahora = dt.datetime.now(MAD)
    mes = ahora.strftime('%Y-%m')
    try: cont = json.load(open(CONT))
    except Exception: cont = {}
    gastado = cont.get(mes, BASE_MES.get(mes, 0)); limite = LIMITE_MES
    real = cuenta()
    if real: gastado, limite = real[0], min(LIMITE_MES, real[1] - 15)     # se deja un margen de 15 por si acaso
    if gastado >= limite:
        print(f'Límite mensual de peticiones alcanzado ({gastado}/{limite}): no se piden cuotas'); return
    global MAXPET
    MAXPET = min(MAXPET, limite - gastado)
    def ko(m): return dt.datetime.fromisoformat(m['d'] + 'T' + (m.get('t') or '23:59')).replace(tzinfo=MAD)
    def ventana(liga):
        jor = app.get('ligas', {}).get(liga, {}).get('jor', [])
        ms = [m for j in jor for m in j['ms'] if ahora.date().isoformat() <= m['d'] <= (ahora + dt.timedelta(days=DIAS)).date().isoformat()]
        if HORAS > 0: ms = [m for m in ms if ahora <= ko(m) <= ahora + dt.timedelta(hours=HORAS)]
        return ms
    ligas = [l for l in LIGAS_PEDIR if ventana(l)]
    if not ligas:
        print('Sin partidos en la ventana: no se gasta ninguna petición'); return
    CATF = os.path.join(HERE, 'catalogo_mercados.json')   # el catálogo de mercados casi no cambia: se pide una sola vez y se guarda
    try: cat = {int(k): v for k, v in json.load(open(CATF, encoding='utf-8')).items()}
    except Exception:
        cat = {m['marketId']: m for m in (lambda r: r.get('data', r) if isinstance(r, dict) else r)(get('/markets', sportId=10))}
        json.dump(cat, open(CATF, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    try: cu = json.load(open(CUOTAS, encoding='utf-8'))
    except Exception: cu = {}
    # 1) Lote: UNA petición con las cuotas de bwin de todos los partidos próximos de las ligas pedidas
    lote_ = None
    try:
        lote_ = lote('bwin.es', [TORNEOS[l] for l in ligas])   # lista vacía = bwin aún sin cuotas: no se gasta más
        print('Lote OddsPapi:', len(lote_), 'partidos en total')
    except Exception as e:
        print('AVISO lote no disponible, se usa la vía partido a partido solo para', ligas[0], '->', repr(e)[:100]); lote_ = None; ligas = ligas[:1]
    pin = {}
    if PIN and lote_ is not None and limite - gastado - usadas >= 30:   # con poco cupo, se prioriza bwin
        try:
            time.sleep(1.5)
            for f in lote('pinnacle', [TORNEOS[l] for l in ligas]):
                mk_ = (f.get('bookmakerOdds') or {}).get('pinnacle', {}).get('markets')
                if mk_: pin[f.get('fixtureId')] = mk_
            print('Pinnacle:', len(pin), 'partidos')
        except Exception as e:
            print('AVISO Pinnacle no disponible:', repr(e)[:100])
    elif PIN: print('Pinnacle omitido para ahorrar cupo')
    for liga in ligas:
        tid = TORNEOS[liga]; ms = ventana(liga)
        if lote_ is not None:
            fx = [f for f in lote_ if f.get('tournamentId') in (tid, str(tid)) or f.get('tournamentId') is None]
        else:
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
                try: k0 = dt.datetime.fromisoformat((f.get('startTime') or '').replace('Z', '+00:00')).astimezone(MAD)
                except Exception: continue
                if k0.date().isoformat() != m['d'] or (lote_ is None and not f.get('hasOdds')): continue
                s = sim(m['h'], f.get('participant1Name', '')) + sim(m['a'], f.get('participant2Name', ''))
                if s > bs: mejor, bs = f, s
            if not mejor or bs < 1.2:
                sin += 1; print('  sin casar:', liga, m['h'], m['a'], m['d'], round(bs, 2)); continue
            try:
                if lote_ is not None: mk = mejor['bookmakerOdds']['bwin.es']['markets']
                else: mk = get('/odds', fixtureId=mejor['fixtureId'], bookmaker='bwin.es')['bookmakerOdds']['bwin.es']['markets']
            except Exception as e:
                print('  sin cuotas:', m['h'], m['a'], repr(e)[:80]); continue
            et = etiquetas(cat, mk, m['h'], m['a'])
            if et:
                cu[f"{liga}|{m['d']}|{m['h']}|{m['a']}"] = {'act': ahora.strftime('%d/%m %H:%M'), 'bw': et}; n += 1
                if mejor.get('fixtureId') in pin:
                    ep = etiquetas(cat, pin[mejor['fixtureId']], m['h'], m['a'])
                    if ep: cu[f"{liga}|{m['d']}|{m['h']}|{m['a']}"]['pin'] = ep
                with open(HIST, 'a', encoding='utf-8') as fh:
                    fh.write(json.dumps({'t': ahora.isoformat(timespec='minutes'), 'liga': liga, 'd': m['d'], 'hora': m.get('t'), 'h': m['h'], 'a': m['a'], 'bw': et, 'pin': cu[f"{liga}|{m['d']}|{m['h']}|{m['a']}"].get('pin')},
                                        ensure_ascii=False, separators=(',', ':')) + '\n')
        print(f'{liga}: {n} partidos con cuotas, {sin} sin casar')
    json.dump(cu, open(CUOTAS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('peticiones usadas en esta pasada:', usadas)
    cont[mes] = gastado + usadas; json.dump(cont, open(CONT, 'w'))
    print(f'peticiones del mes: {cont[mes]}/{limite}')


SIN_TARJETAS = {'segunda'}


def aplicar():
    cu = json.load(open(CUOTAS, encoding='utf-8')) if os.path.exists(CUOTAS) else {}
    app = json.load(open(DATOS, encoding='utf-8')); k = aj = 0
    for liga, L in app.get('ligas', {}).items():
        for j in L['jor']:
            for m in j['ms']:
                if liga in SIN_TARJETAS:   # bwin no ofrece apuestas de tarjetas en esta liga: no se pronostican
                    m['s'] = [x for x in m.get('s') or [] if x[1] != 'tar']; m['notar'] = 1
                v = cu.get(f"{liga}|{m['d']}|{m['h']}|{m['a']}")
                if v:
                    m['bw'] = v['bw']; m['bwact'] = v['act']; k += 1
                    if v.get('pin'): m['pin'] = v['pin']
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
