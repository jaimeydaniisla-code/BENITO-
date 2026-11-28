"""Carga de datos football-data.co.uk para La Liga (SP1) y Segunda (SP2).
Ruta por defecto: carpeta de adjuntos del proyecto; se puede cambiar con la variable de entorno LALIGA_DATA."""
import glob, os
import numpy as np
import pandas as pd

D = os.environ.get('LALIGA_DATA', '/mnt/user-data/attachments/03573891-f6b9-5fb6-a834-744d8f6cad0e/')


def _load(div):
    al = []
    extra = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '01_datos')
    files = sorted(glob.glob(os.path.join(extra, f'{div}_*.csv'))) + sorted(glob.glob(os.path.join(D, f'*{div}*.csv')))
    for f in files:  # 01_datos (actualizados) primero: en duplicados se queda la versión nueva
        d = pd.read_csv(f, encoding='utf-8-sig')
        d = d[d.Div == div].dropna(subset=['HomeTeam', 'FTHG'])
        d['Date'] = pd.to_datetime(d.Date, dayfirst=True)
        d = d.copy()
        d['season'] = d.Date.min().year  # temporada = año de inicio del archivo (2019-20 acabó en julio)
        al.append(d)
    df = pd.concat(al, ignore_index=True)
    df = df.drop_duplicates(['Date', 'HomeTeam', 'AwayTeam']).sort_values(['Date', 'HomeTeam']).reset_index(drop=True).copy()
    df['res'] = np.select([df.FTHG > df.FTAG, df.FTHG == df.FTAG], [0, 1], 2)
    return df


def load_sp1():
    df = _load('SP1')
    ARB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '01_datos', 'arbitros_fotmob.csv')
    if os.path.exists(ARB):   # árbitros sacados de FotMob (football-data no los trae en España)
        a = pd.read_csv(ARB)
        a = a[a.Referee.notna() & (a.Referee != 'sin dato')]
        temp = lambda x: x.dt.year.where(x.dt.month >= 7, x.dt.year - 1)
        a['tt'] = temp(pd.to_datetime(a.Date)); df['tt'] = temp(df.Date)
        df = df.merge(a[['tt', 'HomeTeam', 'AwayTeam', 'Referee']].drop_duplicates(['tt', 'HomeTeam', 'AwayTeam']),
                      on=['tt', 'HomeTeam', 'AwayTeam'], how='left').drop(columns='tt')
    return df


def load_sp2():
    return _load('SP2')


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
