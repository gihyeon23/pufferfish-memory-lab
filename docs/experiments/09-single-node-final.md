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

- [x] 예산 도달 시점까지 `pf-test-1/2/3` 셋 다 생존 (청크 버스트 없이)
- [x] `admission.py`가 정확히 "여유 부족" 판단 (`free=0MiB`)
- [x] `reclaim_host()`가 EJF 순서(가장 나중에 생성된 컨테이너부터)로 회수
- [x] reclaim된 컨테이너들이 즉시 OOM-kill되지 않음 (8차 안전 하한선 확인)
- [x] `pf-test-4` 정상 실행

## 검증 결과

`assigned=3119MiB=budget`(free=0)에서 `admission.py pf-test-4 --request-mb 512` 실행 —

```
[admission] 여유 부족 (free=0MiB < request=512MiB) -> reclaim_host 호출
[puff_manager] pf-test-3: 실사용량(952MiB)이 이미 커서 reclaim 건너뜀 (한도 981MiB 유지)
[puff_manager] pf-test-2: reclaim 적용 981MiB -> 977MiB (회수 4MiB, 실사용량 945MiB)
[puff_manager] pf-test-1: reclaim 적용 1157MiB -> 919MiB (회수 238MiB, 실사용량 887MiB)
[admission] reclaim 242MiB 회수, reclaim 후 여유 242MiB
[admission] 경고: reclaim 후에도 여유(242MiB)가 요청량(512MiB)보다 적음 — 그래도 실행함
[admission] 컨테이너 시작됨: pf-test-4
```

**세 가지가 한 번에 확인됨**:

1. **EJF(6차)**: reclaim 시도 순서가 `pf-test-3`(가장 최근 생성) →
   `pf-test-2` → `pf-test-1`(가장 오래됨) — 창생 순서(1→2→3)의 정확히
   역순으로 시도됐다.
2. **실사용량 안전 하한선(8차)**: `pf-test-3`은 실사용량(952MiB)+안전마진이
   이미 한도(981MiB)에 육박해 **아예 건너뜀**. `pf-test-2`/`pf-test-1`은
   각자 실사용량+32MiB까지만 정확히 회수되고 그 아래로는 안 내려감.
3. **budget 일관성(5차 버그 수정)**: `free=0MiB`을 정확히 감지해 reclaim을
   트리거함 (수정 전이었다면 raw 100% 기준으로 "여유 있다"고 오판했을
   지점).

목표한 512MiB 중 242MiB만 회수됐다 — **컨테이너 3개가 전부 실제로 메모리를
거의 다 쓰고 있어서 더 짜낼 여유(slack)가 없었기 때문**이다(버그가 아니라
논문 p.263의 "여유분만 회수" 원칙이 정확히 지켜진 결과). admission은 이
경우 지연/큐 없이 경고만 남기고 그대로 실행하도록 설계돼 있어(05번 문서
참고), `pf-test-4`는 예정대로 시작됐다.

`docker inspect` 결과 reclaim 직후 및 20초 뒤 모두 **4개 컨테이너 전부
생존**(`OOMKilled=false`). 다만 20초 뒤 `assigned=3631MiB`로 budget
(3119MiB)을 넘어선 상태(`free=-512MiB`)가 됐다 — admission이 지연/큐를
구현하지 않아 예산을 넘겨서라도 실행한 결과이며, 이후에도 컨테이너가
계속 자라면 04번 데몬 없이는 다시 압박받을 수 있다(이건 8차에서 이미
확인한, 논문에 부합하는 별개의 정상 동작).

## 상태

**완료.** 5·6·8차가 실제 워크로드에서 함께 정확히 작동함을 확인했다.
단일 호스트 재현 트랙은 여기서 마무리하고, 다음은 7차(멀티노드)로
넘어간다.
