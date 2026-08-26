# Pufferfish Memory Lab

Pufferfish 논문의 컨테이너 기반 동적 메모리 관리 기법을  
Docker와 cgroup v2 환경에서 단계적으로 재현하는 실험 프로젝트입니다.

> 대상 논문  
> **Pufferfish: Container-driven Elastic Memory Management for Data-intensive Applications**  
> ACM SoCC 2019

---

## 프로젝트 목표

Pufferfish는 메모리가 부족한 컨테이너를 바로 종료하는 대신,
컨테이너의 실행을 제어하고 사용 가능한 메모리를 동적으로 재분배합니다.

이 프로젝트에서는 논문의 핵심 동작을 소규모 환경에서 다음 순서로 재현합니다.

1. 메모리 부족 컨테이너의 CPU 사용률을 1%로 제한
2. `puff()`를 이용한 컨테이너 메모리 한도 증가
3. 여러 컨테이너 환경에서 `reclaim()`을 통한 메모리 회수

---

## 구현 단계

| 단계 | 내용 | 상태 |
|---|---|---|
| 사전 준비 | Ubuntu VM, Docker Engine, cgroup v2 환경 구축 | 완료 |
| 사전 준비 | 32MB씩 점진적으로 메모리를 할당하는 Java 워크로드 | 완료 |
| 1차 | 논문 3장의 CPU 1% 제한 동작 재현 | 완료 |
| 2차 | 논문 4장의 `puff()`/`reclaim()` 구현 | 구현 완료 (실습 검증 필요) |
| 3차 | 다중 컨테이너 환경에서 `reclaim()` 시나리오 검증 | 예정 |

> 위 단계는 논문의 공식 단계 구분이 아니라, 본 재현 실험을 위해 정의한 구현 순서입니다.

---

## 실험 환경

| 항목 | 설정 |
|---|---|
| Host | MacBook Apple M4 |
| 가상화 | VirtualBox |
| Guest OS | Ubuntu Server 24.04 ARM64 |
| VM CPU | 2 cores |
| VM RAM | 약 4GB |
| VM Swap | 약 3.8GB |
| Container Runtime | Docker Engine |
| Resource Control | cgroup v2 |
| 개발 환경 | VS Code Remote-SSH |

환경 구성에 대한 자세한 내용은 [`docs/environment.md`](docs/environment.md)에서 확인할 수 있습니다.

---

## 현재 구현: 메모리 증가 워크로드

`MemoryGrowthWorkload`는 일정한 시간 간격으로 새로운 `byte[]` 배열을 생성해
Java 힙 메모리 사용량을 점진적으로 증가시킵니다.

### 동작 방식

1. 지정된 크기의 `byte[]` 배열 생성
2. 배열 전체에 값을 기록해 실제 메모리 사용 유도
3. 배열의 참조를 리스트에 보관해 Garbage Collection 방지
4. 설정된 주기만큼 대기
5. 최대 할당량에 도달할 때까지 반복

### 기본 설정

| 환경 변수 | 기본값 | 설명 |
|---|---:|---|
| `CHUNK_SIZE_MB` | 32 | 한 번에 증가하는 메모리 |
| `INTERVAL_SECONDS` | 5 | 메모리 증가 간격 |
| `MAX_ALLOCATION_MB` | 512 | 최대 누적 할당량 |

---

## 실행 방법

### 컴파일

```bash
cd workload-java

mkdir -p out

javac \
  -d out \
  src/main/java/lab/pufferfish/MemoryGrowthWorkload.java
```

### 기본 설정으로 실행

```bash
java -cp out lab.pufferfish.MemoryGrowthWorkload
```

### 환경 변수를 지정해 실행

```bash
CHUNK_SIZE_MB=32 \
INTERVAL_SECONDS=5 \
MAX_ALLOCATION_MB=512 \
java -cp out lab.pufferfish.MemoryGrowthWorkload
```

실행 시 다음과 같이 누적 할당량이 증가합니다.

```text
Allocated: 32 MB
Allocated: 64 MB
Allocated: 96 MB
...
```

---

## 1차: OCM 감지 및 CPU 1% 제한

메모리가 부족해 swap이 발생하는 컨테이너(OCM: On-Container Memory
pressure)를 감지하면, 컨테이너를 종료하지 않고 `docker update`로 CPU를
1%(코어 0번만)로 제한해 heartbeat만 유지시킨다. `docker pause`는 사용하지
않는다 — Pufferfish의 suspend는 완전 정지가 아니라 소량의 CPU를 남겨두는
방식이기 때문이다.

### 컨테이너 이미지 빌드 및 실행

```bash
cd workload-java
docker build -t pufferfish/workload-java:latest .

docker run -d --name pf-test \
  --memory=256m --memory-swap=768m \
  -e JAVA_OPTS="-Xmx700m" \
  pufferfish/workload-java:latest
```

- RAM 한도는 256MiB(`--memory`), RAM+swap 합산 한도는 768MiB(`--memory-swap`)로
  설정한다. 즉 swap 여유는 512MiB다. 768MiB는 논문의 값이 아니라 이 워크로드가
  OOM-kill 전에 OCM으로 감지될 수 있도록 잡은 PoC용 헤드룸이며, 이후
  unrestricted 실행에서 실제 peak 사용량을 측정해 조정할 수 있다.
- `--memory-swappiness`는 사용하지 않는다. cgroup v2에서는 이 옵션 대신 실제
  swap 가능 여부(`memory.swap.max`)와 `memory.stat`으로 상태를 직접 확인한다.
- `JAVA_OPTS`로 JVM 플래그를 주입할 수 있다. 컨테이너 메모리 한도(256MiB) 내에서
  JVM이 기본으로 잡는 최대 힙은 그보다 작아서, 힙이 cgroup 메모리 한도를
  실제로 넘어서게 하려면 `-Xmx`를 명시적으로 크게 잡아야 한다.

### controller (Python)

`controller/` 아래 스크립트는 컨테이너의 PID를 통해 `/proc/<pid>/cgroup`을
읽어 cgroup v2 경로를 알아낸다(cgroupfs/systemd 드라이버 어느 쪽이든 동작).

| 스크립트 | 역할 |
|---|---|
| `cgroup_utils.py` | cgroup 경로 탐색, 파일 파싱 등 공용 헬퍼 |
| `cgroup_precheck.py` | Docker cgroup 버전, host swap, `memory.swap.max`, `memory.stat`의 swap 관련 키 존재 여부를 사전 점검 |
| `swap_preflight.py` | 본 실험 전 dry-run — `memory.swap.current`가 실제로 0에서 증가하는지 확인. 증가하지 않으면 host/VM swap 설정부터 진단해야 한다 |
| `container_monitor.py` | 500ms 주기로 `memory.current`/`memory.max`/`memory.swap.current`/`memory.events`/`memory.stat`/`cpu.stat`을 폴링하고 OCM 여부를 판정 |
| `suspend_manager.py` | OCM 감지 시 CPU를 1%(cpuset 0번 코어)로 제한(`suspend`)하고, 저장해둔 원래 설정으로 복구(`resume`)하는 인터페이스 |
| `puff_manager.py` | OCM 감지 시 호스트에 여유가 있으면 컨테이너의 `memory.max`를 늘리고(`puff`), 필요하면 원래 한도까지 다시 줄이는(`reclaim`/`reclaim-host`) 인터페이스 |

```bash
cd controller
python3 cgroup_precheck.py pf-test     # 사전 점검
python3 swap_preflight.py pf-test      # swap 발생 여부 dry-run
python3 container_monitor.py pf-test   # OCM 감지 + 자동 suspend + 자동 puff

# 수동 suspend/resume (테스트/1차 이후 확장용)
python3 suspend_manager.py suspend pf-test
python3 suspend_manager.py resume pf-test

# 수동 puff/reclaim (테스트/2차 이후 확장용)
python3 puff_manager.py puff pf-test
python3 puff_manager.py reclaim pf-test                  # 원래 한도까지 전부 회수
python3 puff_manager.py reclaim pf-test --amount-mb 50   # 50MiB만 회수
python3 puff_manager.py reclaim-host --target-free-mb 500  # 호스트 여유 500MiB 확보될 때까지 puff했던 컨테이너들을 순서대로 reclaim
```

### 직접 실습해보기 (단계별)

터미널 창 2개를 띄워두고 따라 하면 편하다. 창 A에서 컨테이너 실행과 모니터를,
창 B에서 결과 확인을 한다.

**창 A**

```bash
# 0) 저장소 루트에서 시작
cd ~/pufferfish-memory-lab

# 1) 이미지 빌드
cd workload-java
docker build -t pufferfish/workload-java:latest .
cd ..

# 2) 컨테이너 실행 (이미 떠 있다면 먼저 정리)
docker rm -f pf-test 2>/dev/null
docker run -d --name pf-test \
  --memory=256m --memory-swap=768m \
  -e CHUNK_SIZE_MB=32 -e INTERVAL_SECONDS=2 -e MAX_ALLOCATION_MB=512 \
  -e JAVA_OPTS="-Xmx700m" \
  pufferfish/workload-java:latest

# 3) 로그로 워크로드가 정상 동작하는지 잠깐 확인 (Ctrl+C로 스트리밍만 중단, 컨테이너는 계속 실행됨)
docker logs -f pf-test

# 4) 반드시 controller 디렉터리로 이동한 뒤 모니터 실행
cd controller
python3 container_monitor.py pf-test --interval 0.5
```

`container_monitor.py`를 저장소 루트에서 그대로 실행하면
`can't open file '.../container_monitor.py': No such file or directory`
에러가 난다 — 흔한 실수이니 4번 단계에서 `cd controller`를 빼먹지 않는다.

> **팁: 2)와 4) 사이에 시간이 걸리면 증가 과정을 놓친다**
> `CHUNK_SIZE_MB=32`, `INTERVAL_SECONDS=2` 기준으로 컨테이너 실행 후 약
> 16초(8번째 할당) 만에 `memory.current`가 이미 256MiB 근처에 도달한다.
> 컨테이너를 띄우고 모니터를 붙이는 사이에 시간이 걸리면, 모니터 첫
> 스냅샷부터 `current`가 이미 255MiB 근처로 찍혀서 0MiB부터 올라가는
> 과정을 못 보게 된다. `&&`로 묶어 컨테이너 실행 직후 곧바로 모니터를
> 붙이면 이를 피할 수 있다.
> ```bash
> docker rm -f pf-test 2>/dev/null
> docker run -d --name pf-test \
>   --memory=256m --memory-swap=768m \
>   -e CHUNK_SIZE_MB=32 -e INTERVAL_SECONDS=2 -e MAX_ALLOCATION_MB=512 \
>   -e JAVA_OPTS="-Xmx700m" \
>   pufferfish/workload-java:latest \
> && cd controller && python3 container_monitor.py pf-test --interval 0.5
> ```

모니터 로그에 다음 순서가 찍히면 정상 동작이다 (32MiB씩 쌓이다 256MiB를
넘는 시점, 대략 16번째 할당 전후에서 발생).

```
[container_monitor] pf-test: OCM 감지 (method=swap_current_delta_fallback, ...)
[suspend_manager] pf-test: 원래 CPU 설정 저장 ...
[suspend_manager] pf-test: suspend 적용 (--cpus 0.01 --cpuset-cpus 0)
[suspend_manager] pf-test: cgroup cpu.max='1000 100000' cpuset.cpus='0'
```

이미 `MAX_ALLOCATION_MB`까지 다 채우고 "최대 누적 할당량에 도달" 상태인
컨테이너로 모니터를 새로 실행하면, swap이 이미 정체 상태라 새로운 swap
activity가 안 잡혀 OCM이 감지되지 않을 수 있다 — 그럴 땐 컨테이너를 2번
단계로 다시 띄운다.

**창 B** (모니터는 창 A에서 계속 켜둔 채로)

```bash
# CPU 실사용률 확인 — suspend 이후 ~1%대로 떨어져야 한다
docker stats pf-test --no-stream

# cgroup 파일 직접 확인 (docker inspect의 CpuQuota/CpusetCpus는 부정확할 수 있어 신뢰하지 않는다)
PID=$(docker inspect --format '{{.State.Pid}}' pf-test)
CG=$(sed -n 's/^0:://p' /proc/$PID/cgroup)
cat /sys/fs/cgroup$CG/cpu.max      # 1000 100000 => 1%
cat /sys/fs/cgroup$CG/cpuset.cpus  # 0 => 0번 코어만
```

**정리**

```bash
docker rm -f pf-test
rm -f controller/state/*.json
```

**OCM 판정 로직**: `memory.current + memory.swap.current > memory.max` 이면서
swapping activity가 있을 때 OCM으로 판정한다. swapping activity는 우선
`memory.stat`의 `pswpin`/`pswpout` delta로 판단하되, 이 커널 버전처럼 해당
키가 없는 cgroup v2 환경에서는 `memory.swap.current`의 delta > 0을 fallback으로
사용한다(이 프로젝트의 실험 환경, 커널 6.8에서 실제로 확인됨).
`workingset_refault_anon`은 판정에 쓰지 않고 참고용으로만 로그에 남긴다.

**검증 결과**: `--memory=256m --memory-swap=768m -e JAVA_OPTS="-Xmx700m"`로
실행한 워크로드가 256MiB를 넘어서며 swap이 발생하고, `container_monitor.py`가
fallback 방식으로 OCM을 감지해 `suspend_manager.suspend()`를 호출, 실제
cgroup(`cpu.max`가 `1000 100000`, `cpuset.cpus`가 `0`)에 CPU 1% 제한이
적용되는 것을 확인했다. 제한 이후에도 컨테이너/JVM은 종료되지 않고 계속
동작하며(단, 진행 속도는 크게 느려짐), `resume()`은 저장해둔 원래 cgroup
상태(`cpu.max`, `cpuset.cpus`)로 정확히 복구한다.

---

## 2차: `puff()`/`reclaim()`로 메모리 한도 동적 조절

**알고리즘 출처**: 논문 4장이 설명하는 puff/reclaim은 논문 저자가 공개한
Hadoop YARN 구현([`yncxcw/pufferfish`](https://github.com/yncxcw/pufferfish)의
`NodeMemoryManager.MemoryBalloon()`/`MemoryReclaim()`,
`ContainerImpl.ContainerMonitor.reclaimMemory()`)을 참고해, 이 프로젝트의
단일 Docker 호스트/cgroup v2 환경에 맞게 옮겼다. YARN 버전은 NodeManager가
여러 컨테이너의 메모리를 중앙에서 조정하지만, 이 프로젝트는 `docker update
--memory/--memory-swap`으로 cgroup `memory.max`를 직접 조정하고, 원 구현의
설정값 이름(`balloon.ratio`=0.4, `balloon.stop`=0.8)을 기본값으로 그대로
따른다.

### 동작 방식 (`controller/puff_manager.py`)

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
결정하는 host 레벨 정책(다중 컨테이너 우선순위 등)은 3차 범위다.

### 검증 결과

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
호출)는 이번에 코드 반영과 컴파일 확인(`python3 -m py_compile`)만 했고,
실제 워크로드로 OCM을 발생시켜 자동 puff가 붙는지는 아직 실습 검증 전이다 —
1차 실습(`직접 실습해보기` 절차)처럼 `pf-test`를 다시 띄우고 모니터 로그에
`puff 완료, 새 메모리 한도 ...MiB`가 찍히는지 확인해봐야 한다.

---

## 프로젝트 구조

```text
pufferfish-memory-lab/
├── workload-java/
│   ├── src/main/java/lab/pufferfish/
│   │   └── MemoryGrowthWorkload.java
│   ├── Dockerfile
│   └── README.md
├── controller/
│   ├── cgroup_utils.py
│   ├── cgroup_precheck.py
│   ├── swap_preflight.py
│   ├── container_monitor.py
│   ├── suspend_manager.py
│   └── puff_manager.py
├── experiments/
│   ├── configs/
│   └── results/
├── docs/
│   └── environment.md
└── README.md
```

| 디렉터리 | 역할 |
|---|---|
| `workload-java` | 메모리 사용량을 증가시키는 Java 워크로드와 컨테이너 이미지 |
| `controller` | 모니터링, suspend/resume, puff/reclaim 제어 스크립트 |
| `experiments/configs` | 실험별 설정 파일 |
| `experiments/results` | 로그 및 측정 결과 |
| `docs` | 환경 구성 및 실험 설계 문서 |

---

## 다음 작업

- [x] Java 워크로드 Docker 이미지 구성
- [x] 컨테이너 초기 메모리 256MB 제한 (`--memory=256m --memory-swap=768m`)
- [x] cgroup의 메모리·swap·CPU 상태 수집 (`container_monitor.py`)
- [x] 메모리 부족 상황에서 CPU 사용률 1% 제한 (`suspend_manager.py`)
- [x] `puff()`/`reclaim()`을 통한 메모리 한도 증감 (`puff_manager.py`, 단위 동작은 검증됨, 실습 시나리오 검증은 예정)
- [ ] 다중 컨테이너 환경에서 `reclaim()` 시나리오 검증
- [ ] 고정 메모리 방식과 동적 메모리 방식 비교
