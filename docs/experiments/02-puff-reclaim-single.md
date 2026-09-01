# 2차: `puff()`/`reclaim()`로 메모리 한도 동적 조절 (단일 컨테이너)

## 알고리즘 출처

논문 4장이 설명하는 puff/reclaim은 논문 저자가 공개한
Hadoop YARN 구현([`yncxcw/pufferfish`](https://github.com/yncxcw/pufferfish)의
`NodeMemoryManager.MemoryBalloon()`/`MemoryReclaim()`,
`ContainerImpl.ContainerMonitor.reclaimMemory()`)을 참고해, 이 프로젝트의
단일 Docker 호스트/cgroup v2 환경에 맞게 옮겼다. YARN 버전은 NodeManager가
여러 컨테이너의 메모리를 중앙에서 조정하지만, 이 프로젝트는 `docker update
--memory/--memory-swap`으로 cgroup `memory.max`를 직접 조정하고, 원 구현의
설정값 이름(`balloon.ratio`=0.4, `balloon.stop`=0.8)을 기본값으로 그대로
따른다.

## 동작 방식 (`controller/puff_manager.py`)

- **`puff(container)`**: OCM 상태의 컨테이너에게 호스트 메모리 여유가 있으면
  `memory.max`를 현재 한도의 `PUFF_RATIO`(기본 40%)만큼 늘린다. 단
  - 호스트 전체 메모리의 `HOST_STOP_RATIO`(기본 80%)를 넘어서까지는 늘리지
    않는다 — `get_host_assigned_mb()`로 실행 중인 모든 컨테이너의
    `memory.max` 합을 구해 현재 얼마나 배정돼 있는지 확인한다.
  - 늘어나는 양이 `MIN_PUFF_STEP_MB`(기본 16MiB)보다 작으면 의미가 없다고
    보고 포기한다. 원 구현은 대규모 YARN 클러스터 기준 1000MB를 임계값으로
    쓰지만, 이 실습은 32MiB 청크/256MiB 컨테이너 규모라 16MiB로 낮췄다.
  - puff하기 **전** 원래 한도를 `state/<container>_memory.json`에 최초 1회만
    저장해둔다(suspend_manager가 원래 CPU 설정을 저장하는 것과 같은 패턴).
- **`reclaim(container, amount_mb=None)`**: puff했던 컨테이너의 `memory.max`를
  줄인다. 저장해둔 원래 한도를 하한선(floor)으로 삼아 그 아래로는 절대
  내리지 않는다. `amount_mb`를 생략하면 원래 한도까지 전부 회수하고, 정확히
  floor에 도달하면 상태 파일을 지워 puff 상태를 해제한다.
- **`reclaim_host(target_free_mb)`**: 다중 컨테이너 환경을 염두에 둔 host
  레벨 진입점. 호스트 여유 메모리가 `target_free_mb`에 도달할 때까지, puff한
  적 있는 컨테이너들 중 **가장 최근에 puff한 것부터** 순서대로 `reclaim`을
  호출한다(원 구현이 "가장 최근에 balloon한 컨테이너부터 reclaim"하는 것과
  동일한 순서 — 영향받는 컨테이너 수를 최소화하기 위함).

`container_monitor.py`는 OCM을 감지하면 기존의 `suspend_manager.suspend()`
호출에 더해 `puff_manager.puff()`도 함께 시도한다(1차에서 검증된 suspend
동작 자체는 그대로 유지). `resume()`과 마찬가지로 `reclaim`은 이 단계에서는
자동으로 트리거하지 않고 수동/CLI로만 호출한다 — 언제 얼마나 reclaim할지
결정하는 host 레벨 정책(다중 컨테이너 우선순위 등)은
[3차](03-multi-container-reclaim.md) 범위다.

## 실행 명령어

`pf-test`가 [1차](01-ocm-suspend.md) 절차대로 떠 있는 상태에서:

```bash
cd controller

# 수동 puff/reclaim
python3 puff_manager.py puff pf-test
python3 puff_manager.py reclaim pf-test                  # 원래 한도까지 전부 회수
python3 puff_manager.py reclaim pf-test --amount-mb 50   # 50MiB만 회수
python3 puff_manager.py reclaim-host --target-free-mb 500  # 호스트 여유 500MiB 확보될 때까지 puff했던 컨테이너들을 순서대로 reclaim
```

## 검증 결과

`puff_manager.py`를 실행 중이던 `pf-test`(당시 `memory.max=256MiB`)에 대해
CLI로 직접 확인했다.

- `puff pf-test` 2회 연속 호출 → `256MiB → 358MiB → 501MiB`로 매번 정확히
  40%씩 늘어나고, cgroup `memory.max`에 그대로 반영됨을 확인. `memory-swap`도
  cgroup v2에서는 `memory.swap.max`(=swap 전용 한도, `--memory-swap` 값에서
  `--memory`를 뺀 값)로 분리 저장되는데, `SWAP_HEADROOM_MB=128` 그대로
  `memory.swap.max=128MiB`로 반영됨을 확인.
- `reclaim pf-test --amount-mb 50` → `501MiB → 451MiB`로 요청한 만큼만 줄고
  floor(256MiB) 아래로는 내려가지 않음을 확인.
- `reclaim pf-test`(전체 회수) → 정확히 floor `256MiB`로 복귀하고 상태 파일이
  삭제됨을 확인.
- puff한 적 없는 컨테이너에 `reclaim` 호출 → 안전하게 아무 동작 없이 `0`
  반환.
- `reclaim-host --target-free-mb <호스트 전체의 99.9%>` → 여유가 부족한
  상황을 만들어주면 puff했던 `pf-test`를 floor까지 reclaim해 목표 여유를
  확보함을 확인.

`container_monitor.py`에 붙인 자동 puff 트리거(OCM 감지 시 suspend와 함께
호출)는 코드 반영과 컴파일 확인(`python3 -m py_compile`)만 이 시점에 끝냈고,
실제 워크로드로 OCM을 발생시켜 자동 puff가 붙는지는 별도로 검증했다 —
아래 "자동 puff 검증" 참고.

## 자동 puff 검증 (`container_monitor.py` 연동)

[1차 실습](01-ocm-suspend.md#직접-실습해보기-단계별) 절차처럼 `pf-test`를
띄우고 모니터를 실행하면, OCM 감지 시 로그에
`puff 완료, 새 메모리 한도 ...MiB`가 찍히는 것을 확인했다. 다만 워크로드가
청크(예: 32MiB)를 한 번에 다 터치하면서 순간적으로 `memory.current +
memory.swap.current`가 급증할 수 있는데, 이 증가가 monitor의 폴링 주기
(500ms)와 `puff()` 내부 `docker update` 실행 시간보다 빠르면 실제 커널
cgroup OOM killer가 puff보다 먼저 컨테이너를 SIGKILL할 수 있다
(`docker inspect <container> --format 'OOMKilled={{.State.OOMKilled}}
ExitCode={{.State.ExitCode}}'`로 확인 가능, `ExitCode=137`이면 SIGKILL).

즉 `SWAP_HEADROOM_MB`(고정 128MiB)와 `CHUNK_SIZE_MB`, monitor `--interval`
사이의 비율이 puff의 안정성에 직접 영향을 준다 — 청크 크기가 헤드룸 대비
너무 크거나 폴링 주기가 너무 길면, puff가 따라잡기 전에 OOM-kill이 먼저
발생할 수 있다.

이와 별개로 3차(다중 컨테이너) 실습 과정에서 OCM 판정 로직 자체의 blind spot도
발견해 수정했다 — swap이 이미 포화 상태(`swap_current ≈ swap_max`)면
delta 기반 판정이 영구히 0이 되어 OCM이 재감지되지 않는 문제였다. 수정 내용은
[01-ocm-suspend.md의 OCM 판정 로직](01-ocm-suspend.md#ocm-판정-로직),
재현·검증 과정은 [03-multi-container-reclaim.md](03-multi-container-reclaim.md)
참고. 청크 버스트 레이스 자체(위 문단)는 여전히 청크 크기/헤드룸 조정으로
완화하는 수준이며, 근본 해결(예: 헤드룸을 `memory.max`에 비례하게 조정)은
미해결 과제로 남아 있다.
