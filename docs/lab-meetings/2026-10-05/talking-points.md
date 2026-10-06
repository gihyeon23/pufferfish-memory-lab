# 발표 메모 — 교수님께 짚을 사항 (2단계: YARN 클러스터)

> 용도: 이 폴더의 md(로드맵 + Step 0~3)로 PPT를 만들 때 **슬라이드 흐름과 강조점**의 기준.
> 표기: **[논문]** 논문 본문 근거 / **[원 구현]** 저자 공개 코드 근거 / **[실측]** 우리 측정값 /
> **[추측]** 내 해석 — 발표에서도 이 구분을 유지한다.

## 1. 한 줄 메시지

- "처음부터 다시"가 아니라 **"메커니즘 검증 완료 → 논문과 같은 평가 환경으로 확장"**
- 1단계(1~10차): Pufferfish 메커니즘(OCM 감지·suspend·puff·reclaim·EJF·안전 하한선)을 단일 노드 Docker로 검증
- 2단계(지금): 논문 baseline인 **YARN + 실제 워크로드(HiBench Kmeans)** 위에서 효과를 측정

## 2. 추천 슬라이드 흐름

| # | 슬라이드 | 핵심 내용 | 출처 md |
|---|---|---|---|
| 1 | 현 위치 | 1단계 완료 항목 요약 → 2단계로 넘어가는 이유 | 2026-10-05.md §0 |
| 2 | 왜 YARN인가 | YARN = 기본 자원 관리자, Pufferfish = 그 위에 붙는 메모리 관리. 논문 비교 구도 = **YARN만 vs YARN + Pufferfish** | §3 아래 |
| 3 | 버전 결정 근거 | cgroup v2 지원은 **Hadoop 3.5.0부터** (9/30 메모의 "3.4 추정"은 틀렸음 → 정정) | 2026-10-05.md §2 |
| 4 | 자원 예산 | 맥 swap이 이미 86% 포화 → VM 3대 = 8.5 GB로 보수적 설계, worker 우선 보호 | 00-step0-baseline.md |
| 5 | 클러스터 구성 | control 1 + worker 2, NAT Network `pfnet`, 역할 배치 그림 | 01-step1-vm-setup.md |
| 6 | 진행 현황 | Step 0~3 완료 — 완료 기준과 실측값 표 (Step 3: NM 2대 RUNNING, pi SUCCEEDED, control 여유 609 MB) | 02, 03 md |
| 6-1 | `pi` 예제로 YARN 검증 | `pi`가 무엇인지(π 추정 MapReduce 예제) + 왜 검증에 쓰는지 + **5회 반복 결과**(5/5 성공, 중앙값 13.081초) | 03-step3-yarn.md |
| 7 | 앞으로의 단계 | Step 4~9 로드맵, **Step 8(controller ↔ YARN 연결)이 구현량 최대** | §3 Step 4~9 |
| 8 | 리스크 | HiBench 아카이브, container-executor·cgroup v2 설정, 호스트 메모리 | §5 |
| 9 | 확인 요청 | 아래 §5 질문 목록 | §4 |

## 3. 꼭 짚을 포인트

### 3-1. YARN과 Pufferfish의 관계 (가장 헷갈리기 쉬움)

- YARN: job을 받아 컨테이너에 **고정된** 메모리·CPU 할당. 남는 자원이 없어 보이면 다음 job은 대기
- Pufferfish: 실행 중 컨테이너의 메모리를 **유동적으로** 조절(puff/reclaim) → 더 많은 job 수용
- **[논문]** 구성 요소: Node Memory Manager(노드당 1) + Container Monitor(컨테이너당 1) +
  Cluster Scheduler Plugin (p.262~264). puff 주기도 NM↔RM heartbeat(2초)에 맞춤
- **[원 구현]** YARN 소스 **내부**에 구현 (예: OCM 판정이 NodeManager의 `ContainerImpl.java`에 있음)
- **우리(A안)**: YARN은 **수정하지 않고**, worker마다 외부 데몬(controller)이 YARN 컨테이너 cgroup을 감시·조절
  - **[추측]** 장점: YARN 3.5.0 재빌드 불필요, 1단계 Python controller 재사용
  - **[추측]** 한계: YARN 스케줄러는 puff/reclaim을 모름 → admission 쪽 연동(로드맵 8-4)이 별도로 필요
  - → "**YARN에 내장** vs **YARN 옆에 붙임**" 차이를 먼저 밝혀 두면 질문을 예방할 수 있음

### 3-2. 버전 결정은 조사로 정정된 것

- 9/30 메모: "cgroup v2 지원 YARN = 3.4 계열(추정)" → **틀렸음**
- 확인 결과: **3.5.0부터** (YARN-11669), 서버 측 **JDK 17 필수**
- Ubuntu 24.04는 기본이 cgroup v2 → 3.4.x를 쓰면 YARN cgroup 제어가 사실상 안 됨
- 정정한 사실을 숨기지 말고 "조사로 바로잡았다"로 보여주는 게 좋음

### 3-3. 측정 신뢰성 — 호스트 메모리

- **[실측]** VM 1대만 돌던 시점에 맥 swap 7052/8192 MB(86%)
- 그대로 VM 3대를 올리면 "워크로드 메모리 압박으로 느려진 것"과 "맥이 스왑해서 느려진 것"을 구분할 수 없음
- 대응: VM 합계 8.5 GB, worker 우선 배정, 측정 중 `sysctl vm.swapusage`를 같이 기록
- → 나중 결과의 신뢰성 질문에 미리 답하는 슬라이드

### 3-4. Step 3을 cgroup 없이 먼저 하는 이유

- 변수 최소화: 스케줄링 경로(job 제출 → 컨테이너 할당 → 완료)만 먼저 확인
- **R2 대비**: container-executor + cgroup v2 설정(Step 8-1)에서 오래 막혀도,
  **Step 7 baseline은 cgroup 없이 확보 가능** → 일정 리스크 분산
- `pi` 예제(MapReduce)를 Spark보다 먼저 돌려서 YARN 문제와 Spark 문제를 분리

### 3-4-1. `pi` 예제 — Hadoop 기본 제공 기능

- Hadoop 배포판에 들어 있는 MapReduce 예제(`hadoop-mapreduce-examples-3.5.0.jar`). 따로 만든 것이 아님
- 정사각형에 점을 찍어 내접원 안 비율로 **π를 추정** (준몬테카를로, 앱 이름 `QuasiMonteCarlo`)
- 슬라이드 포인트: "계산은 가볍지만 **AM → map → reduce → HDFS** 까지 YARN 전체 경로를 거치는 표준 동작 테스트"
- 그림 추천: 정사각형 + 내접원 + 점 (π ≈ 4 × 원 안 점 / 전체 점), 옆에 YARN 경로 화살표
- 5회 반복 결과 표를 같이 보여주면 **교수님이 요청한 반복·대표값(중앙값) 방식**을 이미 적용하고 있다는 신호가 됨
  - 5/5 SUCCEEDED, 중앙값 13.081초, 평균 13.001 ± 1.327초, 최소/최대 11.130/14.867초
  - 단, **성능 비교가 아니라 안정성 확인**이라는 점을 분명히 말할 것
- 예상 질문 대비: "π가 왜 3.8?" → 점 20개뿐 + 정해진 수열(Halton)이라 매번 같은 값. 정확도는 목적이 아님

### 3-4-2. 반복 측정·통계 기준 (교수님 요청 사항)

- Step 3(기능 확인)은 통과/실패 판정이라 통계 대상이 아님 → 안정성 확인용으로만 5회 반복
- **Step 6~9(성능 비교)**: 조건당 최소 5회, 대표값 = **중앙값**, 함께 평균 ± 표준편차, 최소/최대
- 최빈값은 연속값(완료시간)에서 의미가 거의 없어 생략 — 이유를 슬라이드에 한 줄로 밝힐 것
- 맥 swap 포화로 이상치가 생길 수 있어 평균보다 중앙값이 안전함

### 3-5. 표현 주의 — cgroup 버전

- 로드맵 §6에 "cgroup v2 조작 경험(논문은 v1)"이라고 적혀 있지만,
  **[논문] 본문은 cgroup 버전을 명시하지 않음** ([pufferfish-architecture.md](../../pufferfish-architecture.md) §3.1)
- 발표에서는 "논문은 v1"이 아니라 **"논문은 미명시, 2019년 Docker/YARN 기반이라 v1이었을 것으로 추정"**으로 말할 것

### 3-6. 1단계 자산의 연결

- 재사용: OCM 판정, suspend, puff, reclaim, EJF, 안전 하한선, 9/21 swap 실험 결과(suspend 86배 vs swap 3.6배)
- 수정: Docker 결합부(`docker inspect`/`docker update` → cgroup 파일 직접 write), 컨테이너 생명주기 추적
- 폐기: MemoryGrowthWorkload를 **평가** 워크로드로 쓰는 것 (단위 테스트용으로는 유지)
- → "1단계가 헛수고가 아니다"를 보여주는 근거

## 4. 예상 질문과 답

| 예상 질문 | 답 (근거) |
|---|---|
| 왜 Docker Swarm이 아니라 YARN? | 논문 baseline이 YARN 기본 동작. Swarm 역할은 교수님 확인 대기 (§5) |
| 왜 Hadoop 최신 3.5.0? 논문은 2019년인데 | cgroup v2 지원이 3.5.0부터. Ubuntu 24.04가 v2 기본이라 3.4 이하는 cgroup 제어 불가 |
| 노드 3대로 충분한가? | worker 2대 이상이어야 baseline(대기 발생)과 클러스터 레벨 비교가 성립. 호스트 16 GB 한계로 3대가 상한 |
| VM 메모리가 너무 작지 않나? | 맥 swap 포화 실측 때문에 보수적으로 설정. worker는 우선 보호, control은 부족하면 상향 (Step 3에서 재측정) |
| 원 구현과 결과가 다르면? | 원 구현은 YARN 내장 + `--oom-kill-disable` 등 실행 조건이 다름. 차이 목록을 architecture 문서에 이미 정리 |
| HiBench가 아카이브됐는데? | 패치 / 포크 / Spark MLlib KMeans 직접 작성(백업) 3안 (§5 R1) |

## 5. 교수님께 확인받을 것 (로드맵 §4에서 가져옴)

- [ ] Docker Swarm의 역할 — YARN과 병행 / 대체 / 제외 중 무엇인지
- [ ] Hadoop 3.5.0(2026-04 릴리스)으로 진행해도 되는지
- [ ] HiBench 아카이브 → 그대로 패치해서 쓸지, 대체 워크로드로 갈지
- [ ] (추가 제안) A안(외부 데몬)으로 가도 되는지 — 원 구현(YARN 내장)과 구조가 다르다는 점을 확인

## 6. 업데이트 규칙

- Step이 끝날 때마다 §2의 "진행 현황" 행과 §4의 답을 실측값으로 갱신
- Step 3 반영 완료 (2026-10-06): control available 609 MB, `pi` SUCCEEDED, NM RSS 274 MB
- 호스트 swap이 YARN 기동 후 5.78 GB까지 늘어남 → §3-3 슬라이드에 이 수치를 추가해도 좋음
