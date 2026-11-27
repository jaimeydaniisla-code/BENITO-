"""Tabla maestra de partidos: football-data (goles, estadísticas, cuotas) + xG de Understat.
Añade los partidos jugados que aún no están en football-data (solo goles y xG)."""
import numpy as np
import pandas as pd
from data import load_e0

import os
US = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '01_datos', 'partidos_xg.csv')


def load_matches():
    df = load_e0()
    if not os.path.exists(US):   # Serie A: sin xG de Understat guardado -> el modelo usa los goles (Dixon-Coles clásico)
        m = df.copy(); m['source'] = 'football-data'
        m['xG_h'] = m.FTHG.astype(float); m['xG_a'] = m.FTAG.astype(float)
        teams = {s: set(g.HomeTeam) for s, g in m.groupby('season')}
        m['promoted_h'] = [s - 1 in teams and h not in teams[s - 1] for s, h in zip(m.season, m.HomeTeam)]
        m['promoted_a'] = [s - 1 in teams and a not in teams[s - 1] for s, a in zip(m.season, m.AwayTeam)]
        return m
    us = pd.read_csv(US, parse_dates=['Date'])
    m = df.merge(us[['season', 'HomeTeam', 'AwayTeam', 'xG_h', 'xG_a', 'us_pH', 'us_pD', 'us_pA']],
                 on=['season', 'HomeTeam', 'AwayTeam'], how='left')
    extra = us.merge(df[['season', 'HomeTeam', 'AwayTeam']], how='left', indicator=True,
                     on=['season', 'HomeTeam', 'AwayTeam']).query('_merge=="left_only"')
    extra = extra.rename(columns={'us_hg': 'FTHG', 'us_ag': 'FTAG'})[
        ['Date', 'season', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'xG_h', 'xG_a', 'us_pH', 'us_pD', 'us_pA']]
    extra['source'] = 'understat_only'
    m['source'] = 'football-data'
    m = pd.concat([m, extra], ignore_index=True).sort_values(['Date', 'HomeTeam']).reset_index(drop=True)
    m['res'] = np.select([m.FTHG > m.FTAG, m.FTHG == m.FTAG], [0, 1], 2)
    # partidos recientes sin xG de Understat: xG de football-data (HxG/AxG) y, si falta, los goles
    if 'HxG' in m: m['xG_h'] = m.xG_h.fillna(m.HxG); m['xG_a'] = m.xG_a.fillna(m.AxG)
    m['xG_h'] = m.xG_h.fillna(m.FTHG); m['xG_a'] = m.xG_a.fillna(m.FTAG)
    # equipos recién ascendidos: no estaban en la temporada anterior
    teams = {s: set(g.HomeTeam) for s, g in m.groupby('season')}
    m['promoted_h'] = [s - 1 in teams and h not in teams[s - 1] for s, h in zip(m.season, m.HomeTeam)]
    m['promoted_a'] = [s - 1 in teams and a not in teams[s - 1] for s, a in zip(m.season, m.AwayTeam)]
    return m


def promoted_in(m, season):
    teams = {s: set(g.HomeTeam) for s, g in m.groupby('season')}
    if season - 1 not in teams:
        return set()
    return teams[season] - teams[season - 1]
