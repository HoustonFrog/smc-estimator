# SMC 获批时间预测 修订版 v2 — 可复现脚本
# 用法: python3 smc_model_v2.py（默认读取 ../data/CN/）
# 供 build_web_data.py 复用：import smc_model_v2 as smc; smc.DEC,smc.ACC,smc.OH=smc.load(raw_dir);
#   par=smc.estimate(smc.DEC.index[-1], look=3); pv=smc.pitvals()

import pandas as pd, numpy as np

def load(raw_dir):
    r1=pd.read_csv(raw_dir+"R1_Residence_Decisions_by_Decision_Type_and_Application_Substream.csv")
    dec=r1.pivot_table(index='Date',values='Count',aggfunc='sum').sort_index()['Count']
    acc=pd.read_csv(raw_dir+"R7_Residence_Accepted_by_Application_Stream.csv").set_index('Date')['Count']
    oh =pd.read_csv(raw_dir+"R8_Residence_On_Hand_by_Application_Stream.csv").set_index('Date')['Count']
    for s in (dec,acc,oh): s.index=pd.PeriodIndex(pd.to_datetime(s.index),freq='M')
    return dec.astype(float),acc.astype(float),oh.astype(float)
REBOUND=1.0
BLOCK=2
DRIFT_CAP=0

# ---------- 季节因子 ----------
SEAS={1:0.25, 2:0.85}
def s_of(per): return SEAS.get(per.month,1.0)
def sadj(s):  return s/ pd.Series([s_of(p) for p in s.index],index=s.index)

# ---------- 产能与中断状态估计（只用截至 origin 的数据） ----------
def estimate(origin, look=6):
    """origin = 最后一个已知数据月(含)。返回 mu(季调后正常月产能), 正常月比率池, 中断参数"""
    hist=DEC.loc[:origin]
    a=sadj(hist)
    trail=hist.shift(1).rolling(6,min_periods=4).median()
    ratio=hist/trail
    disrupt=(ratio<0.5)&(pd.Series([p.month!=1 for p in hist.index],index=hist.index))
    # 当前产能：最近 look 个月的季调值，剔除中断月
    L=look
    while True:                                   # 窗口内至少要有3个非中断月，否则向前扩展
        win=a.loc[:origin].tail(L)
        win=win[~disrupt.reindex(win.index).fillna(False)]
        if len(win)>=3 or L>=15: break
        L+=1
    mu=win.mean()
    # 正常月波动池：最近 12 个月季调值 / 各自 6 个月中心水平，剔除中断月
    lvl=a.rolling(5,min_periods=3,center=True).median()   # 居中窗口，避免趋势期产生虚假离散
    pool=(a/lvl).dropna()
    pool=pool[~disrupt.reindex(pool.index).fillna(False)]
    keep=lvl.reindex(pool.index)>=max(0.4*mu,60)          # 只用与当前量级可比的月份(小样本月相对噪声过大)
    pool=pool[keep.fillna(False)]
    if len(pool)<6: pool=(a/lvl).dropna().tail(12)
    pool=pool.values
    pool=pool/pool.mean()                       # 归一化，均值=1
    # 中断参数
    nb=(~disrupt).sum(); nd=disrupt.sum()
    ep=int((disrupt.astype(int).diff()==1).sum())+int(bool(disrupt.iloc[0]))
    p_enter = ep/max(nb,1)                      # 每个正常月进入中断的概率
    dur     = nd/ep if ep else 2.0
    p_exit  = 1/max(dur,1.0)
    lo = (hist[disrupt]/trail[disrupt]).mean() if nd else 0.30
    if not np.isfinite(lo): lo=0.30
    # 动量：季调后对数产能的近期斜率(剔除中断月)，收缩50%后使用，防止过度外推
    tr=a.loc[:origin].tail(9)
    tr=tr[~disrupt.reindex(tr.index).fillna(False)]
    tr=tr[tr>0]
    if len(tr)>=4:
        tt=np.arange(len(tr)); b=np.polyfit(tt,np.log(tr.values),1)
        g=float(np.clip(0.5*b[0],-0.05,0.08))
        resid=np.log(tr.values)-np.polyval(b,tt)
        sd_g=float(np.std(resid,ddof=2)/max(np.sqrt(((tt-tt.mean())**2).sum()),1e-9))*0.5
    else: g,sd_g=0.0,0.02
    return dict(mu=mu,pool=pool,p_enter=p_enter,p_exit=p_exit,lo=lo,g=g,sd_g=min(sd_g,0.06),
                n_norm=len(win),sd_mu=win.std(ddof=1)/np.sqrt(max(len(win),1)),disrupt=disrupt)

# ---------- 模拟 ----------
def simulate(par,q_mean,q_sd,start,n=100000,H=30,force=None,seed=1):
    rng=np.random.default_rng(seed)
    months=[pd.Period(start,'M')+i for i in range(H)]
    seas=np.array([s_of(m) for m in months])
    mu=par['mu']+rng.normal(0,par['sd_mu'],size=n)        # 产能水平的参数不确定性
    mu=np.clip(mu,20,None)
    pool=par['pool']; LB=BLOCK                             # 正常月波动：块抽样，保留"连续几个月低迷"的持续性
    nb=max(len(pool)-LB+1,1)
    ks=rng.integers(0,nb,size=(n,int(np.ceil(H/LB))))
    eps=np.concatenate([pool[ks[:,j][:,None]+np.arange(LB)[None,:]] for j in range(ks.shape[1])],axis=1)[:,:H]
    # 两状态马尔可夫
    st=np.zeros((n,H),bool)
    cur=np.zeros(n,bool)
    for t in range(H):
        u=rng.random(n)
        nxt=np.where(cur, u>par['p_exit'], u<par['p_enter'])
        cur=nxt; st[:,t]=cur
    if force is not None:                                  # 压力情景：强制指定月份中断，之后从中断态继续演化
        idx=[months.index(m) for m in force if m in months]
        for i in idx: st[:,i]=True
        if idx:
            cur=np.ones(n,bool)
            for t in range(max(idx)+1,H):
                u=rng.random(n)
                cur=np.where(cur,u>par['p_exit'],u<par['p_enter']); st[:,t]=cur
    lvl=np.where(st, par['lo'], 1.0)
    reb=np.ones_like(lvl,dtype=float)                      # 中断结束后的追赶反弹(历史上均出现)
    if REBOUND>1.0:
        prev=np.concatenate([np.zeros((n,1),bool),st[:,:-1]],axis=1)
        reb=np.where(prev&(~st),REBOUND,1.0)
    gg=par.get('g',0.0)+rng.normal(0,par.get('sd_g',0.0),size=n)
    ramp=np.minimum(np.arange(H),DRIFT_CAP)                # 动量最多外推 DRIFT_CAP 个月后走平
    grow=np.exp(gg[:,None]*ramp[None,:])
    path=mu[:,None]*seas[None,:]*eps*lvl*reb*grow
    cum=path.cumsum(axis=1)
    q=np.clip(rng.normal(q_mean,q_sd,size=n),1,None)
    done=cum>=q[:,None]
    hit=np.where(done.any(axis=1),done.argmax(axis=1),H)   # H = 未清完(删失)
    return months,hit,path

def quants(months,hit,H=30,qs=(0.10,0.25,0.50,0.75,0.90)):
    out=[]
    for qq in qs:
        v=int(np.quantile(hit,qq))
        out.append(str(months[v]) if v<len(months) else ">%s"%months[-1])
    return out

# ================= 回测（修订版模型，统一口径） =================
def backtest(look=6,qsd=60,n=40000):
    rows=[]
    for sub in pd.period_range('2024-06','2026-01',freq='M'):
        prev=sub-1
        if prev not in OH.index or sub not in ACC.index: continue
        q_at_sub = OH[prev] + 0.5*ACC[sub]
        if sub not in DEC.index: continue
        q_rem = q_at_sub - DEC[sub]          # 提交当月实际决定量已知(与本次预测口径一致)
        if q_rem<=0: continue
        origin=sub                            # 已知数据截至提交当月
        par=estimate(origin,look=look)
        months,hit,_=simulate(par,q_rem,qsd,str(sub+1),n=n,seed=7)
        pr=quants(months,hit)
        # 实际清队月：累计实际决定量(从提交次月起)首次达到 q_rem
        fut=DEC.loc[sub+1:]
        cs=fut.cumsum()
        act=cs.index[(cs>=q_rem).values][0] if (cs>=q_rem).any() else None
        if act is None: continue
        p10,p90=pr[0],pr[4]
        hitband = (not p10.startswith('>')) and (not p90.startswith('>')) and (pd.Period(p10,'M')<=act<=pd.Period(p90,'M'))
        rows.append(dict(提交月=str(sub),排队位置=int(q_at_sub),扣除当月已决后=int(q_rem),
                         P10=pr[0],P50=pr[2],P90=pr[4],实际清队月=str(act),
                         误差月=(act-pd.Period(pr[2],'M')).n if not pr[2].startswith('>') else None,
                         命中80区间='是' if hitband else '否'))
    return pd.DataFrame(rows)

def pitvals(n=40000):
    o=[]
    for sub in pd.period_range('2024-06','2026-01',freq='M'):
        q=OH[sub-1]+0.5*ACC[sub]-DEC[sub]
        if q<=0: continue
        p=estimate(sub,look=3); m,h,_=simulate(p,q,QSD,str(sub+1),n=n,seed=7)
        cs=DEC.loc[sub+1:].cumsum()
        if not (cs>=q).any(): continue
        k=m.index(cs.index[(cs>=q).values][0]); o.append(((h<k).mean()+(h<=k).mean())/2)
    return np.sort(np.array(o))

# ================= 主程序（仅直接运行本脚本时执行；import 不触发任何模拟） =================
if __name__=="__main__":
    RAW="../data/CN/"
    QSD=80; N=300000
    DEC,ACC,OH=load(RAW)
    ORI=DEC.index[-1]                 # 数据截止月，自动从数据推导，不再手写
    START=str(ORI+1)
    SHOCK=[ORI+1,ORI+2]; P_SHOCK=0.35
    par=estimate(ORI,look=3)
    print("生产参数  mu=%.0f(标准误%.0f, 近3个月季调, look=3)  正常月波动sd=%.2f(块长2)  内生中断: 进入%.1f%%/月, 期望时长%.1f月, 产能倍数%.2f"%(
     par['mu'],par['sd_mu'],par['pool'].std(ddof=1),100*par['p_enter'],1/par['p_exit'],par['lo']))

    PV=pitvals(); MAP={a:float(np.clip(np.quantile(PV,a),0.005,0.995)) for a in (.10,.25,.50,.75,.90)}
    print("PIT标定映射:", {k:round(v,3) for k,v in MAP.items()})

    def qm(m,h,levels): return [str(m[int(np.quantile(h,a))]) if int(np.quantile(h,a))<len(m) else '>'+str(m[-1]) for a in levels]
    out=[]; store={}
    # 数据截止月的月初/月中/月底三个代表性递交点：有效排队 = 上月末在办 + frac×本月受理，再扣除本月已发生的决定量
    monthlabel=str(ORI)
    for lab,frac in [(monthlabel+' 月初',0.0),(monthlabel+' 月中旬',0.5),(monthlabel+' 月底',1.0)]:
        qe=OH[ORI-1]+frac*ACC[ORI]-DEC[ORI]
        mb,hb,pathb=simulate(par,qe,QSD,START,n=N,seed=11)
        ms,hs,_=simulate(par,qe,QSD,START,n=N,force=SHOCK,seed=12)
        rng=np.random.default_rng(99); hm=np.where(rng.random(N)<P_SHOCK,hs,hb)
        e26=max(i for i,x in enumerate(mb) if x<=pd.Period(str(ORI.year)+'-12','M'))
        store[lab]=(mb,hb,hs,hm,pathb,qe)
        for tag,h in [('基准情景',hb),('新规冲击(条件情景)',hs),('混合(冲击概率35%)',hm)]:
            r=qm(mb,h,[.10,.25,.50,.75,.90]); c=qm(mb,h,[MAP[.10],MAP[.25],MAP[.50],MAP[.75],MAP[.90]])
            out.append(dict(提交时点=lab,有效排队=int(round(qe)),情景=tag,
              P10=r[0],P25=r[1],P50=r[2],P75=r[3],P90=r[4],
              标定P10=c[0],标定P50=c[2],标定P90=c[4],年内获批概率="%.0f%%"%(100*(h<=e26).mean())))
    R=pd.DataFrame(out); R.to_csv('forecast_final.csv',index=False)
    print("\n"+R.to_string(index=False))
    import pickle; pickle.dump({'store':{k:(v[0],v[1],v[2],v[3],v[5]) for k,v in store.items()},'par':par,'MAP':MAP,'PV':PV},open('res.pkl','wb'))
