"""Rendimiento real del modelo: compara los picks que propuso la app (picks_log.jsonl, ~45 min antes de cada partido)
con los resultados reales. Escribe rendimiento.json para la app. Sin cuotas ni claves."""
import os, re, json, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..'))
LOG, RES, SAL, DATOS = os.path.join(HERE, 'picks_log.jsonl'), os.path.join(HERE, 'picks_resueltos.json'), os.path.join(ROOT, 'rendimiento.json'), os.path.join(ROOT, 'datos.json')


def evaluar(lab, H, A, r):
    hg, ag = r[3], r[4]; hc, ac, hk, ak = (r[5:9] + [None] * 4)[:4] if len(r) > 5 else (None,) * 4
    num = lambda s: float(s.replace(',', '.'))
    if re.match(r'^(Córners|Tarjetas|Más córners)', lab) and hc is None: return None
    if lab == 'Ambos marcan: Sí': return hg > 0 and ag > 0
    if lab == 'Ambos marcan: No': return not (hg > 0 and ag > 0)
    m = re.match(r'^(Goles|Córners|Tarjetas)(?: (.+))?: (más|menos) de (\d+,\d)$', lab)
    if m:
        p = [hg, ag] if m[1] == 'Goles' else [hc, ac] if m[1] == 'Córners' else [hk, ak]
        if None in p: return None
        v = p[0] + p[1] if not m[2] else p[0] if m[2] == H else p[1] if m[2] == A else None
        if v is None: return None
        return v > num(m[4]) if m[3] == 'más' else v < num(m[4])
    m = re.match(r'^Más córners: (.+)$', lab)
    if m: return (hc > ac) if m[1] == H else (ac > hc) if m[1] == A else None
    t = {H + ' o empate': hg >= ag, 'Empate o ' + A: ag >= hg, 'No hay empate': hg != ag, 'Gana ' + H: hg > ag, 'Gana ' + A: ag > hg,
         H + ' +1,5 (no pierde por 2)': hg - ag >= -1, A + ' +1,5 (no pierde por 2)': ag - hg >= -1, H + ' gana por 2 o más': hg - ag >= 2,
         A + ' gana por 2 o más': ag - hg >= 2, H + ' gana sin encajar': hg > 0 and ag == 0, A + ' gana sin encajar': ag > 0 and hg == 0}
    if lab in t: return t[lab]
    if lab == H + ' (empate no válido)': return 'N' if hg == ag else hg > ag
    if lab == A + ' (empate no válido)': return 'N' if hg == ag else ag > hg
    return None


def main():
    if not os.path.exists(LOG): print('Rendimiento: aún no hay picks registrados'); return
    picks = {}
    for ln in open(LOG, encoding='utf-8'):
        try: x = json.loads(ln)
        except Exception: continue
        picks[f"{x['liga']}|{x['d']}|{x['h']}|{x['a']}"] = x          # vale el último registro de cada partido
    try: hechos = json.load(open(RES, encoding='utf-8'))
    except Exception: hechos = {}
    app = json.load(open(DATOS, encoding='utf-8'))
    for k, x in picks.items():
        if k in hechos: continue
        for r in (app.get('ligas', {}).get(x['liga'], {}).get('res') or []):
            if r[1] == x['h'] and r[2] == x['a'] and r[0] >= x['d']:
                hechos[k] = [[lab, cat, p, o, evaluar(lab, x['h'], x['a'], r), 1 if lab == x.get('top') else 0] for lab, cat, p, o in x['ps']]
                hechos[k] = [z for z in hechos[k] if z[4] is not None]
                break
    json.dump(hechos, open(RES, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    def acum(): return {'n': 0, 'ok': 0, 'p': 0.0, 'nc': 0, 'ben': 0.0}
    cat, liga, franja, top = {}, {}, {}, acum()
    def suma(o, z):
        o['n'] += 1; ok = z[4] is True; o['ok'] += ok; o['p'] += z[2]
        if z[3] and z[4] != 'N': o['nc'] += 1; o['ben'] += (z[3] - 1) if ok else -1
    for k, L in hechos.items():
        lg = k.split('|')[0]
        for z in L:
            if z[4] == 'N': continue
            suma(cat.setdefault(z[1], acum()), z); suma(liga.setdefault(lg, acum()), z)
            b = min(int(z[2] * 10), 9); suma(franja.setdefault(f'{b * 10}-{b * 10 + 9} %' if b < 9 else '90 %+', acum()), z)
            if z[5]: suma(top, z)
    fmt = lambda o: {'n': o['n'], 'acierto': round(o['ok'] / o['n'], 3) if o['n'] else None, 'p_media': round(o['p'] / o['n'], 3) if o['n'] else None,
                     'n_cuota': o['nc'], 'roi': round(o['ben'] / o['nc'], 3) if o['nc'] else None}
    out = {'act': dt.datetime.now(__import__('zoneinfo').ZoneInfo('Europe/Madrid')).strftime('%d/%m %H:%M'), 'partidos': len(hechos), 'pendientes': len(picks) - len(hechos), 'top': fmt(top),
           'cat': {k: fmt(v) for k, v in cat.items()}, 'liga': {k: fmt(v) for k, v in liga.items()}, 'franja': {k: fmt(v) for k, v in sorted(franja.items())}}
    json.dump(out, open(SAL, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('Rendimiento:', len(hechos), 'partidos resueltos,', out['pendientes'], 'pendientes; mejor pick', out['top'])


if __name__ == '__main__':
    main()
