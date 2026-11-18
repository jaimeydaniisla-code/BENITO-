# Modelo vs mercado (18/11/2026)
Walk-forward semanal sin fuga, SP1 2021-08 a 2026-11 (2.019 partidos). Scripts: exp_walkforward.py, exp_mercado.py, exp_eval.py, exp_calib.py (en modelo/02_codigo).
Mercado = cuotas de apertura B365 sin margen (potencia), matriz de marcadores ajustada a 1X2 + O/U 2,5.

Logloss medio sobre 20 mercados (test 2023-26, 1.259 partidos): modelo xG 0,5334; mercado 0,5249; mezcla 50 % 0,5271; mezcla 25 % 0,5297; cierre medio 0,5230.
El mercado gana o empata en todos los mercados, incluidos los que no se usan para ajustar (BTTS, líneas 1,5/3,5/4,5, goles por equipo, hándicap +-1,5).
Calibración (2022-26, todos los mercados): modelo sobreestima en 0,5-0,7 (pred 0,55/0,65 -> real 0,525/0,629); mercado calibrado (0,549->0,554; 0,655->0,662; 0,745->0,744; 0,853->0,884; 0,934->0,948: los picks muy probables aciertan algo más de lo previsto).
Quitar margen: potencia 0,9614 vs proporcional 0,9635 (logloss 1X2 B365).
Decisión: con cuotas bwin de 1X2 (vía doble oportunidad) y O/U 2,5 las probabilidades de goles y resultado salen del mercado (modelo_cuotas/mercado.py). Córners y tarjetas siguen con el modelo propio (sin cuotas históricas para validar).
