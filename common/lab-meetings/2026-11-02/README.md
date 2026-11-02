# 2026-11-02 랩미팅 — 발표 준비 패키지 (다른 AI 인계용)

> 실험 기록 원문은 `original-hadoop2.7/x86-server/steps/`에 있고, 여기선 요약 + 링크만 둔다.
> 발표 메모·예상 질문: [talking-points.md](talking-points.md)

## 0. 인계받는 AI에게

- 목적: 이 폴더와 아래 링크 문서로 **랩미팅 발표 자료(PPT용 슬라이드 흐름·문장)**를 만든다
- 청중: 지도교수님 + 연구실. 발표자는 학부연구생 과정 학생
- 표기 규칙(발표에서도 유지): **[논문]** 논문 본문(페이지) / **[원 구현]** 저자 공개 코드(파일:줄) / **[실측]** 우리가 측정·실행한 결과 / **[추측]** 해석 / **[우리]** 논문·원 코드에 없어 우리가 정한 값
- 추측을 사실처럼 쓰지 말 것. 숫자는 아래 출처 문서의 값만 사용
- "논문이 틀렸다 / 거짓말" 같은 표현 금지 → "논문 설명과 공개 코드가 다르다"로
- **PPT 서식 (항상 지킬 것)**
  - 글꼴: 모든 글자를 **맑은 고딕**으로 (제목·본문·표·도표 라벨 포함)
  - 색: **최대 3개**까지만 사용 (검정·흰색 같은 기본색도 개수에 포함해서 3개 이하)
- 먼저 읽을 문서 (저장소 루트 기준)
  1. 이 README
  2. `original-hadoop2.7/README.md` — 진행 체크리스트
  3. `original-hadoop2.7/x86-server/steps/06-spark-flex.md` §7(06b 첫 OCM·puff·shrink), §8(06c)
  4. `original-hadoop2.7/x86-server/steps/08-hibench-config.md` §2·§6 (★ 우리가 정한 값)
  5. `original-hadoop2.7/x86-server/steps/07-hibench.md` §2 (HiBench 버전 근거)
  6. `original-hadoop2.7/x86-server/steps/09-fig6a-puff.md` §5 (★ Fig 6(a) 재현 결과 + 그래프 `09-fig6a/fig6a.png`)
  7. `common/pufferfish-architecture.md` "원 공개 구현의 puff/reclaim 흐름" 표
  8. 이 README §9 — 오늘(11/01) 커밋 기록 (슬라이드 순서의 뼈대)
- **꼭 별도 슬라이드로 넣을 것 (발표자 요청)**: §3-5 "논문에 없어 우리가 정한 값", §3-4 shrink 2GB vs ×1.1, §3-7 Fig 6(a) 재현 (논문 그래프와 나란히)

## 1. 한 줄 메시지

**"x86 VM에서 원 저자 환경(원 task 이미지 포함)을 그대로 맞췄고, HiBench로 논문 Fig 6(a)를 1/4 규모로 재현해 puff → stop ballooning → 최저 우선순위 kill → 재시작 차단까지 확인했다. 다만 kill 횟수와 job별 메모리 비율은 논문과 다르다."**

## 2. 흐름 (지난 랩미팅 10/26 → 이번 주)

| 날짜 | 내용 |
|---|---|
| 10/26 | 지난 랩미팅: x86 VM 전환 결정, 3대(master 1 + worker 2) 사양 메일 |
| 11/01 | x86 VM 1대 수령 (worker 사양 8 vCPU / 32GB / 200GB) → 설치 스크립트로 환경 구성 |
| 11/01 | task 이미지: 원 `sequenceiq/hadoop-docker:2.4.0` 반입 성공 → DCE pi 성공 |
| 11/01 | swap 32GB, 워커 메모리 설정(YARN 28GB, MAX_HEAP 16GB) |
| 11/01 | Spark 2.0.1 + Flex 확인 → OCM·suspend·puff·shrink 관찰 (06b) → 재실행·원 코드 분석 (06c) |
| 11/01 | HiBench 6.0 빌드, 실행 조건·데이터 1/4 설정 |
| 11/01 | PR·KM 단독 예비 실험 → **Fig 6(a) 재현** (PR 1 + KM 2) |

## 3. 이번 주 결과 (슬라이드 핵심)

### 3-1. x86 VM 환경 = 원 저자 환경 [실측]

| 항목 | 논문 / 원 구현 | x86 VM |
|---|---|---|
| OS·커널 | Ubuntu 16.04 [논문 p.265] | 16.04.7, 커널 4.4, x86_64, vCPU 8개 모두 인식 ✅ |
| Docker | 1.12.1 [논문 p.265] | 1.12.1, aufs, cgroupfs, cgroup v1 + `swapaccount=1` ✅ |
| YARN | 원 저자 코드 | 공식 2.7.3 + 원 저자 YARN jar 13개 ✅ |
| task 이미지 | `sequenceiq/hadoop-docker:2.4.0` [원 구현 README] (안쪽 Hadoop 2.4.0) | **원 이미지 그대로 반입** (CentOS 6.5 + Oracle JDK 7u51) ✅<br>단 안쪽 Hadoop은 **2.7.3으로 교체** — NM이 호스트 경로(`HADOOP_*_HOME`)를 컨테이너에 넣어서 호스트와 경로를 맞춤 (steps/03 §4·§7) ⚠️ |
| Spark | 2.0.1 [논문 p.265] | 2.0.1 ✅ |
| 메모리 (1/4 축소) | 노드 128GB, YARN 120GB, MAX_HEAP 64GB, MIN_CONT 4GB [논문 p.265] | 32GB, 28GB, 16GB, 1GB [우리: 1/4] |

- 원 이미지는 Docker 1.12.1·최신 Docker 모두 pull 불가 → 레지스트리 API로 레이어를 직접 받아 sha256 검증 후 `docker load` (steps/03)
- 정정: 지난 발표의 "원 저자 JDK 7u71"은 2.7.1 태그 기준. 원 저자가 테스트한 2.4.0 태그는 **7u51** (steps/03 §3)
- 지난 발표에서 말한 **JDK 7/8 비교 계획은 취소**: 원 이미지(JDK 7u51)를 그대로 쓸 수 있게 돼서 비교할 필요가 없어짐 (steps/03 §2)

### 3-2. 첫 관찰 — OCM → suspend → puff → shrink [실측, steps/06 §7]

- Spark executor가 Flex로 판정되고 `-Xmx16384m`으로 치환됨 (`--memory-swap -1`)
- executor에 6GB를 cache → 컨테이너 1536MB 초과
  - OCM 감지: mem 1535 / limit 1536 + swap 134M → `out of memory contianer detected` (`ContainerImpl.java:1143`, 원문 오타)
  - suspend: CPU quota 1000(1%) + cpuset 0 [논문 p.260과 일치]
  - puff: 1536 → 2150 → 3010 → 4214 → 5899MB, **정확히 ×1.4** (ϕ=40%) [논문 p.263과 일치]
  - shrink: 5899 → 5216MB
- 노드 메모리에 여유가 있어서 `stop ballooning`·kill·reclaim은 아직 안 일어남 → Fig 6 재현 실험에서 확인 예정

### 3-3. backoff — 원 코드는 job 단위, 논문 본문과 일치 [논문 + 원 구현 + 실측]

- 06c: 같은 앱의 executor 2개가 같은 라운드에서 **둘 다 ×1.4** [실측]
- 원 코드: 같은 앱의 컨테이너는 같은 비율, 앱 하나를 처리한 뒤 `ϕ /= 앱 수` (`NodeMemoryManager.java:308-345`)
- 논문 본문: "assigns the same puff ratio to tasks belonging to the same job" [p.265] → **일치**
- Algorithm 1 의사코드(`Nc = C.size()`, 컨테이너마다 `ϕ /= Nc`) [p.264]만 문자 그대로면 컨테이너 단위 → 의사코드를 단순화한 것으로 봄 [추측]
- 처음엔 "차이"로 기록했다가 p.265 문장을 찾아 정정함 (발표에서 정정 과정도 짧게)

### 3-4. ★ shrink 여유분: 논문 2GB vs 원 코드 ×1.1 — 별도 슬라이드

| 논문 [p.264] | 원 코드 | 실측 |
|---|---|---|
| "50GB → 70GB로 puff, 실제 수요 60GB → **62GB로 shrink (2GB overhead by default)**" | `target = (mem + swap) × 1.1`, `SLACK_FACTOR = 1.1` 하드코딩 (`ContainerImpl.java:663, 1204-1217`) | 06b: (4157 + 585) × 1.1 = **5216** ✅, (3236 + 98) × 1.1 = **3667** ✅ / 06c에서도 같은 식으로 일치 |

- 논문 예시 기준이면 62GB(2GB 고정) vs 66GB(10%)
- 우리 규모(수요 수 GB)에선 10%가 2GB보다 작음 → 여유가 적게 남음
- 06c: shrink 뒤 앱 종료 중 **OCM이 다시 발생**해 puff 4826 → 6756 [실측] — 원인은 단정 못 함 [추측: executor 종료 과정]
- 원인 추측 [추측]: 공개 코드(2018-02 마지막 코드 변경) ≠ 논문 실험 코드일 가능성, 또는 논문 예시 단순화
- 결정: 원 코드 재현이 목적이라 ×1.1 그대로 사용, 결과 해석 때 명시

### 3-5. ★★ 논문에 없어 우리가 정한 값 — 별도 슬라이드 (발표자 "꼭 말해야 함")

> 원문: `x86-server/steps/08-hibench-config.md` §2·§6, `07-hibench.md` §2
> 원칙: 논문 "We follow the **default configuration of Spark and Hadoop, except we change the application heap size**" [p.265] → 논문에 있는 값만 지정, 나머지는 기본값

| 항목 | 정한 값 | 근거 | 결과에 주는 영향 [추측] |
|---|---|---|---|
| HiBench 버전 | **6.0** | 논문·원 코드에 없음. 원 저자 저장소 로그 날짜(2017-02-06) 시점 최신 = 6.0 (7.0은 2017-11) | 워크로드 구현 차이 (작음) |
| executor 코어 | **1** | 논문에 없음. "Spark 기본 설정" 문장 → Spark on YARN 기본값 1 (HiBench 템플릿은 4) | **실행 시간, OCM·puff 시점** (아래) |
| parallelism | Spark 기본 (HiBench의 8 덮어쓰기 제거) | 같은 문장 | task당 데이터 크기 → task별 메모리 |
| driver 메모리 | Spark 기본 1g (HiBench 4g 제거) | 같은 문장 | 작음 |
| KM·PR·NW 세부 파라미터 | HiBench 기본값 | 논문 규모(KM 1×10⁸, PR 5×10⁶)가 HiBench `huge` 프로파일과 같음 | — |

- 논문에 있어서 그대로 따른 값: executor 수 1 (Table 1 Small), MIN_CONT → `spark.executor.memory` 1g, 데이터는 Table 1 Small의 1/4 (WC 25GB, KM 2.5×10⁷, PR 1.25×10⁶, NW 2.5×10⁶)
- **코어 수가 결과에 주는 영향** (발표 핵심)
  - 코어 = executor JVM 안에서 동시에 도는 task 수
  - 코어 ↑ → 실행 시간 ↓, 메모리 증가 속도 ↑ → OCM·puff가 더 일찍·촘촘히, task별 작업 메모리 합 ↑
  - 안 바뀌는 것: cache 데이터 크기, Pufferfish 규칙(OCM 판정, ×1.4, ×1.1)
  - Pufferfish와 baseline을 같은 설정으로 비교하면 상대 비교(Fig 7 정규화 makespan)는 유효
  - 1코어로 실행 시간이 너무 길면 다시 결정 → **교수님 의견 여쭙기**

### 3-6. 원 코드 reclaim — 논문 강조점과 다른 부분 (나중에 확인할 문제) [논문 + 원 구현]

- 논문: "Reclaiming starts from the OCM container with the **lowest priority**" [p.264]
- 원 코드 (`NodeMemoryManager.java:392-470`)
  - 1단계: suspend(OCM) 중인 Flex 컨테이너에서 **필요량 ÷ 개수로 균등 회수**, 우선순위 정렬 없음
  - 2단계: 부족하면 puff됐지만 suspend가 아닌 컨테이너를 **늦게 시작한 순**으로 회수
  - 회수는 요청량(MIN_CONT)까지 내릴 수 있음 (`ContainerImpl.java:1234`)
- 영향: 앱 2개 이상이 동시에 OCM일 때만 드러남 → Fig 6(b) 재현 때 앱 2개를 동시에 OCM으로 만들어 실측 예정
- 기타 차이(참고): OCM 집합 유지 "2분"[p.264] ↔ 5라운드, puff 상한 노드 메모리 ↔ ×0.8, suspension tolerance ↔ 고정 10라운드

### 3-7. ★ Fig 6(a) puff() 재현 — 별도 슬라이드 (논문 그래프와 나란히) [실측, steps/09 §5]

- 그래프: `original-hadoop2.7/x86-server/steps/09-fig6a/fig6a.png` (실선 = 실제 사용량, 점선 = 컨테이너 크기, × = kill)
  - 논문 그래프는 `common/papers/pufferfish-paper.pdf` p.265 Figure 6(a)
- 구성: PR 1개 → 120초 뒤 KM1 → 120초 뒤 KM2, job마다 Flex executor 1개·1코어·1g, 데이터 1/4
  - 제출 간격 120초는 [우리] (6(a)엔 없음, 같은 절 Fig 7의 값)
- 예비 실험(단독): PR 753초·최대 사용 10.4GB, KM 476초·최대 사용 12.4GB

| job | 실행 시간 (단독 대비) | kill |
|---|---|---|
| PR (container-1) | 900초 (753초) | 0번 |
| KM1 (container-2) | 1124초 (476초) | 2번 |
| KM2 (container-3) | 1321초 (476초) | 3번 |

| 논문 Fig 6(a) [p.265] | 우리 | |
|---|---|---|
| 먼저 온 PR이 우선 puff, KM은 억눌림 | PR은 kill 없이 계속 puff, KM이 suspend·kill | ✅ |
| 노드가 차면 가장 늦은 container-3 kill | 첫 kill = KM2 (323초), `stop ballooning` 0.799 → 10라운드 후 `memory conflicts kill` | ✅ |
| 재시작이 메모리 부족으로 막힘 | KM2 재시작 184초 대기, RM `memflexn actual memory give up` 373회 | ✅ |
| kill 1번 | **kill 5번** (KM1·KM2가 번갈아) | ❌ |
| 메모리 비율 PR ≫ KM (약 60GB : 27GB) | PR ≈ KM (약 10GB : 10~11GB) | ❌ |

- 원 코드 근거 [원 구현]
  - kill 대상 = 가장 늦게 시작한 앱 중 Flex 컨테이너가 있는 앱 (`NodeMemoryManager.java:355-385`) → KM2 executor가 재배정 대기 중이면 KM1이 대상
  - RM: Flex 컨테이너는 노드 실제 여유가 요청의 2배 이상일 때만 배정 (`LeafQueue.java:1551-1569`) = 논문 cluster scheduler plugin [p.264]
- kill이 많은 이유 [추측]: 1/4 규모에서 KM 하나가 노드의 약 44%를 씀 (논문 약 23%) → KM 2개가 서로 밀어냄
- 발표 문장: "Fig 6(a)의 메커니즘 — 우선순위 puff, puff 정지, 가장 늦은 컨테이너 kill, 재시작 차단 — 은 전부 재현됐습니다. 다만 우리 축소 규모에선 KMeans 비중이 커서 kill이 1번이 아니라 5번 났고, 데이터 비율을 논문에 맞추는 조정을 다음에 해 보겠습니다."

## 4. 결정 사항

| 날짜 | 결정 |
|---|---|
| 11/01 | task 이미지 = 원 `sequenceiq/hadoop-docker:2.4.0` 반입, JDK 7/8 비교 취소 |
| 11/01 | swap 32GB swapfile, YARN 28GB, MAX_HEAP 16GB, `balloon.*`는 원 코드 기본값(ratio 0.4, stop 0.8, reclaim 0.9) |
| 11/01 | shrink ×1.1 등 원 코드 동작은 수정하지 않고 결과 해석 때 명시 |
| 11/01 | HiBench 6.0, executor 1개·1코어·1g, 나머지 Spark 기본값, 데이터 Table 1 Small의 1/4 |
| 11/01 | VM 1대로 단일 노드 실험 먼저, 원 코드 문제(reclaim 균등 분할 등)는 환경 세팅 후 |
| 11/01 | Fig 6(a): 제출 간격 120초, HiBench가 만든 spark-submit을 직접 실행(동시 실행 시 출력 폴더 충돌 회피) |

## 5. 교수님께 확인할 것

- [ ] **VM 추가 할당**: 받은 VM은 worker 1대분. master 1대(4 vCPU / 8GB / 100GB) + worker 1대가 더 가능한지. 어려우면 worker 1대만 추가하고 master 역할은 worker에 같이 올리는 방법도 가능
- [ ] **VM 디스크 HDD/SSD** (논문은 HDD → swap 속도 차이 해석용)
- [ ] executor 1코어(논문 "기본 설정" 문장 해석)로 진행해도 되는지
- [ ] 원 저자 문의 메일 (shrink 여유분, MR Flex, 코드 버전, HiBench 버전) — 보내도 되는지
- [ ] Fig 6(a) 데이터 비율: 1/4 그대로 둘지, 논문의 PR:KM 메모리 비율에 맞춰 조정할지

## 6. 다음 계획 (단일 노드)

1. ~~PR·KM 데이터, 예비 실험, Fig 6(a)~~ → 완료 (11/01)
2. Fig 6(a) 데이터 비율 조정 후 재실행 검토, WC·NW 데이터 생성
3. 입력 규모 예비 실험 (PR을 1GB/16GB 힙으로) + YARN 28GB 여유 점검
4. TPC-H(Spark-SQL) 준비 + baseline(공식 YARN jar) 전환 → **Fig 6(b)(c) reclaim 재현**
5. Fig 7 container parallelism (힙 1·2·4·8·16GB vs PF)
6. VM 추가되면 3대 구성 → 다중 노드 실험

## 7. 발표에서 피할 주장

- "reclaim을 확인했다" ❌ → 호출 로그만 봄, 실제 회수는 아직 없음 (Fig 6(a)의 kill은 puff 쪽 kill, reclaim 아님)
- "Fig 6(a)를 똑같이 재현했다" ❌ → 메커니즘은 재현, kill 횟수(5 vs 1)·메모리 비율은 다름
- "실행 시간이 논문보다 빠르다/느리다" ❌ → 하드웨어·1/4 규모·1코어라 절대 시간 비교 불가
- "논문과 원 코드의 backoff가 다르다" ❌ → p.265 본문과 일치, 의사코드만 다름
- "shrink 후 OCM 재발은 ×1.1 때문" ❌ → 앱 종료 중이라 원인 단정 못 함
- "HiBench 6.0이 논문 버전" ❌ → 논문·원 코드에 버전 없음, 근거 있는 선택일 뿐
- "1코어가 논문 설정" ❌ → 논문에 코어 수 없음, "기본 설정" 문장의 해석
- "x86 VM은 디스크가 SSD/HDD" ❌ → 아직 모름

## 9. 오늘(2026-11-01) 커밋 기록 — 슬라이드 순서의 뼈대

> 브랜치 `feat/x86-vm-sequenceiq-image` (push 전). 시간순

| 시각 | 커밋 | 내용 | 관련 README 절 |
|---|---|---|---|
| 14:28 | `424efe5` | x86 VM 단일 노드 구성, 원 task 이미지(sequenceiq 2.4.0) 반입, pi 성공, swap 32GB | §3-1 |
| 14:52 | `b69bab8` | 워커 메모리 설정 (YARN 28GB, MAX_HEAP 16GB) | §3-1 |
| 15:00 | `d285f22` | Spark 2.0.1 설치 + Flex 컨테이너 동작 확인 (06a) | §3-2 |
| 15:13 | `667162f` | Flex executor에서 OCM → suspend → puff → shrink 관찰 (06b) | §3-2 |
| 15:21 | `97b09f1` | shrink 여유분 — 논문 2GB vs 원 코드 ×1.1 | §3-4 |
| 16:36 | `d5d79fb` | 06c — 두 번째 읽기 개선, backoff 원 코드, shrink 후 OCM 재발 | §3-3, §3-4 |
| 16:36 | `431efaf` | HiBench 6.0 빌드 (07) | §3-5 |
| 16:53 | `b8cb96f` | backoff 정정 — 원 코드 앱 단위 = 논문 본문(p.265) | §3-3 |
| 16:53 | `6e53a2f` | HiBench 설정 — executor 1개·1코어·1g, Spark 기본값, 데이터 1/4 (08) | §3-5 |
| 16:53 | `ba72d59` | 이 랩미팅 자료 첫 작성 | — |
| 이후 | (Fig 6(a) 커밋) | PR·KM 예비 실험 + Fig 6(a) 재현 (09) | §3-7 |

