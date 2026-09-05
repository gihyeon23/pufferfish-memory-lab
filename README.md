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

각 단계의 실행 방법·검증 결과는 [`docs/experiments/`](docs/experiments/)에
단계별 문서로 정리돼 있다.

| 단계 | 내용 | 상태 | 문서 |
|---|---|---|---|
| 사전 준비 | Ubuntu VM, Docker Engine, cgroup v2 환경 구축 | 완료 | [environment.md](docs/environment.md) |
| 사전 준비 | 32MB씩 점진적으로 메모리를 할당하는 Java 워크로드 | 완료 | 아래 [현재 구현](#현재-구현-메모리-증가-워크로드) 참고 |
| 1차 | 논문 3장의 CPU 1% 제한 동작 재현 | 완료 | [01-ocm-suspend.md](docs/experiments/01-ocm-suspend.md) |
| 2차 | 논문 4장의 `puff()`/`reclaim()` 구현 | 완료 | [02-puff-reclaim-single.md](docs/experiments/02-puff-reclaim-single.md) |
| 3차 | 다중 컨테이너 환경에서 `reclaim()` 시나리오 검증 | 부분 완료 | [03-multi-container-reclaim.md](docs/experiments/03-multi-container-reclaim.md) |
| 4차 | 호스트 예산 부족 시 자동 `reclaim_host()` 트리거 (⚠️ 논문 재현 아님, 독자 확장 정책) | 구현 완료 (실습 검증 필요) | [04-host-reclaim-daemon.md](docs/experiments/04-host-reclaim-daemon.md) |
| 5차 | 신규 컨테이너 admission 시점 `reclaim_host()` 트리거 (논문 §4.3.1 lazy reclaim 재현) | 구현 완료 (실습 검증 필요) | [05-admission-reclaim.md](docs/experiments/05-admission-reclaim.md) |
| 6차 | `reclaim_host()` 대상 선정을 EJF 우선순위(논문 §4.3.3 기본 정책)로 교체 | 완료 | [06-priority-reclaim.md](docs/experiments/06-priority-reclaim.md) |

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

## controller (Python)

`controller/` 아래 스크립트는 컨테이너의 PID를 통해 `/proc/<pid>/cgroup`을
읽어 cgroup v2 경로를 알아낸다(cgroupfs/systemd 드라이버 어느 쪽이든 동작).

| 스크립트 | 역할 |
|---|---|
| `cgroup_utils.py` | cgroup 경로 탐색, 파일 파싱 등 공용 헬퍼 |
| `cgroup_precheck.py` | Docker cgroup 버전, host swap, `memory.swap.max`, `memory.stat`의 swap 관련 키 존재 여부를 사전 점검 |
| `swap_preflight.py` | 본 실험 전 dry-run — `memory.swap.current`가 실제로 0에서 증가하는지 확인. 증가하지 않으면 host/VM swap 설정부터 진단해야 한다 |
| `container_monitor.py` | 500ms 주기로 `memory.current`/`memory.max`/`memory.swap.current`/`memory.events`/`memory.stat`/`cpu.stat`을 폴링하고 OCM 여부를 판정 |
| `suspend_manager.py` | OCM 감지 시 CPU를 1%(cpuset 0번 코어)로 제한(`suspend`)하고, 저장해둔 원래 설정으로 복구(`resume`)하는 인터페이스 |
| `puff_manager.py` | OCM 감지 시 호스트에 여유가 있으면 컨테이너의 `memory.max`를 늘리고(`puff`), 필요하면 원래 한도까지 다시 줄이는(`reclaim`/`reclaim-host`) 인터페이스. `reclaim-host`의 대상 선정은 EJF(가장 나중에 생성된 컨테이너부터) 정책을 따름 |
| `host_reclaim_daemon.py` | 호스트 메모리 예산이 부족해지면 `puff_manager.reclaim_host()`를 자동으로 호출하는 감시 데몬 (컨테이너별이 아니라 호스트당 하나만 실행, ⚠️ 논문 재현 아님 — 이 프로젝트의 독자 확장 정책) |
| `admission.py` | 신규 컨테이너를 `docker run`으로 띄우기 전 가용 메모리를 확인하고, 부족하면 `reclaim_host()`를 호출한 뒤 실행하는 래퍼 (논문 §4.3.1의 실제 reclaim 트리거 재현) |

```bash
cd controller
python3 cgroup_precheck.py pf-test     # 사전 점검
python3 swap_preflight.py pf-test      # swap 발생 여부 dry-run
python3 container_monitor.py pf-test   # OCM 감지 + 자동 suspend + 자동 puff
python3 host_reclaim_daemon.py         # 호스트 예산 감시 + 자동 reclaim (호스트당 1개, 독자 확장 정책)

# 수동 suspend/resume, puff/reclaim
python3 suspend_manager.py suspend pf-test
python3 suspend_manager.py resume pf-test
python3 puff_manager.py puff pf-test
python3 puff_manager.py reclaim pf-test

# 신규 컨테이너 admission (논문 방식 reclaim 트리거)
python3 admission.py pf-test-new pufferfish/workload-java:latest --request-mb 512
```

이미지 빌드, 컨테이너 실행, 단계별 실습, 검증 결과 등 실험별 상세 절차는
[`docs/experiments/`](docs/experiments/)를 참고한다.

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
│   ├── puff_manager.py
│   ├── host_reclaim_daemon.py
│   └── admission.py
├── experiments/
│   ├── configs/
│   └── results/
├── docs/
│   ├── environment.md
│   ├── pufferfish-architecture.md
│   └── experiments/
│       ├── README.md
│       ├── 01-ocm-suspend.md
│       ├── 02-puff-reclaim-single.md
│       ├── 03-multi-container-reclaim.md
│       ├── 04-host-reclaim-daemon.md
│       ├── 05-admission-reclaim.md
│       └── 06-priority-reclaim.md
└── README.md
```

| 디렉터리 | 역할 |
|---|---|
| `workload-java` | 메모리 사용량을 증가시키는 Java 워크로드와 컨테이너 이미지 |
| `controller` | 모니터링, suspend/resume, puff/reclaim 제어 스크립트 |
| `experiments/configs` | 실험별 설정 파일 (현재 비어 있음) |
| `experiments/results` | 로그 및 측정 결과 (현재 비어 있음) |
| `docs` | 환경 구성 문서 |
| `docs/experiments` | 실험 단계별 실행 방법·검증 결과 문서 |

> `experiments/`(설정·로그 데이터)와 `docs/experiments/`(실행 방법 문서)는
> 이름은 비슷하지만 용도가 다르다 — 헷갈리지 않도록 주의.

---

## 다음 작업

- [x] Java 워크로드 Docker 이미지 구성
- [x] 컨테이너 초기 메모리 256MB 제한 (`--memory=256m --memory-swap=768m`)
- [x] cgroup의 메모리·swap·CPU 상태 수집 (`container_monitor.py`)
- [x] 메모리 부족 상황에서 CPU 사용률 1% 제한 (`suspend_manager.py`)
- [x] `puff()`/`reclaim()`을 통한 메모리 한도 증감 (`puff_manager.py`, 단일 컨테이너 기준 단위 동작·자동 트리거 모두 검증됨)
- [x] 다중 컨테이너 puff 경쟁 상황 재현, OCM 판정 로직의 swap 포화 blind spot 발견·수정
- [x] 호스트 예산 부족 시 자동으로 `reclaim_host()`를 호출하는 호스트 레벨 데몬 (`host_reclaim_daemon.py`, 구현 완료 — ⚠️ 논문 재현이 아닌 독자 확장 정책, 다중 컨테이너 경쟁 상황에서의 실습 검증은 예정)
- [x] 신규 컨테이너 admission 시점에만 `reclaim_host()`를 호출하는 논문 방식 lazy reclaim 재현 (`admission.py`, 구현 완료 — 실습 검증은 예정)
- [x] `reclaim_host()` 대상 선정을 EJF 우선순위(가장 나중에 생성된 컨테이너부터)로 교체, "최근 puff순" 대비 다르게 동작함을 검증
- [ ] 고정 메모리 방식과 동적 메모리 방식 비교
