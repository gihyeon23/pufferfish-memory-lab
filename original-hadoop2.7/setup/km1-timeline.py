# 사용: cd x86-server/runs/17 && python3 ../../../setup/km1-timeline.py G2-r1 G2-r2 ...
# 컨테이너별 suspend 시간(초, nm.log의 1초 샘플), puff/shrink, kill 시각, 첫 kill 전후 limit
import re,sys,os
from datetime import datetime
def t(s): return datetime.strptime(s[:19],"%Y-%m-%d %H:%M:%S").timestamp()+int(s[20:23])/1000
for run in sys.argv[1:]:
    apps={l.split()[1].replace('fig6a-',''):l.split()[0].replace('application_','') for l in open(f'{run}/apps.txt') if l.strip()}
    inv={v:k for k,v in apps.items()}
    ev=open(f'{run}/events.log').read()
    start=t(re.search(r'start=(\S+ \S+)',ev).group(1)+',000')
    ends=[l for l in ev.splitlines() if ' end ' in l]
    day=re.search(r'start=(\S+)',ev).group(1)
    last=max(t(f"{day} {l.split()[0]},000") for l in ends)
    if last<start: last+=86400
    T=last-start
    st={};puff={};kills=[];lim={}
    for l in open(f'{run}/nm.log'):
        m=re.search(r'\$\$\$  container_(\d+_\d+)_01_(\d+) (\w+)',l)
        if m and m.group(2)!='000001':
            k=(inv.get(m.group(1),'?'),m.group(2)); st.setdefault(k,{}).setdefault(m.group(3),set()).add(l[11:19]); continue
        m=re.search(r'balloon-nswap: container_(\d+_\d+)_01_(\d+) from (\d+)to: (\d+)',l)
        if m:
            k=(inv.get(m.group(1),'?'),m.group(2)); a,b=int(m.group(3)),int(m.group(4))
            puff.setdefault(k,[]).append((t(l[:23])-start,a,b)); continue
        m=re.search(r'container_(\d+_\d+)_01_(\d+) transitioned from KILLING to CONTAINER_CLEANEDUP',l)
        if m: kills.append((t(l[:23])-start,inv.get(m.group(1)),m.group(2)))
    print(f"== {run}  total {T:.0f}s")
    for k in sorted(st):
        s=st[k]; sus=len(s.get('SUSPENDING',())); run_=len(s.get('RUNNING',()))
        p=puff.get(k,[]); up=sum(b-a for _,a,b in p if b>a)
        print(f"  {k[0]}#{k[1][-1]}  suspend {sus}s  running {run_}s  puffs {len([x for x in p if x[2]>x[1]])} (+{up}MB)  shrinks {len([x for x in p if x[2]<x[1]])}")
    for kt,kj,kc in kills:
        print(f"  kill {kj}#{kc[-1]} at {kt:.0f}s ({kt/T*100:.0f}%)")
    if kills:
        k0=kills[0][0]
        for k in sorted(puff):
            before=[b for x,a,b in puff[k] if x<k0]; after=[(x,a,b) for x,a,b in puff[k] if k0<=x<k0+300]
            gain=sum(b-a for x,a,b in after if b>a)
            print(f"  {k[0]}#{k[1][-1]} limit@kill1 {before[-1] if before else '-'}MB, +{gain}MB within 300s after kill1")
