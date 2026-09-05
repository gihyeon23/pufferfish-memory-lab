# 9차: 단일 노드 최종 검증 (5·6·8차 통합)

## 목적

5차(admission 기반 lazy reclaim), 6차(EJF 우선순위), 8차(실사용량 안전
하한선)가 각각 따로 검증됐다. 이 실습은 셋을 **실제 Java 워크로드 하나로
한 번에 붙여서** 최종 확인하는, 단일 호스트 재현 트랙의 마지막 실습이다.
이후 7차(멀티노드)로 넘어간다.

## 시나리오

03/05/08번과 동일한 구성 — `pf-test-1/2/3`을 `CHUNK_SIZE_MB=8`로 띄우고
monitor를 붙여 puff가 반복되게 한 뒤, 호스트 예산이 꽉 찬 시점에
`admission.py`로 `pf-test-4`를 요청한다.

```bash
cd controller
docker run -d --name pf-test-1 --memory=256m --memory-swap=768m \
  -e CHUNK_SIZE_MB=8 -e INTERVAL_SECONDS=2 -e MAX_ALLOCATION_MB=1024 \
  -e JAVA_OPTS="-Xmx1200m" pufferfish/workload-java:latest
sleep 5
docker run -d --name pf-test-2 --memory=256m --memory-swap=768m \
  -e CHUNK_SIZE_MB=8 -e INTERVAL_SECONDS=2 -e MAX_ALLOCATION_MB=1024 \
  -e JAVA_OPTS="-Xmx1200m" pufferfish/workload-java:latest
sleep 5
docker run -d --name pf-test-3 --memory=256m --memory-swap=768m \
  -e CHUNK_SIZE_MB=8 -e INTERVAL_SECONDS=2 -e MAX_ALLOCATION_MB=1024 \
  -e JAVA_OPTS="-Xmx1200m" pufferfish/workload-java:latest

python3 container_monitor.py pf-test-1 --interval 0.5 > monitor-1.log 2>&1 &
python3 container_monitor.py pf-test-2 --interval 0.5 > monitor-2.log 2>&1 &
python3 container_monitor.py pf-test-3 --interval 0.5 > monitor-3.log 2>&1 &

# 예산 근접 확인 (반복 실행)
python3 -c "
from puff_manager import get_host_assigned_mb, get_host_budget_mb
a=get_host_assigned_mb(); b=get_host_budget_mb()
print(f'assigned={a}MiB budget={b}MiB free={b-a}MiB')
"

# 예산 도달 시 (rm -f state/*.json 하지 않음 — 이미 puff 진행 중이므로)
python3 admission.py pf-test-4 pufferfish/workload-java:latest \
  --request-mb 512 --env CHUNK_SIZE_MB=8 --env INTERVAL_SECONDS=2 \
  --env MAX_ALLOCATION_MB=512 --env JAVA_OPTS="-Xmx600m"
```

## 확인 포인트

- [ ] 예산 도달 시점까지 `pf-test-1/2/3` 셋 다 생존 (청크 버스트 없이)
- [ ] `admission.py`가 정확히 "여유 부족" 판단 (budget 기준, 8차 이전
      버그였다면 오판했을 시점)
- [ ] `reclaim_host()`가 EJF 순서(가장 나중에 생성된 컨테이너부터)로 회수
- [ ] reclaim된 컨테이너들이 즉시 OOM-kill되지 않음 (8차 안전 하한선 확인)
- [ ] `pf-test-4` 정상 실행

## 진행 상황

- `pf-test-1/2/3` 실행 + monitor 부착 완료, `CHUNK_SIZE_MB=8`로 청크
  버스트 없이 안정적으로 puff 반복하며 성장
- assigned가 budget에 정확히 도달(`assigned=3119MiB=budget`, free=0MiB)
  — admission 트리거 직전 상태

## 상태

**진행 중** — admission 실행 및 결과 확인 예정.
