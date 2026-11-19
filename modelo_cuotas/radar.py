"""🎯 Radar de bwin (ocio aparte del fútbol): busca selecciones en las que bwin paga más que la cuota justa de Pinnacle
(Pinnacle sin margen = mejor estimación pública de la probabilidad real). 2 peticiones por escaneo (3 competiciones por petición).
El fútbol tiene prioridad: si el cupo del mes no da para el fútbol que queda, el radar no pide nada."""
import os, sys, json, time, datetime as dt, calendar
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import generar_cuotas as G
from mercado import devig_pot
ROOT = os.path.abspath(os.path.join(HERE, '..')); SAL = os.path.join(ROOT, 'radar.json')
CATR = os.path.join(HERE, 'catalogo_radar.json')
# En OddsPapi, bwin.es solo trae fútbol (comprobado: sin NBA ni NHL). Se rotan grupos de 3 competiciones (máximo por petición).
GRUPOS = {   # tournamentId de OddsPapi: nombre, deporte, fiabilidad (1 = mercado grande y eficiente; 0 = liga menor: se exige más diferencia)
    'B': {18: ('Championship (Inglaterra)', 'Fútbol', 1), 52: ('Süper Lig (Turquía)', 'Fútbol', 0), 37: ('Eredivisie (Países Bajos)', 'Fútbol', 0)},
    'C': {238: ('Primeira Liga (Portugal)', 'Fútbol', 0), 325: ('Brasileirão', 'Fútbol', 0), 955: ('Saudi Pro League', 'Fútbol', 0)},
    'D': {23: ('Serie A (Italia)', 'Fútbol', 1), 35: ('Bundesliga (Alemania)', 'Fútbol', 1), 34: ('Ligue 1 (Francia)', 'Fútbol', 1)},
    # Otros deportes: bwin no está en OddsPapi, así que se usa Winamax (casa "blanda" parecida a bwin) como señal: si paga más que lo justo,
    # el partido es CANDIDATO y la app da la cuota mínima que debe pagar bwin para que sea ganga. Se comprueba en bwin a mano.
    'E': {679: ('Europa League', 'Fútbol', 1), 34480: ('Conference League', 'Fútbol', 0), 18: ('Championship (Inglaterra)', 'Fútbol', 1)},
    'N': {132: ('NBA', 'Baloncesto', 1), 138: ('Euroliga', 'Baloncesto', 1), 234: ('NHL', 'Hockey', 1)},
}
CASA = {'N': 'winamax.es'}          # por defecto bwin.es
VISTOS = {}
MARGEN_GANGA = 0.02                 # cuota mínima en bwin = justa × 1,02
TIPOS = {'1x2': 'Resultado', 'totals': 'Goles', 'bothteamsscore': 'Ambos marcan', 'doublechance': 'Doble oportunidad', 'spreads': 'Hándicap asiático',
         'teamtotals-team1': 'Goles {H}', 'teamtotals-team2': 'Goles {A}', 'totals-corners': 'Córners', 'totals-bookings': 'Tarjetas', 'drawnobet': 'Empate no válido'}
DIAS, EV_MIN, EV_MIN_MENOR, EV_MAX, P_MIN = 1.6, 0.03, 0.05, 0.20, 0.40
FUTBOL_DIA = 7     # peticiones que se reservan para el fútbol por cada día que queda de mes
TRAD = {'Over': 'Más de', 'Under': 'Menos de', 'X': 'Empate', 'Yes': 'Sí', 'No': 'No'}


def grupo_hoy(ahora):
    if os.environ.get('RADAR_GRUPO'): return os.environ['RADAR_GRUPO']
    # Días sin fútbol de la app (lunes a jueves): lun y mié baloncesto/hockey, mar fútbol de otras ligas, jue Europa/Conference League
    return {0: 'N', 1: 'BCD'[ahora.isocalendar()[1] % 3], 2: 'N', 3: 'E'}.get(ahora.weekday(), 'BCD'[ahora.isocalendar()[1] % 3])


def catalogo(sports):
    try: cat = json.load(open(CATR, encoding='utf-8'))
    except Exception: cat = {}
    for sid in sports:
        if str(sid) in cat.get('_deportes', []): continue
        r = G.get('/markets', sportId=sid); r = r.get('data', r) if isinstance(r, dict) else r
        for m in r: cat[str(m['marketId'])] = {'n': m.get('marketName'), 'h': m.get('handicap'), 'p': m.get('period'), 'l': m.get('marketLength'), 'pp': m.get('playerProp'), 't': m.get('marketType'),
                                               'o': {str(o['outcomeId']): o['outcomeName'] for o in m.get('outcomes', [])}}
        cat.setdefault('_deportes', []).append(str(sid)); time.sleep(1.2)
    json.dump(cat, open(CATR, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    return cat


def precios(mk):
    out = {}
    for oid, o in (mk.get('outcomes') or {}).items():
        try:
            pl = list(o['players'].values())[0]
            if float(pl['price']) > 1 and pl.get('active', True): out[str(oid)] = float(pl['price'])
        except Exception: pass
    return out


def tipo_otro(c):
    """Baloncesto/hockey: solo ganador, hándicap y totales del partido completo (con prórroga si la hay). Devuelve el nombre en español o ''."""
    n, t, p = (c.get('n') or ''), (c.get('t') or ''), (c.get('p') or '')
    if p not in ('fulltime', 'result', 'ot', 'incl_ot', 'fulltime_ot', 'match') and 'ot' not in p: return ''
    if any(x in t for x in ('team', 'player', 'corners', 'bookings')): return ''
    if t.startswith(('moneyline', '1x2', 'winner', 'h2h')): return 'Ganador' + (' (con prórroga)' if 'incl' in n.lower() or 'ot' in p else '')
    if t.startswith(('spreads', 'handicap')): return 'Hándicap'
    if t.startswith('totals'): return 'Total del partido'
    return ''


def main():
    ahora = dt.datetime.now(G.MAD); mes = ahora.strftime('%Y-%m')
    if not G.KEY: print('Sin ODDSPAPI_KEY'); return
    real = G.cuenta()
    try: cont = json.load(open(G.CONT))
    except Exception: cont = {}
    gastado = real[0] if real else cont.get(mes, 0); limite = min(G.LIMITE_MES, real[1] - 15) if real else G.LIMITE_MES
    quedan_dias = calendar.monthrange(ahora.year, ahora.month)[1] - ahora.day + 1
    reserva = quedan_dias * FUTBOL_DIA
    if limite - gastado - 2 < reserva:
        print(f'Radar en pausa: quedan {limite - gastado} peticiones y el fútbol necesita ~{reserva} hasta fin de mes')
        try: R = json.load(open(SAL, encoding='utf-8'))
        except Exception: R = {}
        R.setdefault('esc', {}); R['pausa'] = f'En pausa hasta el mes que viene para no quitarle peticiones al fútbol ({gastado}/{limite} usadas).'
        json.dump(R, open(SAL, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':')); return
    g = grupo_hoy(ahora); comps = GRUPOS[g]
    casa = CASA.get(g, 'bwin.es')
    bw = G.lote(casa, list(comps)); time.sleep(1.2); pn = G.lote('pinnacle', list(comps))
    pnd = {f['fixtureId']: f for f in pn}
    cat = catalogo(sorted({f.get('sportId') for f in bw + pn if f.get('sportId') and f.get('sportId') != 10}))
    try: cat10 = {str(k): {'n': v.get('marketName'), 'h': v.get('handicap'), 'p': v.get('period'), 'l': v.get('marketLength'), 'pp': v.get('playerProp'), 't': v.get('marketType'),
                           'o': {str(o['outcomeId']): o['outcomeName'] for o in v.get('outcomes', [])}} for k, v in json.load(open(os.path.join(HERE, 'catalogo_mercados.json'), encoding='utf-8')).items()}
    except Exception: cat10 = {}
    picks, eventos = [], 0
    for f in bw:
        p = pnd.get(f.get('fixtureId'))
        try: ko = dt.datetime.fromisoformat(f['startTime'].replace('Z', '+00:00')).astimezone(G.MAD)
        except Exception: continue
        if not p or not (ahora < ko <= ahora + dt.timedelta(days=DIAS)): continue
        eventos += 1
        nombre, dep, fiab = comps.get(int(f.get('tournamentId') or 0), ('?', '?', 0))
        H, A = f.get('participant1Name') or 'Local', f.get('participant2Name') or 'Visitante'
        mb, mp = (f.get('bookmakerOdds') or {}).get(casa, {}).get('markets', {}), (p.get('bookmakerOdds') or {}).get('pinnacle', {}).get('markets', {})
        mejor = None
        for mid, v in mb.items():
            c = (cat10 if f.get('sportId') == 10 else cat).get(str(mid))
            if not c or c.get('pp') or mid not in mp: continue
            if f.get('sportId') == 10 and (c.get('p') != 'fulltime' or c.get('t') not in TIPOS): continue
            if f.get('sportId') != 10: VISTOS[(c.get('t'), c.get('p'))] = VISTOS.get((c.get('t'), c.get('p')), 0) + 1
            if f.get('sportId') != 10 and not tipo_otro(c): continue
            pb, pp = precios(v), precios(mp[mid])
            if not c.get('l') or len(pp) != c['l'] or len(pp) < 2: continue      # hace falta el mercado completo en Pinnacle para quitar su margen
            ks = list(pp); jus = dict(zip(ks, devig_pot([pp[k] for k in ks])))
            for oid, cb in pb.items():
                if oid not in jus: continue
                pr = float(jus[oid]); ev = cb * pr - 1
                if pr >= P_MIN and ((0.015 if g == 'N' else EV_MIN) if fiab else EV_MIN_MENOR) <= ev <= EV_MAX and (not mejor or ev > mejor['ev']):
                    o0 = c['o'].get(oid, oid); on = o0; on = {'1': H, '2': A, '1X': H + ' o empate', 'X2': 'Empate o ' + A, '12': 'No hay empate'}.get(on, TRAD.get(on, on))
                    h = c.get('h'); hs = str(h).replace('.', ',') if h not in (None, '') else ''
                    lin = f" {hs}" if hs and on.startswith(('Más', 'Menos')) else (f" ({'+' if hv > 0 else ''}{str(hv).replace('.', ',')})" if c.get('t') == 'spreads' and hs and (hv := float(h) * (-1 if o0 == '2' else 1)) is not None else '')
                    mejor = {'dep': dep, 'comp': nombre, 'h': H, 'a': A, 'ko': ko.strftime('%Y-%m-%dT%H:%M'), 'mer': (TIPOS[c['t']].format(H=H, A=A) if f.get('sportId') == 10 else tipo_otro(c)), 'casa': casa,
                             'min': round(1 / pr * (1 + MARGEN_GANGA), 2), 'per': c.get('p'),
                             'sel': on + lin, 'p': round(pr, 3), 'justa': round(1 / pr, 2), 'bw': cb, 'ev': round(ev, 3), 'fiab': fiab}
        if mejor: picks.append(mejor)
    picks.sort(key=lambda x: -x['ev'])
    try: R = json.load(open(SAL, encoding='utf-8'))
    except Exception: R = {}
    R.setdefault('esc', {})['N' if g == 'N' else 'F'] = {'act': ahora.strftime('%d/%m %H:%M'), 'grupo': g, 'casa': casa, 'comps': [v[0] for v in comps.values()],
                                                        'eventos': eventos, 'picks': picks[:25]}
    R['pausa'] = None; R['pet'] = f'{gastado + G.usadas}/{limite}'
    for k in ('act', 'grupo', 'comps', 'eventos', 'picks'): R.pop(k, None)
    json.dump(R, open(SAL, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    cont[mes] = gastado + G.usadas; json.dump(cont, open(G.CONT, 'w'))
    print(f'Radar {g}: {eventos} eventos con bwin y Pinnacle, {len(picks)} con valor; peticiones usadas {G.usadas} (mes {gastado + G.usadas}/{limite})')
    if VISTOS: print('Mercados comunes (tipo, periodo):', sorted(VISTOS.items(), key=lambda z: -z[1])[:20])
    for x in picks[:10]: print('  ', x['dep'], x['comp'], x['h'], '-', x['a'], x['ko'], '|', x['mer'], '|', x['sel'], x['casa'], x['bw'], 'justa', x['justa'], 'mín. bwin', x['min'], f"+{round(x['ev'] * 100)} %")


if __name__ == '__main__':
    main()
