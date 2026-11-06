#!/usr/bin/env python3
# Fig 6(a) 형식 그래프: job별 executor 컨테이너의 실제 사용량(실선, use-N)과 컨테이너 크기(점선, cnt-N)
#   입력: fig6a.sh 결과 폴더의 watch.log(2초 간격 cgroup), apps.txt(앱 ID ↔ 이름), events.log(시작 시각)
#   AM 컨테이너(_000001)는 제외. kill 후 relaunch된 executor는 같은 job 색, 컨테이너마다 선을 끊어 그림
#   nm.log의 "OOM kill: <컨테이너>" 시점에 ×, 가장 큰 shrink 한 곳에 "shrinked" 글자
#   색 3개만 사용 (PPT 서식 규칙), 라벨은 논문 그래프처럼 영어
# usage: python3 plot-fig6a.py <결과 폴더> [출력 png] [제목 뒤에 붙일 설명]
import re
import sys
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

d = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else d + "/fig6a.png"
note = sys.argv[3] if len(sys.argv) > 3 else "1/4 scale, single node"

names = {}  # 앱 번호(0010 등) → job 이름
for line in open(d + "/apps.txt"):
    m = re.match(r"\s*application_\d+_(\d+)\s+(fig6a-\S+)", line)
    if m:
        names[m.group(1)] = m.group(2)
start = re.search(r"start=\S+ (\S+)", open(d + "/events.log").readline()).group(1)
t0 = datetime.strptime(start, "%H:%M:%S")

series = {}  # (job, 컨테이너 번호) → {"t": [], "use": [], "cnt": []}
t = None
row = re.compile(r"container_\d+_(\d+)_01_(\d+)\s+limit\s+(\d+)M\s+mem\s+(\d+)M")
for line in open(d + "/watch.log"):
    if line.startswith("== "):
        t = (datetime.strptime(line[3:].strip(), "%H:%M:%S") - t0).total_seconds()
        continue
    m = row.search(line)
    if not m or m.group(2) == "000001" or m.group(1) not in names:
        continue
    s = series.setdefault((names[m.group(1)], m.group(2)), {"t": [], "use": [], "cnt": []})
    s["t"].append(t)
    s["cnt"].append(int(m.group(3)) / 1024)
    s["use"].append(int(m.group(4)) / 1024)

kills = []  # (시각, job, 컨테이너 번호)
kpat = re.compile(r"^\S+ (\d\d:\d\d:\d\d),\d+ .*OOM kill: container_\d+_(\d+)_01_(\d+)")
for line in open(d + "/nm.log", errors="ignore"):
    m = kpat.match(line)
    if m and m.group(2) in names:
        kills.append(((datetime.strptime(m.group(1), "%H:%M:%S") - t0).total_seconds(), names[m.group(2)], m.group(3)))

# shrink: "slacking contianer detected" 다음 같은 컨테이너의 "update container memory"에서 크기가 줄어든 것
shrinks = []  # (시각, job, 이전 MB, 이후 MB)
spat = re.compile(r"^\S+ (\d\d:\d\d:\d\d),\d+ .*slacking contianer detected: container_\d+_(\d+)_01_(\d+)")
upat = re.compile(r"^\S+ (\d\d:\d\d:\d\d),\d+ .*update container memory: container_\d+_(\d+)_01_(\d+) old: (\d+)new: (\d+)")
slack = set()
for line in open(d + "/nm.log", errors="ignore"):
    m = spat.match(line)
    if m:
        slack.add((m.group(2), m.group(3)))
        continue
    m = upat.match(line)
    if m and (m.group(2), m.group(3)) in slack:
        slack.discard((m.group(2), m.group(3)))
        old, new = int(m.group(4)), int(m.group(5))
        if new < old and m.group(2) in names:
            t = (datetime.strptime(m.group(1), "%H:%M:%S") - t0).total_seconds()
            shrinks.append((t, names[m.group(2)], old, new))

jobs = [("fig6a-pr", "1", "#1f4fd8"), ("fig6a-km1", "2", "#000000"), ("fig6a-km2", "3", "#2e8b2e")]
fig, ax = plt.subplots(figsize=(10, 4))
for kind, ls in (("use", "-"), ("cnt", "--")):
    for job, n, color in jobs:
        first = True
        for (j, c), s in sorted(series.items()):
            if j != job:
                continue
            ax.step(s["t"], s[kind], where="post", color=color, lw=2, ls=ls,
                    label=f"{kind}-{n}" if first else None)
            first = False
for t, job, c in kills:
    s = series.get((job, c))
    color = [col for j, _, col in jobs if j == job][0]
    y = next((u for u in reversed(s["use"]) if u > 0), 0) if s else 0  # kill 직전 사용량
    ax.plot([t], [max(y, 0.3)], marker="x", ms=10, mew=2.5, color=color)
ax.plot([], [], marker="x", ls="", color="#000000", label="killed")
# shrink: 1GB 이상 줄어든 것 중(종료 앞뒤 15초 제외) 가장 크게 줄어든 곳에만 논문처럼 "shrinked" 글자
#   ▼ 표시는 그래프가 안 보여 뺌 (2026-11-06 교수님)
ends = {}  # job → 그 job 컨테이너들의 종료 시각 목록
for (j, c), s in series.items():
    ends.setdefault(j, []).append(s["t"][-1])
big = [s for s in shrinks if s[2] - s[3] >= 1024
       and not any(abs(e - s[0]) <= 15 for e in ends.get(s[1], []))]
if big:
    t, job, old, new = max(big, key=lambda s: s[2] - s[3])
    ax.annotate("shrinked", xy=(t, old / 1024), xytext=(t + 60, old / 1024 + 3),
                arrowprops=dict(arrowstyle="->", color="#000000"), fontsize=10)
# 축을 논문 Fig 6(a)와 같은 기준으로: 가로 0~1750초 눈금 250초, 세로는 논문 0~100GB(노드 120GB)와 같은 높이
#   왼쪽 = 우리 GB (노드 28GB), 오른쪽 = 논문 노드로 환산한 GB (× 120/28)
SCALE = 120 / 28
ax.set_xlabel("Run time (s)")
ax.set_ylabel("Memory usage (GB, node 28GB)")
ax.set_ylim(0, 100 / SCALE)
xmax = max(max(s["t"]) for s in series.values())
ax.set_xlim(-90, max(1900, xmax + 60))
ax.set_xticks(range(0, int(max(1900, xmax + 60)), 250))
ax2 = ax.secondary_yaxis("right", functions=(lambda y: y * SCALE, lambda y: y / SCALE))
ax2.set_ylabel("paper-scale GB (×120/28)")
ax2.set_yticks(range(0, 101, 20))
ax.grid(True, ls="--", alpha=0.5)
ax.legend(ncol=8, loc="upper center", fontsize=8)
ax.set_title(f"(a) puff() function — {note}")
fig.tight_layout()
fig.savefig(out, dpi=150)
print(out)
