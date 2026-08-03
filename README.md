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
| 1차 | 논문 3장의 CPU 1% 제한 동작 재현 | 예정 |
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

## 프로젝트 구조

```text
pufferfish-memory-lab/
├── workload-java/
│   ├── src/main/java/lab/pufferfish/
│   │   └── MemoryGrowthWorkload.java
│   └── README.md
├── controller/
├── experiments/
│   ├── configs/
│   └── results/
├── docs/
│   └── environment.md
└── README.md
```

| 디렉터리 | 역할 |
|---|---|
| `workload-java` | 메모리 사용량을 증가시키는 Java 워크로드 |
| `controller` | 모니터링, `puff()`, `reclaim()` 제어 스크립트 |
| `experiments/configs` | 실험별 설정 파일 |
| `experiments/results` | 로그 및 측정 결과 |
| `docs` | 환경 구성 및 실험 설계 문서 |

---

## 다음 작업

- [ ] Java 워크로드 Docker 이미지 구성
- [ ] 컨테이너 초기 메모리 256MB 제한
- [ ] cgroup의 메모리·swap·CPU 상태 수집
- [ ] 메모리 부족 상황에서 CPU 사용률 1% 제한
- [ ] `puff()`를 통한 메모리 한도 증가
- [ ] 다중 컨테이너 환경에서 `reclaim()` 구현
- [ ] 고정 메모리 방식과 동적 메모리 방식 비교
