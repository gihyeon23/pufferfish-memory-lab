# 논문 환경 vs 재현 환경 차이

> 랩미팅: 2026-10-26 / 관련: [01-legacy-build.md](01-legacy-build.md), [pufferfish-architecture.md](../../../common/pufferfish-architecture.md)
>
> 표기: **[사실]** 논문·원 코드·실측으로 확인 / **[추측]** 내 해석 또는 확인 전

## 목적

- 논문 실험 환경과 현재 재현 환경의 차이를 한곳에 모아, 결과 보고 때 "무엇이 같고 무엇이 다른지"를 바로 보여준다
- 결론부터 (2026-10-24 갱신): **OS 16.04·Docker 1.12.1·YARN 2.7.3·JDK 8·cgroup v1까지 맞춤. 못 맞추는 것은 CPU 아키텍처(ARM), 하드웨어 규모, 컨테이너 이미지**

## 1. 논문 실험 환경 (p.265 "Cluster setup", "Pufferfish setting") [사실]

- 노드: 26대, 노드당 Intel Xeon E5-2640 ×2 (8코어, HT), RAM 128GB, 1TB HDD ×5 (RAID-5)
- 네트워크: 10Gbps Ethernet
- OS: Ubuntu 16.04
- YARN: 2.7.3 (Pufferfish 구현 기반, 비교 대상도 같은 버전)
- 노드당 YARN 메모리: 120GB (OS·데몬 제외)
- Spark: 2.0.1
- Docker: 1.12.1
- 컨테이너 이미지: Docker Hub `sequenceiq/hadoop-docker`
- Pufferfish 설정: puff 비율 ϕ = 40%, FLEX 컨테이너 MIN_CONT = 4GB, MAX_HEAP = 64GB
- 워크로드: HiBench (Wordcount, Terasort, Kmeans, PageRank, NWeight 등)

## 2. 항목별 비교

| 항목 | 논문 | 현재 재현 환경 | 맞출 수 있나 | 근거 |
|---|---|---|---|---|
| CPU 아키텍처 | x86_64 (Xeon) | **ARM64** (Apple M4, Mac16,12) | ❌ | 아래 모든 ❌의 근본 원인 |
| 노드 수 | 26 | VM 3대 (control 1 + worker 2) | ❌ | 호스트 RAM 16GB [사실] |
| 노드 메모리 | 128GB (YARN 120GB) | control 1.5GB / worker 3.5GB | ❌ | 호스트 swap 포화 실측 [사실, 00-step0-baseline.md] |
| OS | Ubuntu 16.04 | **Ubuntu 16.04.7** (`u1604-test`, 커널 4.4.0-186) | ✅ | 자동 설치 완료, 화면 출력 대신 시리얼 콘솔 [사실, [03](03-ubuntu1604-boot-test.md)·[04](04-ubuntu1604-env.md)] |
| YARN/Hadoop | 2.7.3 | **2.7.3** (원 저자 코드 빌드) | ✅ | pom `version 2.7.3` [사실] |
| JDK | 명시 없음 (2.7.3 시절 JDK 7/8) | **JDK 8** (1.8.0_292) | ✅ | Hadoop 2.7.x는 JDK 7/8 지원 [사실] |
| protoc | 2.5.0 (빌드 의존) | **2.5.0** (ARM64 패치 빌드) | ✅ | [01-legacy-build.md](01-legacy-build.md) §3 |
| cgroup | 논문 미명시 / 원 코드 **v1 하드코딩** | **v1** (16.04 기본) + `swapaccount=1` | ✅ | 원 코드 경로·옵션 동작 확인 [사실, [04](04-ubuntu1604-env.md) §3] |
| Docker | 1.12.1 | **1.12.1** (+ containerd 0.2.3, runc 1.0.0~rc1) | ✅ | Launchpad 보관소의 2016-10-14 xenial arm64 빌드 [사실, [04](04-ubuntu1604-env.md) §2] |
| Docker cgroup 드라이버 | (원 코드) cgroupfs 전제 | cgroupfs로 설정 | ✅ | 경로 `/docker/<id>` [사실] |
| 컨테이너 이미지 | `sequenceiq/hadoop-docker` (CentOS 6.5, JDK 7u71, Hadoop 2.7.1 / 원 코드 기본 태그 2.4.0) | `local/ubuntu:16.04` + JDK 8 + Hadoop 2.7.3 직접 제작 예정 | ❌ | 원 이미지 amd64 전용 [사실]. Docker 1.12.1은 현재 Docker Hub에서 pull 불가 [사실]. 쉬운 설명: [04](04-ubuntu1604-env.md) §2 |
| Spark | 2.0.1 | 2.0.1 사용 예정 | ✅ 대부분 | JVM 기반. snappy 등 네이티브 라이브러리 ARM 지원은 확인 필요 [추측] |
| puff 비율 ϕ | 40% | 40% (`balloon.ratio=0.4`) | ✅ | 원 코드 기본값 [사실] |
| MIN_CONT | 4GB | 축소 필요 | ⚠️ 비율 유지 | worker 3.5GB라 그대로 불가 |
| MAX_HEAP | 64GB (`balloon.jvm-mb`) | 축소 필요 | ⚠️ 비율 유지 | 위와 같음 |
| 워크로드 | HiBench | HiBench (Kmeans 우선) | ⚠️ | HiBench 아카이브됨, 입력 크기는 축소 필요 |

## 3. 차이가 결과에 미치는 영향 [추측]

- **영향 작음 — 메커니즘 재현에는 문제 없음**
  - Docker 버전: 원 코드가 쓰는 명령은 `docker run --memory --memory-swap -1 --oom-kill-disable`, `docker update --cpu-quota --cpuset-cpus --memory` 정도라 최신 Docker에도 있음. 단 `--oom-kill-disable`은 cgroup v1에서만 동작
  - OS: puff/suspend/reclaim은 YARN 코드 + cgroup v1 인터페이스로 동작 → cgroup v1만 맞추면 OS 버전 영향은 적음
- **영향 큼 — 성능 수치는 논문과 직접 비교 불가**
  - 노드 수·메모리 규모가 수십 배 작음 → 처리량·완료시간 **절대값** 비교는 의미 없음
  - 대신 **같은 환경에서 "YARN만 vs YARN + Pufferfish" 상대 비교**로 논문의 경향(개선 여부·방향)을 확인하는 게 목표
  - ARM vs x86: JVM 성능 특성이 달라 절대값은 더 벌어질 수 있음
  - 맥 swap 포화: VM 바깥(호스트) swap이 측정을 흔들 수 있음 → `sysctl vm.swapusage` 같이 기록

## 4. 선택지

| | A. 맥에서 핵심만 맞추기 (현재 진행) | B. x86 서버에서 소프트웨어까지 맞추기 |
|---|---|---|
| 맞추는 것 | YARN 2.7.3, JDK 8, cgroup v1, Spark 2.0.1, Pufferfish 설정 | A + Ubuntu 16.04, Docker 1.12.1, `sequenceiq/hadoop-docker` |
| 못 맞추는 것 | Docker·이미지·OS·하드웨어 | 하드웨어 규모 |
| 필요 조건 | 없음 (지금 VM 그대로) | 연구실 x86 서버 또는 클라우드 VM |
| 추가 작업 | ARM64용 task 이미지 직접 제작 | 없음 (옛 Docker 정적 바이너리 사용 [추측: download.docker.com에 보관]) |

- 현재 판단: **A안으로 진행**, 교수님이 "환경까지 동일"을 요구하시면 B안 (연구실 x86 서버 유무 확인 필요)

## 5. 남은 확인 항목

- [ ] Docker 1.12.1 ARM64 빌드 존재 여부 (B안 판단용)
- [ ] Docker 29가 cgroup v1에서 정상 동작하는지 (worker1 재부팅 후)
- [ ] Spark 2.0.1 네이티브 라이브러리 ARM64 동작 여부
- [ ] MIN_CONT / MAX_HEAP 축소 비율 결정 (논문 4GB : 64GB : 노드 120GB 비율 기준)
- [ ] 연구실 x86 서버 사용 가능 여부 (교수님께 질문)
