import numpy as np, pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln
MAXG=10
def fit(df, ref_date, xi, reg, teams=None, x0=None):
    """Dixon-Coles con decaimiento exp(-xi*dias) y penalización L2 reg/2*sum(a^2+d^2). Solo usa partidos con fecha < ref_date."""
    d=df[df.Date<ref_date]
    if teams is None: teams=sorted(set(d.HomeTeam)|set(d.AwayTeam))
    idx={t:i for i,t in enumerate(teams)}; n=len(teams)
    h=d.HomeTeam.map(idx).values; a=d.AwayTeam.map(idx).values
    x=d.FTHG.values; y=d.FTAG.values
    w=np.exp(-xi*(ref_date-d.Date).dt.days.values)
    c00=(x==0)&(y==0); c01=(x==0)&(y==1); c10=(x==1)&(y==0); c11=(x==1)&(y==1)
    const=gammaln(x+1)+gammaln(y+1)
    def f(p):
        att=p[:n]; de=p[n:2*n]; home=p[2*n]; rho=p[2*n+1]
        el=home+att[h]+de[a]; em=att[a]+de[h]
        lam=np.exp(el); mu=np.exp(em)
        tau=np.ones_like(lam)
        tau[c00]=1-lam[c00]*mu[c00]*rho; tau[c01]=1+lam[c01]*rho; tau[c10]=1+mu[c10]*rho; tau[c11]=1-rho
        tau=np.maximum(tau,1e-10)
        ll=np.log(tau)+x*el-lam+y*em-mu-const
        gl=x-lam; gm=y-mu; gr=np.zeros_like(lam)
        gl[c00]+= -lam[c00]*mu[c00]*rho/tau[c00]; gm[c00]+= -lam[c00]*mu[c00]*rho/tau[c00]; gr[c00]=-lam[c00]*mu[c00]/tau[c00]
        gl[c01]+= lam[c01]*rho/tau[c01]; gr[c01]=lam[c01]/tau[c01]
        gm[c10]+= mu[c10]*rho/tau[c10]; gr[c10]=mu[c10]/tau[c10]
        gr[c11]=-1/tau[c11]
        L=-(w*ll).sum()+reg/2*(att@att+de@de)
        g=np.zeros_like(p)
        g[:n]=-(np.bincount(h,w*gl,n)+np.bincount(a,w*gm,n))+reg*att
        g[n:2*n]=-(np.bincount(a,w*gl,n)+np.bincount(h,w*gm,n))+reg*de
        g[2*n]=-(w*gl).sum(); g[2*n+1]=-(w*gr).sum()
        return L,g
    p0=np.zeros(2*n+2) if x0 is None else x0
    if x0 is None: p0[2*n]=0.25
    bnds=[(None,None)]*(2*n+1)+[(-0.3,0.3)]
    r=minimize(f,p0,jac=True,method='L-BFGS-B',bounds=bnds)
    return dict(teams=teams,idx=idx,p=r.x,n=n,ok=r.success,nll=r.fun)
def score_matrix(m, home, away):
    n=m['n']; p=m['p']; idx=m['idx']
    ah=p[idx[home]] if home in idx else 0.0; dh=p[n+idx[home]] if home in idx else 0.0
    aa=p[idx[away]] if away in idx else 0.0; da=p[n+idx[away]] if away in idx else 0.0
    lam=np.exp(p[2*n]+ah+da); mu=np.exp(aa+dh); rho=p[2*n+1]
    g=np.arange(MAXG+1)
    ph=np.exp(g*np.log(lam)-lam-gammaln(g+1)); pa=np.exp(g*np.log(mu)-mu-gammaln(g+1))
    M=np.outer(ph,pa)
    M[0,0]*=1-lam*mu*rho; M[0,1]*=1+lam*rho; M[1,0]*=1+mu*rho; M[1,1]*=1-rho
    return M/M.sum(), lam, mu
