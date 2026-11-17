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
    return _load('SP1')


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
