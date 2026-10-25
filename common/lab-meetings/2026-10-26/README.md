# 2026-10-26 랩미팅 — 발표 준비 패키지 (다른 AI 인계용)

> 실험 기록 원문은 각 패키지 `steps/`에 있고, 여기선 요약 + 링크만 둔다.
> `talking-points.md`는 **10/24 기준**(일부 오래됨). 이 README가 최신(10/25 저녁)이다 — 충돌하면 이 문서를 따를 것.

## 0. 인계받는 AI에게

- 목적: 이 폴더와 아래 링크 문서로 **랩미팅 발표 자료(PPT용 슬라이드 흐름·문장)**를 만든다
- 청중: 지도교수님 + 연구실. 발표자는 학부연구생 과정 학생
- 표기 규칙(발표에서도 유지): **[논문]** 논문 본문(페이지) / **[원 구현]** 저자 공개 코드(파일:줄) / **[실측]** 우리가 측정·실행한 결과 / **[추측]** 해석
- 추측을 사실처럼 쓰지 말 것. 숫자는 아래 출처 문서의 값만 사용
- **PPT 서식 (항상 지킬 것)**
  - 글꼴: 모든 글자를 **맑은 고딕**으로 (제목·본문·표·도표 라벨 포함)
  - 색: **최대 3개**까지만 사용 (검정·흰색 같은 기본색도 개수에 포함해서 3개 이하)
- 먼저 읽을 문서 (저장소 루트 기준)
  1. 이 README
  2. `original-hadoop2.7/README.md` — 패키지 진행 상황
  3. `original-hadoop2.7/arm-mac/steps/05-hadoop-dist-task-image.md` (§3 jar 검증, §6·§7 이미지·JDK 분석)
  4. `original-hadoop2.7/arm-mac/steps/06-single-node-yarn-pi.md` (기동·pi·Flex 발견·CPU 문제)
  5. `common/pufferfish-architecture.md` (논문 vs 원 구현 대조, §2.5)
  6. `talking-points.md` (10/24 기준 발표 메모 — §3-1 빌드 이슈, §4 예상 질문은 여전히 유효)
- **꼭 별도 슬라이드로 넣을 것**: §3-4(MapReduce로는 puff/suspend 안 됨), **§3-5(JDK 7 vs 8 고민 — 발표자 요청)**, §3-6(CPU 1개 → x86 전환)

## 1. 한 줄 메시지

**"원 저자 코드를 수정 없이 논문 소프트웨어 환경에서 처음으로 실행했다(pi 성공). 그 과정에서 맥(ARM)의 한계를 확인했고, 교수님 지원으로 x86 VM에서 정식 실험을 진행한다."**

## 2. 흐름 (지난 피드백 → 이번 주)

| 날짜  | 내용                                                                                    |
| ----- | --------------------------------------------------------------------------------------- |
| 10/7  | 피드백: 외부 데몬(A안) 중단, 원 코드 활용                                               |
| 10/11 | 결정: 원 코드 그대로 재현(B안)                                                          |
| 10/22 | 결정: "논문 당시 환경을 최대한 똑같이" → Ubuntu 16.04 + Docker 1.12.1                   |
| 10/24 | 16.04 VM 구성, 원 코드 빌드, 공식 2.7.3 + 원 저자 YARN jar 교체·검증, task 이미지 1차   |
| 10/24 | task 이미지 JDK 8로 잘못 진행 → JDK가 메커니즘 입력을 바꾼다는 분석 후 **JDK 7로 복귀** |
| 10/25 | 단일 노드 HDFS/YARN 기동, pi 성공, JDK 7 이미지(CentOS 7) 완성, CPU 1개 문제 발견       |
| 10/25 | 교수님께 보고 → **연구실 x86 VM 할당 결정**, 설치 스크립트 준비                         |

## 3. 이번 주 결과 (슬라이드 핵심)

### 3-1. 논문 환경 맞추기 [실측]

| 항목        | 논문 [논문 p.265]                                                                | 현재 (맥 VM)                           |
| ----------- | -------------------------------------------------------------------------------- | -------------------------------------- |
| OS          | Ubuntu 16.04                                                                     | Ubuntu 16.04.7, 커널 4.4 ✅            |
| Docker      | 1.12.1                                                                           | 1.12.1 (2016-10-14 빌드) ✅            |
| YARN        | 2.7.3 (Pufferfish 기반)                                                          | 원 저자 코드 무수정 ✅                 |
| cgroup      | 미명시 (원 구현은 v1 하드코딩 [원 구현])                                         | v1 + `swapaccount=1` ✅                |
| task 이미지 | `sequenceiq/hadoop-docker:2.4.0` [원 구현 README] (CentOS 6.5 + Oracle JDK 7u71) | CentOS 7 + OpenJDK 7 ⚠️ (ARM이라 대체) |
| CPU         | x86, 8코어 × 2                                                                   | ARM, **1개만 인식** ❌                 |

### 3-2. 원 코드 빌드 — 무수정 원칙 유지 [실측]

- 실행 코드는 수정 없이 컴파일 성공. 원 저자 **테스트 코드 1곳**(`MockNodes.java:99`) 오류로 배포 묶음(tar.gz) 단계만 실패
- 대응: 공식 Hadoop 2.7.3 바이너리 + 원 저자 YARN jar 13개 교체
- **동일성 검증**: Common·HDFS·MR 약 7,300 class를 시그니처 비교 → 차이 4개 전부 컴파일러 자동 생성 `access$` 메서드(JDK 7/8 차이) → 소스 동일 (05 §3)
- 원 저자가 실제 수정한 jar: `yarn-api`, `server-common`, `nodemanager`(+`NodeMemoryManager` 등 8 class 추가), `resourcemanager`

### 3-3. 원 구현 첫 실행 [실측]

- 단일 노드 HDFS/YARN 기동, task가 **DockerContainerExecutor로 Docker 컨테이너에서 실행**됨 (`docker ps` 확인)
- pi 2 10: JDK 7 이미지 6/6 성공, 평균 21.17 ± 2.55초 (참고: JDK 8 20.44초, 지난 Hadoop 3.5.0 13.0초)
- lazy reclaim 경로 호출 확인 (`NodeMemoryManager: memory reclaim called`) — 여유 있어 실제 회수는 없음
- ⚠️ 시간 비교는 성능 결론이 아님 (1 CPU, ARM, 2회차부터 일정한 약 22초 대기 원인 미확인)

### 3-4. 중요한 발견 — pi(MapReduce)로는 puff/suspend가 안 돈다 [원 구현]

- Flex 컨테이너가 되는 조건: **AM의 node label expression이 `flex`일 때만** (`RMAppManager.java:330-360`)
- MapReduce 2.7.3은 AM node label을 지정할 설정이 없음 → 모든 컨테이너 REGULAR (로그 `set to be normal`, Flex 0개)
- 원 README는 "MapReduce는 하드코딩해 뒀다"고 하지만 **공개 저장소엔 그 코드가 없음** (MR 모듈 변경 0건)
- Spark는 `spark.yarn.am.nodeLabelExpression flex`로 가능 → **Pufferfish 동작 확인엔 Spark 2.0.1 필수**

### 3-5. ★ 고민: task 이미지 JDK 7 vs 8 — 별도 슬라이드 1~2장으로 [원 구현 + 추측]

> 발표자 요청으로 꼭 넣을 내용. "질문 → 분석 → 결정 → 확인" 흐름으로 구성.
> 원문: `original-hadoop2.7/arm-mac/steps/05-hadoop-dist-task-image.md` §6·§7, 노션 "10월 24일 task 이미지 JDK 7 vs 8 고민"

**① 질문** — task 이미지의 OS·JDK가 원 저자와 다르면 puff·reclaim·CPU 1% suspend 결과가 달라지나?

- 배경: 원 저자 이미지(`sequenceiq/hadoop-docker:2.4.0` = CentOS 6.5 + Oracle JDK 7u71)는 x86 전용 → 맥(ARM)에선 못 씀
- 처음엔 Ubuntu 16.04 + **JDK 8**로 만들었음 (Ubuntu 16.04 저장소엔 JDK 7이 없어서) → 원래 계획(JDK 7)과 다름을 발견하고 다시 검토

**② 분석 1 — 메커니즘 자체는 이미지와 무관** [원 구현]

- OCM 판정(`memory + swap > limit`)·suspend(`docker update --cpu-quota 1000 --cpuset-cpus 0`)·puff·reclaim은 모두 컨테이너 **바깥**(NodeManager + cgroup v1)이 처리
- 컨테이너 안 OS는 커널을 공유 → **베이스 OS(CentOS/Ubuntu)는 무관**

**③ 분석 2 — 하지만 JDK는 메커니즘의 "입력"을 바꿈**

- 원 코드가 Flex 컨테이너의 `-Xmx`를 **64GB로 강제 치환** (`DockerContainerExecutor.java:353-366`) [원 구현]
  → 힙이 컨테이너 한도를 넘어 swap → OCM → puff로 받아내는 설계
  → **JVM이 힙을 언제·얼마나 늘리는지**가 OCM·puff 횟수를 결정

| 차이 | JDK 7u71 (원 저자) | JDK 8u292 (처음 만든 이미지) |
|---|---|---|
| JVM이 보는 메모리 | 호스트 RAM | 컨테이너 한도 (8u191부터 cgroup 인식) [사실] |
| 기본 GC | Parallel GC | 한도 약 1.8GB 미만이면 Serial GC [추측] |
| 클래스 메타데이터 | PermGen (힙 영역) | Metaspace (힙 밖) [사실] |

| 메커니즘 | 판단 로직 | 입력 변화의 영향 [추측] |
|---|---|---|
| OCM 감지 | 같음 | 감지 시점·횟수 달라짐 (중간) |
| puff | 같음 | 횟수·최종 크기 달라짐 (중간) |
| CPU 1% suspend | 같음 | 제한 동작은 같음, 횟수만 달라짐 (작음) |
| reclaim | 같음 | 트리거 같음, 회수량 간접 영향 (작음~중간) |

**④ 결정** — JDK 7 계열(CentOS 7 + OpenJDK 7)로 복귀

- 메커니즘 입력을 원 저자와 같은 계열로 유지. CentOS도 원 이미지(CentOS 6.5) 계열
- 대안(JDK 8 + `-XX:-UseContainerSupport -XX:+UseParallelGC`)은 "맞춤"이 아니라 "흉내"라 차선

**⑤ 확인** [실측]

- 걱정 1 — ARM용 JDK 7이 JIT 없는 Zero VM이면 실험 불가 → **Server VM(JIT 포함) 확인**
- 걱정 2 — JDK 7은 지원 종료(EOL) → 빠지는 건 보안 패치뿐. 환경 전체가 의도적 당시 버전, Hadoop 2.7·Spark 2.0.1 모두 JDK 7 지원
- JDK 7 이미지로 pi 6/6 성공, task가 실제로 JDK 7로 실행됨 확인

**⑥ 남은 점 (솔직하게)**

- 맥 VM은 CPU 1개라 JDK 7·8 모두 Serial GC → GC 차이는 **아직 실측 못 함** (§3-6)
- 검증 계획: x86 VM에서 같은 워크로드를 JDK 7/8 이미지로 돌려 OCM·puff 횟수, swap 최대치, 완료 시간 비교

**발표 포인트 (발표자 노트용)**: "이미지가 달라도 Pufferfish 판단 로직은 같지만, 원 코드가 힙을 64GB로 풀어 두는 구조라 JVM 버전이 메커니즘의 입력을 바꿉니다. 그래서 원 저자와 같은 JDK 7 계열로 맞췄고, 실제 영향은 x86에서 7/8 비교로 확인하겠습니다."

### 3-6. CPU 1개 문제 → x86 VM으로 [실측]

- VirtualBox엔 2 vCPU인데 게스트가 1개만 인식: VirtualBox 7.2가 주는 ACPI 6.3 형식(CPU 항목 82바이트)을 2016년 커널 4.4가 못 읽음 (`missing boot CPU MPIDR`)
- 영향 [추측]: suspend의 "코어 1개 제한"(`--cpuset-cpus 0`) 효과 구분 불가, GC가 Serial로 고정, 병렬 실행 불가
- HWE 커널 4.15 시도 → 부팅 멈춤 → 4.4로 복귀
- 근본 원인은 **CPU 종류(ARM vs x86)**: 원 이미지·CentOS 6.5·Oracle JDK·네이티브 라이브러리·protoc 패치·CPU 인식 문제가 모두 여기서 파생
- 10/25 교수님 x86 VM 할당 결정 (요청: 최소 4 vCPU / 16GB / 100GB, 권장 8 / 32 / 200, 최종 3대)

## 4. 결정 사항

| 날짜  | 결정                                                                                           |
| ----- | ---------------------------------------------------------------------------------------------- |
| 10/24 | 공식 2.7.3 + 원 저자 YARN jar 교체 방식 (동일성 검증 완료)                                     |
| 10/24 | task 이미지 JDK 7 계열 (노션 원래 계획 복귀)                                                   |
| 10/25 | 맥 VM = 연습, 연구실 x86 VM = 정식 실험 (`original-hadoop2.7/arm-mac/` vs `x86-server/`)       |
| 10/25 | 설치 과정 스크립트화 (`original-hadoop2.7/setup/`, arm64·amd64 자동 판별, 맥 VM에서 동작 확인) |

## 5. 교수님께 확인할 것

- [ ] x86 VM 사양·접속 방법 (회신 대기)
- [ ] x86 task 이미지: 원 `sequenceiq/hadoop-docker:2.4.0` 반입(다른 PC에서 `docker save`) vs CentOS 6.5 + JDK 7 직접 구성
- [ ] 클러스터 3대(control 1 + worker 2) 추가 요청 시점

## 6. 다음 계획

1. x86 VM 수령 → 커널 4.4·CPU 수 확인 → 설치 스크립트로 환경 구성 → pi
2. Spark 2.0.1 + Flex → OCM·suspend·puff·reclaim 로그 확인
3. baseline(공식 YARN jar) vs Pufferfish 단일 노드 비교 (HiBench, 작은 입력)
4. 3대 구성 → 클러스터 비교

## 7. 발표에서 피할 주장

- "논문은 cgroup v1 기반" ❌ → 논문은 미명시, **원 구현**이 v1
- "원 저자 코드에 MapReduce Flex 지원이 있다" ❌ → README 언급뿐, 공개 코드엔 없음
- "JDK 7/8의 GC 차이를 확인했다" ❌ → 현재 VM은 CPU 1개라 둘 다 Serial, 차이 미확인
- "pi 시간으로 성능 비교" ❌ → 동작 확인용, 성능 결론 아님
- "x86이면 모든 차이가 사라진다" ❌ → Docker Hub pull 불가(Docker 1.12.1 문제)·하드웨어 규모 차이는 남음

## 8. 예상 질문 (추가분, 기존은 talking-points §4)

| 질문                          | 답                                                                                                                                                                     |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 맥에서 한 작업은 버리는 건가? | 알아낸 것(빌드 우회, jar 검증, Flex 조건, env-whitelist, 이미지 우회)은 그대로 사용. 원 저자 YARN jar는 바이트코드라 그대로 복사. 다시 하는 건 설치뿐이고 스크립트화함 |
| 왜 Spark가 필수인가?          | 공개 코드의 Flex 판정이 AM node label `flex`뿐인데 MR 2.7.3은 지정 불가 (§3-4)                                                                                         |
| JDK 7은 지원 종료인데?        | 보안 패치만 없음. 환경 전체가 의도적 당시 버전, Hadoop 2.7·Spark 2.0.1 모두 JDK 7 지원                                                                                 |
