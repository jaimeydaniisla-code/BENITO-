"""Vuelve a aplicar a datos.json solo las cuotas de cuotas.json más nuevas que las que ya tiene cada partido (idempotente)."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import mercado
ROOT = os.path.abspath(os.path.join(HERE, '..'))
cu = json.load(open(os.path.join(ROOT, 'cuotas.json'), encoding='utf-8'))
app = json.load(open(os.path.join(ROOT, 'datos.json'), encoding='utf-8')); n = 0
for liga, L in app.get('ligas', {}).items():
    for j in L.get('jor', []):
        for m in j['ms']:
            v = cu.get(f"{liga}|{m['d']}|{m['h']}|{m['a']}")
            if v and v['act'] != m.get('bwact'):
                m['bw'], m['bwact'] = v['bw'], v['act']
                if v.get('pin'): m['pin'] = v['pin']
                try: mercado.ajustar(m); n += 1
                except Exception as e: print('ajuste falló', m['h'], m['a'], e)
json.dump(app, open(os.path.join(ROOT, 'datos.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print('cuotas previas reaplicadas a', n, 'partidos')
