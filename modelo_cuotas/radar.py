"""🎯 Radar de bwin (ocio aparte del fútbol): busca selecciones en las que bwin paga más que la cuota justa de Pinnacle
(Pinnacle sin margen = mejor estimación pública de la probabilidad real). 2 peticiones por escaneo (3 competiciones por petición).
El fútbol tiene prioridad: si el cupo del mes no da para el fútbol que queda, el radar no pide nada."""
import os, sys, json, time, datetime as dt, calendar
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import generar_cuotas as G
from mercado import devig_pot
ROOT = os.path.abspath(os.path.join(HERE, '..')); SAL = os.path.join(ROOT, 'radar.json')
CATR = os.path.join(HERE, 'catalogo_radar.json')
GRUPOS = {   # tournamentId de OddsPapi: nombre, deporte, fiabilidad (1 = mercado grande y eficiente; 0 = liga menor: se exige más diferencia)
    'A': {132: ('NBA', 'Baloncesto', 1), 138: ('Euroliga', 'Baloncesto', 1), 234: ('NHL', 'Hockey', 1)},
    'B': {18: ('Championship (Inglaterra)', 'Fútbol', 1), 52: ('Süper Lig (Turquía)', 'Fútbol', 0), 37: ('Eredivisie (Países Bajos)', 'Fútbol', 0)},
    'C': {238: ('Primeira Liga (Portugal)', 'Fútbol', 0), 325: ('Brasileirão', 'Fútbol', 0), 955: ('Saudi Pro League', 'Fútbol', 0)},
}
DIAS, EV_MIN, EV_MIN_MENOR, EV_MAX, P_MIN = 4, 0.03, 0.05, 0.20, 0.40
FUTBOL_DIA = 7     # peticiones que se reservan para el fútbol por cada día que queda de mes
TRAD = {'Over': 'Más de', 'Under': 'Menos de', 'X': 'Empate', 'Yes': 'Sí', 'No': 'No'}


def grupo_hoy(ahora):
    if os.environ.get('RADAR_GRUPO'): return os.environ['RADAR_GRUPO']
    if ahora.weekday() in (0, 1, 2): return 'A'                            # lun-mié: baloncesto y hockey
    return 'B' if ahora.isocalendar()[1] % 2 == 0 else 'C'                # jue-dom: fútbol, alternando semanas


def catalogo(sports):
    try: cat = json.load(open(CATR, encoding='utf-8'))
    except Exception: cat = {}
    for sid in sports:
        if str(sid) in cat.get('_deportes', []): continue
        r = G.get('/markets', sportId=sid); r = r.get('data', r) if isinstance(r, dict) else r
        for m in r: cat[str(m['marketId'])] = {'n': m.get('marketName'), 'h': m.get('handicap'), 'p': m.get('period'), 'l': m.get('marketLength'), 'pp': m.get('playerProp'),
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
        R['pausa'] = f'En pausa hasta el mes que viene para no quitarle peticiones al fútbol ({gastado}/{limite} usadas).'
        json.dump(R, open(SAL, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':')); return
    g = grupo_hoy(ahora); comps = GRUPOS[g]
    bw = G.lote('bwin.es', list(comps)); time.sleep(1.2); pn = G.lote('pinnacle', list(comps))
    pnd = {f['fixtureId']: f for f in pn}
    cat = catalogo(sorted({f.get('sportId') for f in bw + pn if f.get('sportId') and f.get('sportId') != 10}))
    try: cat10 = {str(k): {'n': v.get('marketName'), 'h': v.get('handicap'), 'p': v.get('period'), 'l': v.get('marketLength'), 'pp': v.get('playerProp'),
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
        mb, mp = (f.get('bookmakerOdds') or {}).get('bwin.es', {}).get('markets', {}), (p.get('bookmakerOdds') or {}).get('pinnacle', {}).get('markets', {})
        mejor = None
        for mid, v in mb.items():
            c = (cat10 if f.get('sportId') == 10 else cat).get(str(mid))
            if not c or c.get('pp') or mid not in mp: continue
            pb, pp = precios(v), precios(mp[mid])
            if not c.get('l') or len(pp) != c['l'] or len(pp) < 2: continue      # hace falta el mercado completo en Pinnacle para quitar su margen
            ks = list(pp); jus = dict(zip(ks, devig_pot([pp[k] for k in ks])))
            for oid, cb in pb.items():
                if oid not in jus: continue
                pr = float(jus[oid]); ev = cb * pr - 1
                if pr >= P_MIN and (EV_MIN if fiab else EV_MIN_MENOR) <= ev <= EV_MAX and (not mejor or ev > mejor['ev']):
                    on = c['o'].get(oid, oid); on = {'1': H, '2': A}.get(on, TRAD.get(on, on))
                    h = c.get('h'); lin = f" {str(h).replace('.', ',')}" if h not in (None, 0, 0.0) and on.startswith(('Más', 'Menos')) else ''
                    mejor = {'dep': dep, 'comp': nombre, 'h': H, 'a': A, 'ko': ko.strftime('%Y-%m-%dT%H:%M'), 'mer': c.get('n') or '', 'per': c.get('p'),
                             'sel': on + lin, 'p': round(pr, 3), 'justa': round(1 / pr, 2), 'bw': cb, 'ev': round(ev, 3), 'fiab': fiab}
        if mejor: picks.append(mejor)
    picks.sort(key=lambda x: -x['ev'])
    R = {'act': ahora.strftime('%d/%m %H:%M'), 'grupo': g, 'comps': [v[0] for v in comps.values()], 'eventos': eventos, 'picks': picks[:25], 'pausa': None,
         'pet': f'{gastado + G.usadas}/{limite}'}
    json.dump(R, open(SAL, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    cont[mes] = gastado + G.usadas; json.dump(cont, open(G.CONT, 'w'))
    print(f'Radar {g}: {eventos} eventos con bwin y Pinnacle, {len(picks)} con valor; peticiones usadas {G.usadas} (mes {gastado + G.usadas}/{limite})')
    for x in picks[:10]: print('  ', x['dep'], x['comp'], x['h'], '-', x['a'], x['ko'], '|', x['mer'], '|', x['sel'], x['bw'], 'justa', x['justa'], f"+{round(x['ev'] * 100)} %")


if __name__ == '__main__':
    main()
