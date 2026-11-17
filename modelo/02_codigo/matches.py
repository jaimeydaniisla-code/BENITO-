"""Tabla maestra de La Liga: football-data SP1 (goles, estadísticas, cuotas).
xG: football-data solo trae HxG/AxG en 2026-27. Si existe 01_datos/xg_understat.csv
(season, HomeTeam, AwayTeam, xG_h, xG_a) se usa para completar temporadas anteriores.
Donde no hay xG, el objetivo del modelo es el número de goles (w=1 de facto)."""
import os
import numpy as np
import pandas as pd
from data import load_sp1, load_sp2

XG_EXTRA = os.environ.get('LALIGA_XG', os.path.join(os.path.dirname(__file__), '..', '01_datos', 'xg_understat.csv'))


def load_matches():
    m = load_sp1()
    m['xG_h'] = m.get('HxG'); m['xG_a'] = m.get('AxG')
    if os.path.exists(XG_EXTRA):
        x = pd.read_csv(XG_EXTRA)
        m = m.merge(x[['season', 'HomeTeam', 'AwayTeam', 'xG_h', 'xG_a']], on=['season', 'HomeTeam', 'AwayTeam'],
                    how='left', suffixes=('', '_us'))
        # Understat primero (fuente homogénea 2019-2026); HxG de football-data solo si falta
        m['xG_h'] = m.xG_h_us.fillna(m.xG_h); m['xG_a'] = m.xG_a_us.fillna(m.xG_a)
        m = m.drop(columns=['xG_h_us', 'xG_a_us'])
    m['has_xg'] = m.xG_h.notna() & m.xG_a.notna()
    m['HK'] = m.HY + m.HR; m['AK'] = m.AY + m.AR
    return m


def promoted_in(m, season):
    teams = {s: set(g.HomeTeam) for s, g in m.groupby('season')}
    if season - 1 not in teams:
        return set()
    return teams[season] - teams[season - 1]


def sp2_check(m):
    """Comprueba que los ascendidos de cada temporada aparecen en SP2 la temporada anterior."""
    s2 = load_sp2(); t2 = {s: set(g.HomeTeam) for s, g in s2.groupby('season')}
    out = {}
    for s in sorted(m.season.unique()):
        pr = promoted_in(m, s)
        if pr:
            out[s] = {t: (t in t2.get(s - 1, set())) for t in pr}
    return out
