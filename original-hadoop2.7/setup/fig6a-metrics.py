#!/usr/bin/env python3
# Fig 6(a) 결과 폴더들을 같은 기준으로 비교: kill 수(job별), 첫 stop ballooning 시각,
#   그 전까지 job별 OCM·puff·shrink 횟수, job별 최대 컨테이너 크기·사용량, 종료 시각
# usage: python3 fig6a-metrics.py <결과 폴더> [폴더 ...]
import collections
import re
import sys
from datetime import datetime


def sec(hms, t0):
    return (datetime.strptime(hms, "%H:%M:%S") - t0).total_seconds()


for d in sys.argv[1:]:
    names = {}
    for line in open(d + "/apps.txt"):
        m = re.match(r"\s*application_\d+_(\d+)\s+fig6a-(\S+)", line)
        if m:
            names[m.group(1)] = m.group(2)
    ev = open(d + "/events.log").read()
    t0 = datetime.strptime(re.search(r"start=\S+ (\S+)", ev).group(1), "%H:%M:%S")
    ends = {m.group(2): m.group(3) for m in re.finditer(r"(\S+) end fig6a-(\S+) exit=\d+ sec=(\d+)", ev)}

    stop = None
    ocm, puff, shrink, kill = (collections.Counter() for _ in range(4))
    for line in open(d + "/nm.log", errors="ignore"):
        m = re.match(r"\S+ (\d\d:\d\d:\d\d)", line)
        if not m:
            continue
        s = sec(m.group(1), t0)
        m = re.search(r"OOM kill: container_\d+_(\d+)_", line)
        if m:
            kill[names.get(m.group(1), "?")] += 1
        if stop is None and "stop ballooning" in line:
            stop = s
        if stop is not None:
            continue  # 아래는 첫 stop ballooning 전 구간만
        m = re.search(r"out of memory contianer detected: container_\d+_(\d+)_", line)
        if m:
            ocm[names.get(m.group(1), "?")] += 1
        m = re.search(r"balloon-nswap: container_\d+_(\d+)_\S+ from (\d+)to: (\d+)", line)
        if m:
            (puff if int(m.group(3)) > int(m.group(2)) else shrink)[names.get(m.group(1), "?")] += 1

    peak = collections.defaultdict(lambda: [0, 0])  # job → [최대 크기 MB, 최대 사용량 MB]
    row = re.compile(r"container_\d+_(\d+)_01_(\d+)\s+limit\s+(\d+)M\s+mem\s+(\d+)M")
    for line in open(d + "/watch.log"):
        m = row.search(line)
        if m and m.group(2) != "000001" and m.group(1) in names:
            p = peak[names[m.group(1)]]
            p[0] = max(p[0], int(m.group(3)))
            p[1] = max(p[1], int(m.group(4)))

    jobs = ["pr", "km1", "km2"]
    print(f"== {d}")
    print(f"  kill {sum(kill.values())} ({', '.join(f'{j} {kill[j]}' for j in jobs if kill[j])}) | 첫 stop ballooning {stop:.0f}초")
    print("  stop 전  OCM " + " · ".join(f"{j} {ocm[j]}" for j in jobs)
          + " | puff " + " · ".join(f"{j} {puff[j]}" for j in jobs)
          + " | shrink " + " · ".join(f"{j} {shrink[j]}" for j in jobs))
    print("  최대 크기/사용량 GB " + " · ".join(f"{j} {peak[j][0]/1024:.1f}/{peak[j][1]/1024:.1f}" for j in jobs)
          + " | 실행 초 " + " · ".join(f"{j} {ends.get(j, '-')}" for j in jobs))
