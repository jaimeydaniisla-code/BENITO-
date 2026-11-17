"""Walk-forward de córners y tarjetas. Reajuste semanal, solo datos anteriores."""
import numpy as np
import pandas as pd
from matches import load_matches
from countmodel import CountModel, count_pmf, KMAX


def prep():
    df = load_matches()  # HK/AK = amarillas + rojas
    if 'Referee' not in df:
        df['Referee'] = np.nan  # football-data no trae árbitro en SP1
    return df


def run(df, hcol, acol, first=2022, **kw):
    test = df[df.season >= first].copy()
    test['wk'] = test.Date.dt.to_period('W-MON')
    m = CountModel(**kw)
    rows = []
    for wk, g in test.groupby('wk', sort=True):
        ref = g.Date.min(); tr = df[df.Date < ref]
        m.fit(tr, ref, hcol, acol)
        # línea base: media de la liga (mismo decaimiento) y misma familia de distribución
        w = np.exp(-m.xi * (ref - tr.Date).dt.days.values)
        bh = np.sum(w * tr[hcol]) / w.sum(); ba = np.sum(w * tr[acol]) / w.sum()
        bdisp = float(np.sum(w * ((tr[hcol] + tr[acol] - bh - ba) ** 2)) / w.sum() / (bh + ba))
        for i, r in g.iterrows():
            d = m.dists(r.HomeTeam, r.AwayTeam, r.Referee if isinstance(r.Referee, str) else None)
            tot = int(min(r[hcol] + r[acol], KMAX))
            pb = count_pmf(bh + ba, bdisp)
            rows.append(dict(idx=i, season=r.season, lam_h=d['lam_h'], lam_a=d['lam_a'], disp_tot=m.disp_total,
                             obs_h=r[hcol], obs_a=r[acol], obs_tot=r[hcol] + r[acol],
                             p_obs=d['pmf_tot'][tot], p_obs_base=pb[tot],
                             cdf=np.cumsum(d['pmf_tot']).tolist(), cdf_base=np.cumsum(pb).tolist(),
                             p_h_more=float(np.sum(np.tril(np.outer(d['pmf_h'], d['pmf_a']), -1)))))
    return pd.DataFrame(rows).set_index('idx')


def evaluate(P, lines):
    out = {}
    y = P.obs_tot.values
    out['NLL_total_modelo'] = -np.mean(np.log(np.clip(P.p_obs, 1e-12, 1)))
    out['NLL_total_base'] = -np.mean(np.log(np.clip(P.p_obs_base, 1e-12, 1)))
    for L in lines:
        k = int(np.floor(L))
        pu = np.array([c[k] for c in P.cdf]); pb = np.array([c[k] for c in P.cdf_base])
        over = y > L
        out[f'LL_O{L}_modelo'] = -np.mean(np.log(np.where(over, 1 - pu, pu)))
        out[f'LL_O{L}_base'] = -np.mean(np.log(np.where(over, 1 - pb, pb)))
    out['MAE_total_modelo'] = np.mean(np.abs(y - (P.lam_h + P.lam_a)))
    return out
