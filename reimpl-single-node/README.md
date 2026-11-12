# reimpl-single-node — Python controller 재구현 (완료)

논문의 노드 레벨 메커니즘(OCM 감지, CPU 1% suspend, puff/reclaim, admission 시점 lazy reclaim, EJF)을
Python controller로 직접 구현해 단일 호스트(Docker + cgroup v2)에서 검증했다.

| 폴더 | 내용 |
|---|---|
| [controller/](controller/) | cgroup 모니터·suspend·puff/reclaim·admission — 반드시 `cd reimpl-single-node/controller` 후 실행 |
| [workload-java/](workload-java/) | 메모리를 점진적으로 늘리는 Java 워크로드 + 이미지 |
| [experiments/](experiments/) | 1~10차 실행 방법·검증 결과 (인덱스: [experiments/README.md](experiments/README.md)) |
| [evidence/](evidence/) | 원본 로그 등 검증 근거 |
| [experiments/swap-off-latency/](experiments/swap-off-latency/) | 9/21 랩미팅 swap 차단 실험 (발표 자료는 [`common/lab-meetings/2026-09-21/`](../common/lab-meetings/2026-09-21/)) |

- 7차(다중 노드 설계)는 [reimpl-hadoop3/docs/](../reimpl-hadoop3/docs/)로 옮김

---

> 아래는 2026-11-12까지 루트 README에 있던 내용 (맥 ARM VM 단일 노드 재구현)

## 구현 단계

각 단계의 실행 방법·검증 결과는 [`experiments/`](experiments/)에
단계별 문서로 정리돼 있다.

| 단계 | 내용 | 상태 | 문서 |
|---|---|---|---|
| 사전 준비 | Ubuntu VM, Docker Engine, cgroup v2 환경 구축 | 완료 | [environment.md](../common/environment.md) |
| 사전 준비 | 32MB씩 점진적으로 메모리를 할당하는 Java 워크로드 | 완료 | 아래 [현재 구현](#현재-구현-메모리-증가-워크로드) 참고 |
| 1차 | 논문 3장의 CPU 1% 제한 동작 재현 | 완료 | [01-ocm-suspend.md](experiments/01-ocm-suspend.md) |
| 2차 | 논문 4장의 `puff()`/`reclaim()` 구현 | 완료 | [02-puff-reclaim-single.md](experiments/02-puff-reclaim-single.md) |
| 3차 | 다중 컨테이너 환경에서 `reclaim()` 시나리오 검증 | 부분 완료 | [03-multi-container-reclaim.md](experiments/03-multi-container-reclaim.md) |
| 4차 | 호스트 예산 부족 시 자동 `reclaim_host()` 트리거 (⚠️ 논문 재현 아님, 독자 확장 정책) | 구현만 완료, **후속 과제로 보류** (논문 재현이 우선) | [04-host-reclaim-daemon.md](experiments/04-host-reclaim-daemon.md) |
| 5차 | 신규 컨테이너 admission 시점 `reclaim_host()` 트리거 (논문 §4.3.1 lazy reclaim 재현) | 라이브 검증 완료 | [05-admission-reclaim.md](experiments/05-admission-reclaim.md) |
| 6차 | `reclaim_host()` 대상 선정을 EJF 우선순위(논문 §4.3.3 기본 정책)로 교체 | 완료 | [06-priority-reclaim.md](experiments/06-priority-reclaim.md) |
| 7차 | 멀티 노드 클러스터(마스터 1 + 워커 2) — 논문 §4.3.2 클러스터 레벨 재현 | 설계만 완료 (구현 전) | [07-multi-node-cluster.md](../reimpl-hadoop3/docs/07-multi-node-cluster.md) |
| 8차 | `reclaim()`이 실사용량 아래로 못 내려가게 하는 안전 하한선 추가 (즉시 OOM-kill 버그 수정) | 완료 | [08-reclaim-safety-floor.md](experiments/08-reclaim-safety-floor.md) |
| 9차 | 5·6·8차 통합 단일 노드 최종 검증 | 완료 | [09-single-node-final.md](experiments/09-single-node-final.md) |
| 10차 | 컨테이너별 swap 상한(`SWAP_HEADROOM_MB`) 128 → 512MiB | 라이브 검증 완료 | [10-swap-headroom-512.md](experiments/10-swap-headroom-512.md) |

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

환경 구성에 대한 자세한 내용은 [`common/environment.md`](../common/environment.md)에서 확인할 수 있습니다.

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
cd reimpl-single-node/workload-java

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

`reimpl-single-node/controller/` 아래 스크립트는 컨테이너의 PID를 통해 `/proc/<pid>/cgroup`을
읽어 cgroup v2 경로를 알아낸다(cgroupfs/systemd 드라이버 어느 쪽이든 동작).

| 스크립트 | 역할 |
|---|---|
| `cgroup_utils.py` | cgroup 경로 탐색, 파일 파싱 등 공용 헬퍼 |
| `cgroup_precheck.py` | Docker cgroup 버전, host swap, `memory.swap.max`, `memory.stat`의 swap 관련 키 존재 여부를 사전 점검 |
| `swap_preflight.py` | 본 실험 전 dry-run — `memory.swap.current`가 실제로 0에서 증가하는지 확인. 증가하지 않으면 host/VM swap 설정부터 진단해야 한다 |
| `container_monitor.py` | 500ms 주기로 `memory.current`/`memory.max`/`memory.swap.current`/`memory.events`/`memory.stat`/`cpu.stat`을 폴링하고 OCM 여부를 판정 |
| `suspend_manager.py` | OCM 감지 시 CPU를 1%(cpuset 0번 코어)로 제한(`suspend`)하고, 저장해둔 원래 설정으로 복구(`resume`)하는 인터페이스 |
| `puff_manager.py` | OCM 감지 시 호스트에 여유가 있으면 컨테이너의 `memory.max`를 늘리고(`puff`), 필요하면 원래 한도까지 다시 줄이는(`reclaim`/`reclaim-host`) 인터페이스. `reclaim-host`의 대상 선정은 EJF(가장 나중에 생성된 컨테이너부터) 정책을 따르고, `reclaim`은 실사용량(memory.current) 아래로는 내리지 않음 |
| `host_reclaim_daemon.py` | 호스트 메모리 예산이 부족해지면 `puff_manager.reclaim_host()`를 자동으로 호출하는 감시 데몬 (컨테이너별이 아니라 호스트당 하나만 실행, ⚠️ 논문 재현 아님 — 이 프로젝트의 독자 확장 정책) |
| `admission.py` | 신규 컨테이너를 `docker run`으로 띄우기 전 가용 메모리를 확인하고, 부족하면 `reclaim_host()`를 호출한 뒤 실행하는 래퍼 (논문 §4.3.1의 실제 reclaim 트리거 재현) |

```bash
cd reimpl-single-node/controller
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
[`experiments/`](experiments/)를 참고한다.

---

## 다음 작업

- [x] Java 워크로드 Docker 이미지 구성
- [x] 컨테이너 초기 메모리 256MB 제한 (`--memory=256m --memory-swap=768m`)
- [x] cgroup의 메모리·swap·CPU 상태 수집 (`container_monitor.py`)
- [x] 메모리 부족 상황에서 CPU 사용률 1% 제한 (`suspend_manager.py`)
- [x] `puff()`/`reclaim()`을 통한 메모리 한도 증감 (`puff_manager.py`, 단일 컨테이너 기준 단위 동작·자동 트리거 모두 검증됨)
- [x] 다중 컨테이너 puff 경쟁 상황 재현, **이 프로젝트의 delta 기반 OCM 판정**에 있던 swap 포화 blind spot 발견·수정 (논문·원 공개 구현의 결함이 아님 — [pufferfish-architecture.md](../common/pufferfish-architecture.md) §2.5 참고)
- [x] 호스트 예산 부족 시 자동으로 `reclaim_host()`를 호출하는 호스트 레벨 데몬 (`host_reclaim_daemon.py`, 구현만 완료 — ⚠️ 논문 재현이 아닌 독자 확장 정책이라 논문 재현 트랙이 끝날 때까지 검증은 후속으로 보류)
- [x] 신규 컨테이너 admission 시점에만 `reclaim_host()`를 호출하는 논문 방식 lazy reclaim 재현 (`admission.py`, 구현 완료 — 실습 검증은 예정)
- [x] `reclaim_host()` 대상 선정을 EJF 우선순위(가장 나중에 생성된 컨테이너부터)로 교체, "최근 puff순" 대비 다르게 동작함을 검증
- [x] `reclaim()`이 실사용량(memory.current) 아래로 못 내려가게 하는 안전 하한선 추가 — reclaim 직후 즉시 OOM-kill되던 버그를 라이브 테스트로 발견·수정
- [ ] **(9/21 랩미팅)** swap 차단(쿠버네티스 조건)에서 OOM killer 동작 확인 + 할당 응답시간 측정 — [lab-meetings/2026-09-21.md](../common/lab-meetings/2026-09-21/2026-09-21.md)
- [x] **(9/21 랩미팅)** 원 논문이 admission controller인지 검증 → 아니며 "elastic memory manager"임을 확인
- [x] **(9/21 랩미팅)** EJF 우선순위 심화 조사 → 논문은 우선순위를 3곳에 쓰나 현재는 reclaim 순서 1곳만 구현했음을 확인
- [x] 컨테이너별 swap 상한을 128 → 512MiB로 조정 (`SWAP_HEADROOM_MB`) — puff가 기동 시 swap 설정(512MiB)을 128MiB로 줄이던 부작용 제거. **라이브 재검증 완료**: 3대 전원 1024MiB 할당 완주·OOM 0, swap 실수요는 317~386MiB로 관측(2대 때 183~191MiB보다 큼 — puff로 한도가 커지면 swap 수요도 함께 커짐)
- [ ] 고정 메모리 방식과 동적 메모리 방식 비교
- [ ] 멀티 노드 클러스터(마스터 1 + 워커 2) — 논문 §4.3.2 클러스터 레벨 재현 (설계 완료, VM 세팅·구현은 예정)
- [ ] **(2단계 로드맵, 10/5)** YARN 클러스터(control 1 + worker 2) 구축 + 워크로드를 HiBench Kmeans로 교체,
      기존 controller를 외부 데몬(A안)으로 연결 — Step 0~9 작업 순서·버전 제약·리스크는
      [lab-meetings/2026-10-05/2026-10-05.md](../common/lab-meetings/2026-10-05/2026-10-05.md) 참고
