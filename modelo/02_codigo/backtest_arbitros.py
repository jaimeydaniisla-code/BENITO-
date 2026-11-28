"""La Liga: tarjetas sin y con árbitro (historial de FotMob), walk-forward sin mirar el futuro, test 2023-26."""
import os, json
import generar_datos  # noqa: fija LALIGA_DATA al histórico del repo
from backtest_counts import prep, run, evaluate
from analizar_partido import CFG_TARJETAS

d = prep()
print('Partidos SP1:', len(d), '| con árbitro:', int(d.Referee.notna().sum()), '| árbitros:', d.Referee.nunique())
res = {}
for nombre, cfg in (('sin_arbitro', dict(CFG_TARJETAS, use_ref=False)), ('arbitro_reg20', dict(CFG_TARJETAS, use_ref=True, reg_ref=20)),
                    ('arbitro_reg40', dict(CFG_TARJETAS, use_ref=True, reg_ref=40)), ('arbitro_reg80', dict(CFG_TARJETAS, use_ref=True, reg_ref=80))):
    P = run(d, 'HK', 'AK', first=2023, **cfg); e = evaluate(P, [3.5, 4.5, 5.5, 6.5])
    res[nombre] = {k: round(float(v), 4) for k, v in e.items()}; print('tarjetas', nombre, res[nombre])
json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '03_experimentos', 'backtest_arbitros.json'), 'w'), indent=1)
