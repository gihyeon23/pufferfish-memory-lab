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
| 2차 | 논문 4장의 `puff()` 구현 | 예정 |
| 3차 | 다중 컨테이너 및 `reclaim()` 구현 | 예정 |

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

```bash
cd controller
python3 cgroup_precheck.py pf-test     # 사전 점검
python3 swap_preflight.py pf-test      # swap 발생 여부 dry-run
python3 container_monitor.py pf-test   # OCM 감지 + 자동 suspend

# 수동 suspend/resume (테스트/1차 이후 확장용)
python3 suspend_manager.py suspend pf-test
python3 suspend_manager.py resume pf-test
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
상태(`cpu.max`, `cpuset.cpus`)로 정확히 복구한다. `puff()`/`reclaim()`은 이
단계에서 구현하지 않는다.

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
│   └── suspend_manager.py
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
| `controller` | 모니터링, suspend/resume, 이후 `puff()`/`reclaim()` 제어 스크립트 |
| `experiments/configs` | 실험별 설정 파일 |
| `experiments/results` | 로그 및 측정 결과 |
| `docs` | 환경 구성 및 실험 설계 문서 |

---

## 다음 작업

- [x] Java 워크로드 Docker 이미지 구성
- [x] 컨테이너 초기 메모리 256MB 제한 (`--memory=256m --memory-swap=768m`)
- [x] cgroup의 메모리·swap·CPU 상태 수집 (`container_monitor.py`)
- [x] 메모리 부족 상황에서 CPU 사용률 1% 제한 (`suspend_manager.py`)
- [ ] `puff()`를 통한 메모리 한도 증가
- [ ] 다중 컨테이너 환경에서 `reclaim()` 구현
- [ ] 고정 메모리 방식과 동적 메모리 방식 비교
