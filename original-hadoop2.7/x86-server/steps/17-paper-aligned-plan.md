# 17. 논문 기준으로 전환 — 진행 순서 (2026-11-12)

## 결정 (교수님 논의)

- 기준: **논문 Fig 6(a) 그래프와 같게**. 조건은 논문 명시 내용이 1순위
- 논문에 맞춰 원 코드를 고친 결과 = **본 결과**. 원 코드 그대로(09~16)는 비교용
- executor **1코어** 확정. 입력은 논문 Table 1 비율(PR 2배 안 씀)

## 방법

원 코드에서 논문과 다른 곳을 **하나씩** 논문대로 고침 → 실행 → 논문 그래프와 비교. 앞 단계 수정은 유지(누적).

- 시작점: 14 (원 코드, 1코어, 제출 0초, puff 2초, 4회)
- 비교 지표 (`setup/fig6a-metrics.py`): PR이 가장 크고 오래 / stop 전 shrink 수 / kill 수 (논문 1) / 전체 시간 (논문 약 1790초)
- 추가 지표 (11-13, 본문 p.265~266 서술): **첫 kill 시각 (논문 약 600초)**, KM2 재시작 막힘 (논문 600~1050초), PR shrink (논문 약 880초) — [architecture §2.4](../../../common/pufferfish-architecture.md)
  - 첫 kill [실측]: 14 → 148~167초, A → 177~203초, B r1 → 155초. 모든 실행에서 시작 약 3분 안에 kill 1번 — 논문엔 없음 (KM은 "처음에 억눌림")

## 순서

경로 접두어 `hadoop-yarn-server-nodemanager/.../nodemanager/`. 상세 [architecture §2](../../../common/pufferfish-architecture.md)

| 단계 | 고칠 곳 | 논문 | 원 코드 | 기대 변화 | 이유 (순서) |
|---|---|---|---|---|---|
| A | shrink 대기 | e.g. 2분 [p.264] | 약 18초 (`NodeMemoryManager.java:102, 166-177`) | stop 전 shrink 감소 | 그래프 차이 가장 큼, 패치 있음 (11·16) |
| B | kill 시점 (Alg.1 4~6행) | 노드 꽉 참 + 최우선 OCM → 그 라운드에 최저 우선순위 kill [p.264] | 11라운드(약 22초) 연속일 때 kill (`:289-301`) | kill 시점·수 변화 | 지금까지 kill 전부가 이 경로 (14·A 8회 모두) |
| C | shrink 여유분 | +2GB [p.264] | ×1.1 (`ContainerImpl.java:663, 1204, 1217`) | shrink 뒤 크기 | 그래프 점선 높이 |
| D | reclaim 대상 | 최저 우선순위부터 [p.264] | 균등 분할 | 어느 job이 줄어드는지 | 새 job 시작 때만 영향 |
| E | puff 상한·"꽉 참" 기준 | M 기준 puff·kill (A ≥ M) [p.264 Alg.1] | 0.8에서 puff 정지·kill 판단, 0.9 이상 OCM 무관 kill (`:245-251`) | puff 최대 크기, kill 수 | B 결과와 함께 봐야 함 |
| F | 제출 간격 (실험 조건, 코드 아님) | "one by one" [p.265], 숫자 없음. 그래프에서 KM 선이 약 30~45초에 보임 (그래프 읽기) | 우리 `fig6a.sh 0` → KM executor가 PR보다 4~14초 뒤 [실측] | 첫 kill·첫 shrink 시각 | 후보 15초 1회. C 512/2GB 비교·결정 뒤 진행 (11-15 사용자) |
| G (후보) | job별 메모리 수요 (실험 조건) | 단독 수요 PR 약 60GB (그래프) · KM 61GB [p.266] / 노드 120 → 합 약 150%. Fig 6(a)의 KM 약 27GB는 억눌린 값 | 단독 PR 10.4 · KM 12.4GB (09) / 노드 28 → 합 약 126% [실측] | KM 억눌림, 전체 시간 | 우리가 덜 과부하 → KM이 거의 다 받음 (**추측**). 입력을 늘려 150%로 맞추는 안 |

## 단계마다 정할 것 (사용자)

- 반복 횟수
- A: 라운드 수 (2초 주기 → 약 60), B와 분리할지
- ~~B: "job 예상 기간"을 무엇으로 줄지~~ → 정정 (아래 "B 정정")
- C: 2GB 그대로 / 규모 1/4로 512MB
- F: 간격 초 (후보 15), C 결정 뒤

## 단계 A 실행 (worker1)

- 패치 소스 `~/legacy/setup/NodeMemoryManager.java` (= `setup/patches/swap-keep-time.diff`: 59, kill 10 고정)
- `bash ~/legacy/setup/patch-nm-timing.sh ~/legacy/setup/NodeMemoryManager.java` → NM 재시작
- NM 재시작 후 **10분 대기**: 옛 NM(이전 포트)이 RM 목록에서 빠질 때까지 (`hadoop.sh status` 노드 1줄 확인)
- `nohup bash -c 'for i in 1 2 3 4; do bash ~/legacy/setup/fig6a.sh 0 > ~/hibench-logs/stepA-$i.out 2>&1; sleep 60; done; touch ~/hibench-logs/stepA.done' >/dev/null 2>&1 &`
- 누적이라 끝나도 jar 되돌리지 않음

## 진행 기록

| 단계 | 결정 | 실행 | 결과 문서 |
|---|---|---|---|
| A | 4회 (11-12) | 1회차 11:35 worker1 멈춤 (VM 안 원인 없음, 호스트 확인 요청) → 무효 | 패치 적용 확인: 마지막 OCM → 집합 제외 125·127·130초 (원 코드 약 18초), 라운드 2초 [실측, 1회차 PR] |
| A 재시도 | 1회 + `vmstat` 기록 (11-13) | 13:20~13:47 완료, 멈춤 없음 | [17-fig6a-A-r1/](17-fig6a-A-r1/) — kill 5, stop 전 PR shrink 0, 종료 963·1229·1644초. VM 여유 메모리 최저 0.2GB, swap 쓰기 최대 441MB/s [실측] |
| A r2~r4 | 3회 (11-13, Claude 실행) | 14:07~15:23 완료, 멈춤 없음 | [r2](17-fig6a-A-r2/)·[r3](17-fig6a-A-r3/)·[r4](17-fig6a-A-r4/) |
| B | Alg.1 kill 대기 제거, **1회만** (11-13, 아래 정정) — kill이 느는지 확인용 | 17:10~17:35 완료, 멈춤 없음 | [17-fig6a-B-r1/](17-fig6a-B-r1/) — kill 3 (전부 KM2, 155·726·916초), stop 전 PR shrink 0, 종료 PR 1009·KM1 541·KM2 1442초. "kill 중 대기" 0회. VM 여유 최저 0.7GB, swap 읽기·쓰기 최대 409·406MB/s [실측]. kill 증가 예상은 1회로는 안 보임 (A 2~5 범위 안) |
| B+E | Alg.1 전체 (대기 제거 + "꽉 참" = M), 먼저 1회 (VM 버티는지) | 17:53~18:13 완료, 멈춤 없음 | [17-fig6a-BE-r1/](17-fig6a-BE-r1/) — **kill 1** (KM2, 287초), KM2 재시작 287→약 600초 막힘 (KM1 종료 598초 뒤 시작), stop 전 PR shrink 0, PR 최대 9.5GB (세 job 중 가장 작음), 종료 PR 866·KM1 598·KM2 1119초. stop 판단 할당 최대 0.999 (설정 적용 확인). VM 여유 최저 0.2GB, swap 읽기·쓰기 최대 298·399MB/s [실측] |

| B+E r2~r4 | 3회 (11-13, Claude 실행) | 19:12~20:10 완료, 멈춤 없음 | [r2](17-fig6a-BE-r2/)·[r3](17-fig6a-BE-r3/)·[r4](17-fig6a-BE-r4/) |

| C (512MB) | 4회 (11-15, Claude 실행) | 13:47~15:15 완료, 멈춤 없음 | [r1](17-fig6a-C512-r1/)·[r2](17-fig6a-C512-r2/)·[r3](17-fig6a-C512-r3/)·[r4](17-fig6a-C512-r4/) (vmstat는 r1 폴더) |
| C (2GB 비교) | 4회 (11-15, Claude 실행), 옵션만 2048로 바꾸고 NM 재시작 | 15:24~16:45 완료, 멈춤 없음 | [r1](17-fig6a-C2G-r1/)·[r2](17-fig6a-C2G-r2/)·[r3](17-fig6a-C2G-r3/)·[r4](17-fig6a-C2G-r4/) (vmstat는 r1 폴더) |
| F | 제출 간격 15초 1회 (11-15, C 2GB 위) | 17:15~17:35 완료, 멈춤 없음 | [17-fig6a-F-r1/](17-fig6a-F-r1/) — kill 1 (KM2 298초), PR shrink 3 (첫 952초), 종료 PR 1018·KM1 643·KM2 1122초. **첫 kill 시각 변화 없음** (C 2GB 251~303초) [실측] |
| D | reclaim 대상 패치만 (11-16) | 17:44 NM 재시작, 실행 없음 | Fig 6(a)에선 reclaim 미작동 (위 "단계 D 확인") → 현재 VM jar = A+B+C+D, slack 2048, stop 1.0·reclaim 2.0 |
| F r2~r4 | 3회 추가 (11-16, 사용자 요청 — 4회로 맞춤). jar A+B+C+D (D는 Fig 6(a)에서 미작동, 3회 모두 "new reclaim" 0번) | 17:57~18:55 완료, 멈춤 없음 | [r2](17-fig6a-F-r2/)·[r3](17-fig6a-F-r3/)·[r4](17-fig6a-F-r4/) (vmstat는 r2 폴더) |

### 단계 B+E 4회 요약 [실측]

| | A (4회) | B+E (4회) | 논문 |
|---|---|---|---|
| kill | 2~5 | **1·2·2·1** (전부 KM2) | 1 |
| 첫 kill 초 | 177~203 | 279~296 | 약 600 |
| stop 전 PR shrink | 0·0·0·0 | 0·0·0·1 | 거의 없음 |
| PR 최대 크기 GB | 10.7~13.5 | 9.5~12.6 | 가장 큼 |
| 종료 PR 초 | 963~1142 | 864~1153 | 가장 오래 |
| 종료 KM1 / KM2 초 | 530~1229 / 1341~1644 | 554~680 / 964~1167 | 전체 약 1790 |

- 0.9 kill 0회 (꺼짐 확인). VM (r2~r4 `vmstat`): 여유 최저 0.2GB, swap 읽기·쓰기 최대 341·429MB/s, `st` 0

### 단계 C 4회 요약 — 512MB vs 2GB [실측]

- **결정 (사용자, 11-15): C 본 결과 = 2GB** (처음 512MB에서 변경, 이유는 아래). 이후 단계는 2GB 위에서 누적

| | B+E (4회) | C 512MB (4회) | C 2GB (4회) | 논문 |
|---|---|---|---|---|
| kill | 1·2·2·1 | 2·2·4·2 | 2·2·1·3 | 1 |
| 첫 kill 초 | 279~296 | 290~312 | 251~303 | 약 600 |
| PR shrink 횟수 (256MB 이상) | 4~7 (2~5) | 5~11 (5~7) | **1·2·5·2** (1·2·3·2) | 3 (그래프 읽기: 약 905·1000·1480초) |
| PR 첫 shrink 초 | 280~407 | 292~535 | **805·1011·901·1057** | 약 905 (본문 "880초") |
| PR 최대 크기 GB | 9.5~12.6 | 11.5~13.5 | 9.9~12.3 | 가장 큼 |
| 종료 PR 초 | 864~1153 | 1025~1071 | 1001~1057 | 가장 오래 |
| 종료 KM1 / KM2 초 | 554~680 / 964~1167 | 604~878 / 1045~1424 | 580~641 / 1082~1131 | 전체 약 1790 |

- kill은 전부 KM2. VM 여유 최저 0.2GB (둘 다), swap 읽기·쓰기 최대 512MB 302·434 / 2GB 323·388MB/s
- 2GB: PR 첫 shrink가 논문 시각(약 905초) 근처로 감. 단 r2·r4 첫 shrink는 PR 종료 시각과 같음 (끝날 때 줄인 것) → 실행 중 shrink는 r1 805·r3 901초
- 512MB: 여유분이 작아 사용량이 조금만 줄어도 다시 shrink (**추측**), 1MB 단위 연속 shrink도 보임
- 첫 kill·kill 수·PR 높이는 여유분과 무관하게 비슷
- 2GB가 논문에 가까운 이유 [실측 r1 PR 크기 변화]
  - 우리 puff 1회 크기 약 1.1~2.9GB. 512MB면 puff로 받은 여유가 2분 뒤 바로 shrink → 다시 OCM → puff 반복 (512 r1: 9135→8365→11130→9768→12690→11017MB, puff 2분 뒤마다 shrink)
  - 2GB면 puff 여유가 남고 사용량이 실제로 떨어질 때만 shrink (2GB r1: 7718MB 6분 유지 → 11158→10823MB 1번)
  - 논문 그래프도 puff 뒤 점선이 사용량보다 수 GB 위에 몇 분 유지되다가 사용량이 떨어진 뒤 shrink (그래프 읽기) → 2GB 쪽 동작과 같음
  - 논문은 2GB를 규모와 묶어 말하지 않음 ("2GB overhead by default" [p.264]) → 1/4로 줄일 근거 없음
  - 한계: 논문 규모에선 puff 1회가 2GB보다 훨씬 큼 → 2GB가 맞는 게 값 자체 때문인지 우리 puff 크기와 비슷해서인지는 구분 못 함 (**추측**)
- 집계: shrink = nm.log `update container memory`에서 줄어든 것만 셈

### 단계 D 확인 — Fig 6(a)에서 reclaim이 도는가 [실측, 11-15]

- 원 코드 `MemoryReclaim` (`NodeMemoryManager.java:404-480`): 할당 + 요청 < 노드 전체(28672MB)면 바로 return (`:410-412`). 넘을 때만 "new reclaim" 로그 후 ① suspend 컨테이너 균등 분할 ② 늦게 시작한 순
- B+E 4회·C 2GB 4회·F 1회 nm.log: "memory reclaim called" 7~9번, **"new reclaim" 0번** → 회수 한 번도 안 함
- 호출 때 할당 최대 24546MB + 요청 2048 < 28672 (KM2 재시작 포함). KM2 재시작이 막힌 건 RM 스케줄러 (노드 여유 없음), NM reclaim 아님 (**추측**)
- 결론: D를 바꿔도 Fig 6(a) 결과는 같음. 논문의 reclaim 실험은 Fig 6(b) (Kmeans FLEX + TPC-H REGULAR) [p.266]
- **처리 (사용자, 11-16): 패치만 + 문서, Fig 6(a) 재실행 없음**
  - 패치 `setup/patches/reclaim-lowest-first.diff` (A·B 위 누적): ① 균등 분할 → 늦게 시작한 순(EJF 최저 우선순위)부터 요청량 전체 회수
  - VM 적용 [실측]: jar에 비교자 클래스 추가(`NodeMemoryManager$4`), NM 11-16 17:44 재시작, slack 2048 유지. 동작 검증은 reclaim이 도는 실험(Fig 6(b)류)에서만 가능 → 미검증

### 단계 F 4회 요약 [실측]

| | C 2GB (4회) | F 15초 (4회) | 논문 |
|---|---|---|---|
| kill | 2·2·1·3 | 1·2·1·4 (전부 KM2) | 1 |
| 첫 kill 초 (전체 대비) | 251~303 (23~27%) | 281~303 (25~28%) | 약 600 (34%) |
| PR 실행 중 shrink | 2/4회 (805·901초) | 1/4회 (952초) | 3번, 첫 약 905초 |
| 종료 PR 초 | 1001~1057 | 904~1018 | 가장 오래 |
| 종료 KM1 / KM2 초 | 580~641 / 1082~1131 | 592~643 / 1064~1122 | 전체 약 1790 |

- 결론: 제출 간격 0→15초는 첫 kill·kill 수에 영향 없음. VM 여유 최저 0.2GB, swap 읽기·쓰기 최대 365·375MB/s

### 전체 시간 대비 비율로 비교 [실측, 11-15]

- 이유: 데이터 1/4이라 전체 시간이 약 1100초 (논문 약 1790초) → 절대 초 대신 "마지막 job 종료 = 100%"로 비교
- 집계 `norm.py` 방식: 첫 kill, PR 실행 중 첫 shrink (PR 종료 5초 전까지), PR 종료

| | A | B+E | C 512MB | C 2GB | F | 논문 |
|---|---|---|---|---|---|---|
| 첫 kill | 11~13% | 25~29% | 21~27% | 23~27% | 26% | 34% |
| PR 첫 shrink | 19~52% | 25~37% | 28~46% | 71·79% (2회는 실행 중 없음) | 83% | 51% |
| PR 종료 | 58~79% | 77~98% | 71~98% | 89~96% | 88% | 약 100% (PR이 마지막) |

- 단계가 쌓일수록 첫 kill·PR 종료가 논문 쪽으로 이동. 절대 초 차이(300 vs 600초)의 상당 부분은 전체 길이 차이
- PR 첫 shrink는 2GB에서 논문보다 늦어짐 (71~83% vs 51%)

## 단계 C 실행 — shrink 여유분 (worker1, 11-15)

- 결정 (사용자): **512MB 본 결과** (MIN_CONT·MAX_HEAP·노드처럼 1/4) + 시간 되면 **2GB 비교**
- 논문 [p.264]: 수요 60GB → 70GB로 puff된 컨테이너를 **62GB로 shrink** ("2GB overhead by default"). 감지 조건은 안 씀 → 원 코드 구조 그대로 숫자만 [우리]
- 패치 `setup/patches/slack-margin.diff` (`ContainerImpl.java`, A·B 위에 누적)
  - 감지 `:1204` 사용량×1.1 → 사용량 + 여유분, 목표 `:1217` 같은 식
  - 여유분 = NM 옵션 `-Dpufferfish.slack.mb` (yarn-env.sh `YARN_NODEMANAGER_OPTS`, 백업 `~/legacy/yarn-env.before-C.sh`) — 재컴파일 없이 512/2048 전환
- `patch-nm-timing.sh` 여러 파일 받게 수정, 컴파일 실패면 jar 안 건드리고 중단. 적용: `bash patch-nm-timing.sh ~/legacy/setup/B/NodeMemoryManager.java ~/legacy/setup/C/ContainerImpl.java`
- 확인 [실측]: jar에 `pufferfish.slack.mb`·`kill in progress`·`59`, NM 프로세스 `-Dpufferfish.slack.mb=512`
- 13:34 NM 재시작 → `stepC-run.sh` 4회 자동 (`stepC.status`, vmstat `vmstat-1115c.log`)
- B+E 4회 실측 참고: PR shrink 실행당 4~7번 (논문 그래프 3번 — 본문은 880초 1번만 서술). 원 코드 1.1배는 사용량이 조금 줄 때마다 다시 줄여 계단 모양 (**추측**)

- B+E 적용: 코드 변경 없음, yarn-site에 `yarn.nodemanager.balloon.stop` 0.8→**1.0** (puff 상한·kill 판단 = M), `balloon.reclaim` 0.9→**2.0** (OCM 무관 kill 끔 — Alg.1에 없음). 백업 `~/legacy/yarn-site.before-BE.xml`
- 위험 (**추측**): 할당 상한 22.4→28GB (VM RAM 32GB) → swap 증가, VM 멈춤 가능. 멈추면 설정 탓인지 기존 멈춤(11-12)인지 1회로는 구분 못 함

- B를 1회로 줄인 이유: Alg.1의 kill 조건(4~6행)과 puff 상한(18행)은 같은 M을 씀. puff는 (M−A)/2까지만 줘서 A가 M에 거의 안 닿음 → 논문은 kill이 드묾. 대기만 없애고 기준을 0.8로 두면 kill이 늘 수 있음(**추측**) → 1회로 확인 뒤 B+E로 묶음. 처음에 B·E를 나눈 건 11라운드 kill을 tolerance로 잘못 대응시켰기 때문

### 단계 A 4회 요약 [실측]

| | 14 (원 코드 4회) | A (4회) | 논문 |
|---|---|---|---|
| stop 전 PR shrink | 2·2·2·2 | **0·0·0·0** | 거의 없음 |
| kill | 3~7 | 2~5 (5·2·5·2) | 1 |
| PR 최대 크기 GB | 11.4~12.8 | 10.7~13.5 | 가장 큼 |
| 종료 PR 초 | 879~890 | 963~1142 | 가장 오래 |
| 종료 KM1 / KM2 초 | 729~1202 / 1250~1553 | 530~1229 / 1341~1644 | 전체 약 1790 |

- VM (r2~r4 `vmstat`): 여유 메모리 최저 0.2GB, swap 읽기·쓰기 최대 289·387MB/s, `st` 최대 1
- kill 8회(14·A) 모두 `memory conflicts kill` (`:289-301`), 0.9 kill(`:245`) 0회 [실측, nm.log]

## B 정정 (11-13) — suspension tolerance가 아니라 Alg.1 kill

처음 계획은 원 코드 11라운드 kill = suspension tolerance로 보고 "job 예상 기간의 절반"으로 바꾸려 했음. 논문 재확인 결과 틀림.

| 논문 [사실] | 근거 |
|---|---|
| Fig 6(a)는 **기본 EJF**로 실행 | p.266 "with default EJF container-1 is given the highest priority" |
| tolerance는 EJF+S·SJF의 선택 기능 | p.267 "EJF with suspension tolerance … EJF+S. … SJF is enabled with suspension tolerance by default" |
| 노드 꽉 참(A ≥ M) + 최우선 OCM → 최저 우선순위 kill, 그 라운드에 바로 | p.264 Alg.1 4~6행, p.263 |
| Fig 6(a) kill 원인 = container-1의 큰 수요 | p.266 "killed … because of the aggressive demand of container-1" |

- 원 코드 `:289-301`(최우선 app OCM → 최저 우선순위 kill)은 Alg.1 4~6행 구현 + 11라운드 대기 → B = **대기 제거**
- tolerance는 Fig 6(a)에 안 씀 → 구현 안 함
- "꽉 참" 기준(코드 0.8, 논문 M)과 0.9 kill은 E에서

## 단계 B 실행 (worker1, 11-13)

- 패치 `setup/patches/alg1-kill.diff` (A 위에 누적)
  1. `:299` `killRetries > 10` → `shouldKill` (Alg.1 4~6행)
  2. `killContainer()` [우리, 구현 세부]: 최저 우선순위 app에 kill 중(`KILLING`) FLEX가 있으면 그 라운드 건너뜀 — 대기를 없애서 같은 컨테이너를 2초 뒤 또 고르는 것 방지
- VM 소스: `~/legacy/setup/B/NodeMemoryManager.java` (A 소스는 `NodeMemoryManager-A.java`). 스크립트가 파일 이름 `NodeMemoryManager.java`만 받음
- 확인: jar 안 클래스에 `kill in progress` 문자열, `SWAP_KEEP_TIME` 59 [실측]
- 16:59 NM 재시작 → `~/hibench-logs/stepB-run.sh`가 이전 NM LOST 뒤 4회 자동 실행 (`stepB.status`, vmstat `vmstat-1113c.log`)
- 예상 (**추측**): 대기가 없어 kill이 A(2~5)보다 늘 수 있음. 논문 kill 1에 가까워지는 건 E("꽉 참" = M)까지 가야 할 수 있음
