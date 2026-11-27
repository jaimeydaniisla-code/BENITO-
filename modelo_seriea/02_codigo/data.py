import glob
import numpy as np
import pandas as pd

import os
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '01_datos') + os.sep


def load_e0():   # (nombre heredado de la Premier: aquí carga I1 de Serie A)
    al = []
    for f in sorted(glob.glob(D + 'I1_*.csv')):
        d = pd.read_csv(f, encoding='utf-8-sig')
        d = d.dropna(subset=['HomeTeam', 'FTHG'])
        d['Date'] = pd.to_datetime(d.Date, dayfirst=True)
        if 'Referee' not in d: d['Referee'] = 'sin dato'   # football-data no trae árbitro en Italia (valor fijo: el modelo no lo usa)
        al.append(d)
    df = pd.concat(al, ignore_index=True).sort_values(['Date', 'HomeTeam']).reset_index(drop=True)
    df['season'] = df.Date.apply(lambda x: x.year if x.month >= 7 else x.year - 1)
    df['res'] = np.select([df.FTHG > df.FTAG, df.FTHG == df.FTAG], [0, 1], 2)
    df = df.copy()
    ARB = D + 'arbitros_fotmob.csv'   # árbitros sacados de FotMob (football-data no los trae en Italia)
    if os.path.exists(ARB):
        a = pd.read_csv(ARB).dropna(subset=['Referee'])
        a['Date'] = pd.to_datetime(a.Date); a['season'] = a.Date.apply(lambda x: x.year if x.month >= 7 else x.year - 1)
        a = a.drop_duplicates(['season', 'HomeTeam', 'AwayTeam'])[['season', 'HomeTeam', 'AwayTeam', 'Referee']]
        df = df.drop(columns=['Referee']).merge(a, on=['season', 'HomeTeam', 'AwayTeam'], how='left')
        df['Referee'] = df.Referee.fillna('sin dato')
    return df


def implied(df, h, d, a):
    o = df[[h, d, a]].astype(float).values
    ip = 1 / o
    over = ip.sum(1)
    return ip / over[:, None], over - 1


def logloss(p, y):
    p = np.clip(p, 1e-15, 1)
    return -np.mean(np.log(p[np.arange(len(y)), y]))


def brier(p, y):
    oh = np.eye(3)[y]
    return np.mean(((p - oh) ** 2).sum(1))
