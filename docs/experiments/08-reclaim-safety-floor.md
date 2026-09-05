# 8차: reclaim이 실사용량 아래로 내려가지 못하게 하는 안전장치

## 목적

5차(admission.py) 라이브 테스트 중, reclaim이 컨테이너를 그 자리에서
OOM-kill시키는 걸 발견했다. `puff_manager.reclaim()`이 memory.max를
실제 사용량(`memory.current`)보다 낮게 강제로 내려버린 게 원인이었다.
이 실습은 그 문제를 실사용량 기반 안전 하한선으로 고친 기록이다.

## 시행착오: 첫 번째 가설(suspend 먼저)은 틀렸다

**가설 1 (틀림)**: "CPU를 suspend(1%로 제한)한 뒤에 한도를 줄이면, 페이지를
서서히 swap-out할 시간을 벌어서 OOM을 막을 수 있을 것이다."

이 가설대로 `reclaim()`에 `suspend_manager.suspend()` 호출을 먼저 추가했지만,
라이브 재현 테스트에서 **이미 suspend된 컨테이너도 한도를 실사용량 아래로
내리자마자 즉시 OOM-kill됐다**:

```
[container_monitor] pf-test-3: current=718.4MiB ... max=981.0MiB (건강함, suspend 상태)
   ↓ admission.py가 reclaim 실행 (981 -> 645MiB로 축소)
[container_monitor] pf-test-3: current=578.5MiB ... max=645.0MiB events: oom=6479, oom_kill=1
```

**왜 안 통했나**: `memory.max`를 현재 사용량보다 낮은 값으로 쓰면, 커널이
그 자리에서 **동기적으로** 회수를 시도한다. 이건 커널의 reclaim 경로라
컨테이너의 CPU 쿼터(suspend)와 무관하게 동작한다 — CPU를 아무리 낮춰도
커널이 짧은 시간 안에 그만큼 못 비우면 cgroup OOM killer가 바로 발동한다.
논문 Figure 3(p.261)의 64GB→4GB reclaim 사례에서도 CPU 1% 제한은 reclaim
185초 **후에** "이미 진행 중인 swapping storm을 진정시키려고" 따로 적용한
것이었지, reclaim 자체를 안전하게 만들려는 선행 조치가 아니었다 — 이 인과
관계를 처음에 잘못 해석했다.

## 진짜 원인과 수정

논문(p.263)은 puff()의 shrink 메커니즘을 이렇게 설명한다: "컨테이너가
50GB로 puff됐는데 실제 수요가 60GB라면, 10GB는 안 쓰는 여유분(slack)이니
62GB로 줄인다." 즉 **회수 대상은 안 쓰는 여유분이지, 쓰고 있는 메모리가
아니다.** `reclaim()`도 같은 원칙을 지켜야 한다.

`controller/puff_manager.py`에 추가:

```python
RECLAIM_SAFETY_MARGIN_MB = 32  # reclaim 후 한도가 실사용량보다 이만큼은 위에 있게 함

def get_current_memory_usage_mb(container: str) -> int:
    """cgroup memory.current(실제 사용량)를 MiB로 반환한다."""
    ...
```

`reclaim()`의 하한 계산을 `floor_mb`(puff 전 원래 한도) 하나에서
`max(floor_mb, usage_mb + RECLAIM_SAFETY_MARGIN_MB)`로 바꿨다 — 실사용량이
원래 한도보다 크면, 목표량을 다 못 채우더라도 실사용량 위 32MiB까지만
회수한다. suspend 호출 자체는 유지한다(OOM은 안 막아주지만, 회수된 상태로
계속 실행되며 추가 요구를 진정시키는 역할은 있음, p.264).

## 실행 방법 (재현 검증에 쓴 시나리오)

```bash
cd controller
docker run -d --name pf-test-1 --memory=256m --memory-swap=768m \
  -e CHUNK_SIZE_MB=8 -e INTERVAL_SECONDS=2 -e MAX_ALLOCATION_MB=1024 \
  -e JAVA_OPTS="-Xmx1200m" pufferfish/workload-java:latest
sleep 5
docker run -d --name pf-test-2 ... (동일, CHUNK_SIZE_MB=8)
sleep 5
docker run -d --name pf-test-3 ... (동일)

python3 container_monitor.py pf-test-1 --interval 0.5 > monitor-1.log 2>&1 &
python3 container_monitor.py pf-test-2 --interval 0.5 > monitor-2.log 2>&1 &
python3 container_monitor.py pf-test-3 --interval 0.5 > monitor-3.log 2>&1 &

# assigned가 budget 근처(수 분 소요)에 도달할 때까지 대기
python3 -c "from puff_manager import get_host_assigned_mb, get_host_budget_mb; ..."

# budget 근접 시 admission으로 reclaim 트리거
python3 admission.py pf-test-4 pufferfish/workload-java:latest \
  --request-mb 512 --env CHUNK_SIZE_MB=8 --env INTERVAL_SECONDS=2 \
  --env MAX_ALLOCATION_MB=512 --env JAVA_OPTS="-Xmx600m"
```

## 검증 결과

수정 전(같은 시나리오): reclaim 직후(981→645MiB) `pf-test-3` 즉시
OOM-kill.

수정 후: reclaim 직후(`pf-test-3` 981→752MiB, `pf-test-2` 981→874MiB) —

```
[puff_manager] pf-test-3: reclaim 적용 981MiB -> 752MiB (회수 229MiB, 실사용량 720MiB)
[puff_manager] pf-test-2: reclaim 적용 981MiB -> 874MiB (회수 107MiB, 실사용량 713MiB)
[admission] reclaim 336MiB 회수, reclaim 후 여유 512MiB
[admission] 컨테이너 시작됨: pf-test-4
```

`docker inspect` 확인 결과 4개 컨테이너(`pf-test-1/2/3/4`) 전부 reclaim
직후 생존 — **이번에 고치려던 즉시 OOM은 재현 안 됨.**

15초 뒤 `pf-test-2`가 다시 죽었지만(`OOMKilled=true`), 로그 확인 결과
reclaim과 무관한 **별개의, 이미 알려진 원인**이었다: 워크로드가 계속 자라
reclaim된 한도(874MiB)에 다시 부딪혔고, 이때 `assigned=3419MiB >
budget=3119MiB`라 puff가 다시 거부됐다. 이 테스트엔 `host_reclaim_daemon.py`
(4차)를 안 띄웠으니 아무도 두 번째 구제를 안 해준 것.

**이건 04번으로 메워야 할 구멍이 아니다.** 논문 재현이 목적이라면, admission
없이 이미 떠 있는 컨테이너가 다시 압박받는 상황에서 아무도 자동으로
reclaim을 안 해주는 게 오히려 논문에 맞는 동작이다 — 논문(§4.3.3, p.264)은
lazy reclaim에 더해 suspension tolerance(일정 시간 넘게 suspend되면 kill,
다른 노드에서 재기동 기대)까지 명시한다. 04번(호스트 사용률 상시 폴링)은
이미 "논문 재현 아님, 독자 확장 정책"으로 분류돼 있고([pufferfish-architecture.md](../pufferfish-architecture.md)),
**논문 재현이 우선 목표인 동안은 후속 과제로 미룬다.**

## 확인 포인트

- [x] reclaim 직후 즉시 OOM-kill되지 않는지 (수정 전: 재현됨 / 수정 후: 재현 안 됨)
- [x] 실사용량보다 낮게 회수되지 않는지 (로그의 "실사용량" 값과 새 한도 비교로 확인)
- [ ] `RECLAIM_SAFETY_MARGIN_MB=32`가 충분한 값인지 (더 빠르게 자라는
      워크로드에서는 부족할 수 있음 — 튜닝 여지 있음)
- [ ] (후속, 논문 범위 밖) 04번 데몬과 함께 띄웠을 때 위 재성장 상황에서
      구제되는지 — 논문 재현 트랙이 끝난 뒤 별도 확장 실험으로 진행

## 상태

수정·라이브 재검증 완료.
