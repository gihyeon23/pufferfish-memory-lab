#!/bin/bash
# 실행 중 task 컨테이너의 cgroup v1 메모리 limit·사용량·swap·CPU 제한을 주기적으로 출력 (OCM·puff·suspend 관찰용)
#   swap = memory.memsw.usage - memory.usage (swapaccount=1 필요)
#   suspend면 quota 1000 · cpus 0 (원 코드 docker update --cpu-quota 1000 --cpuset-cpus 0)
# usage: bash watch-containers.sh [간격초]   (기본 2 = puff 주기)
IV=${1:-2}
while true; do
  echo "== $(date +%T)"
  for id in $(docker ps -q --no-trunc); do
    m=/sys/fs/cgroup/memory/docker/$id
    lim=$(cat $m/memory.limit_in_bytes 2>/dev/null) || continue
    use=$(cat $m/memory.usage_in_bytes 2>/dev/null) || continue
    msw=$(cat $m/memory.memsw.usage_in_bytes 2>/dev/null) || continue
    q=$(cat /sys/fs/cgroup/cpu/docker/$id/cpu.cfs_quota_us 2>/dev/null)
    cs=$(cat /sys/fs/cgroup/cpuset/docker/$id/cpuset.cpus 2>/dev/null)
    n=$(docker inspect -f '{{.Name}}' $id 2>/dev/null)
    printf '%-40s limit %6dM  mem %6dM  swap %6dM  quota %6s  cpus %s\n' \
      "${n#/}" $((lim >> 20)) $((use >> 20)) $(((msw - use) >> 20)) "$q" "$cs"
  done
  sleep $IV
done
