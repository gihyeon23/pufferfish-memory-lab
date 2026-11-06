# x86-server — 논문·원 코드에 없어 우리가 찾거나 정한 것 (검토용, 2026-11-05)

> 범위: `original-hadoop2.7/x86-server`에서 실제 실행한 것만 (steps 01~12, `setup/`)
> 출처 표기: [논문 p.NN] / [원 코드] / [README] 원 저자 README / [우리] 우리가 정함 / **추측**
> 상태: ✅ 근거 있음 · ⚠️ 검토 필요(우리 실수 가능성 포함) · 🔧 고침

## 1. 하드웨어 · 규모 축소

| 항목 | 논문 / 원 코드 | 우리 | 근거 | 상태 |
|---|---|---|---|---|
| 노드 RAM | 128GB, YARN 120GB [p.265] | 32GB, YARN 28GB | 1/4 = 30GB에서 OS·데몬 여유 4GB [우리] (01 §3) | ✅ 결정 기록됨, 여유 4GB가 실제 필요한지는 미확인 |
| MAX_HEAP | 64GB [p.265], 65536 [원 코드] | 16GB | 1/4 [우리] | ✅ |
| MIN_CONT | 4GB [p.265], "컨테이너 물리 메모리 제한(e.g., 4GB)" [p.261] | `spark.executor.memory=1g` → **실제 컨테이너 1536MB → 11/06부터 2048MB** (최소 할당 1024) | 1/4 = 1GB [우리], README "MIN_CONT = spark.executor.memory" | ⚠️ 논문 그래프 시작 약 5GB = 노드 4.2%, 우리 2048MB = 7.1% (1024 단위 올림) |
| CPU | 16코어/32스레드 [p.265] | 8 vCPU | VM 사양 | ✅ |
| swap 크기 | 논문에 없음 | 32GB swapfile | RAM과 같게 [우리] (04) | ✅ |
| `vm.swappiness` | 논문에 없음 | 60 (Ubuntu 기본) | 그대로 둠 (04) | ✅ |
| swap 장치 | 데이터 디스크 HDD RAID-5 [p.265], **swap은 SSD** ("SSD-backed swap partition") [p.268] | VM 디스크 위 파일, 종류 미확인 | — | 🔧 01 §7·04 §5 정정 (11/06). 교수님께 보낸 10/26 메일에도 "논문은 HDD 환경"이라고 적었음 |

## 2. Pufferfish 설정 (원 코드 기본값 vs 우리)

| 항목 | 논문 / 원 코드 | 우리 | 근거 | 상태 |
|---|---|---|---|---|
| `balloon.stop` | 논문 수치 없음, 원 코드 0.8, README 예시 0.9 | 0.8 | 원 코드 기본값 [우리 선택] (01 §4) | ✅ (README 0.9와 다름은 기록됨) |
| `balloon.ratio`·`reclaim` | 0.4 [p.263]·원 코드 0.9 | 그대로 | — | ✅ |
| puff 주기 | 2초 [p.263]. 원 코드 Java 상수 2000, 그러나 `yarn-default.xml` 3000이 적용 → 실제 3초 | 11/04부터 **설정으로 2초** | 논문 명시 + 저자 커밋 `35f1b1a`의 의도 (11) | ✅ 09·10은 3초로 실행됨 |
| shrink 대기 | e.g. 2분 [p.264] / 원 코드 5 (실제 6라운드) | 원 코드 그대로 | 재현 원칙: 코드 수정 안 함 (11 §3) | ✅ 11은 코드 수정한 보조 결과 |
| shrink 여유 | +2GB [p.264] / 원 코드 ×1.1 | 원 코드 그대로 | (06 §7) | ✅ |

## 3. task 이미지 · 컨테이너 환경

| 항목 | 논문 / 원 코드 | 우리 | 근거 | 상태 |
|---|---|---|---|---|
| 이미지 태그 | 논문은 `sequenceiq/hadoop-docker`만 [p.265] | `2.4.0` | README "tested 2.4.0", `YarnConfiguration.java:1009` | ✅ |
| 안쪽 Hadoop | 이미지 원본 2.4.0 | 11/05까지 **2.7.3으로 교체**해 씀 → 🔧 2.4.0으로 되돌림 | 맥(ARM) 결정을 x86에서 다시 검토 안 함 (03 §7) | 🔧 06~12는 2.7.3 조건 |
| 이미지 안 설정 파일 | — | 우리 클러스터 설정(core/yarn-site 등)을 이미지에 COPY | HDFS 주소 등이 필요 | ✅ 설정만 |
| `env-whitelist` | Hadoop 기본값 | 11/05까지 `JAVA_HOME` 뺀 값 → 🔧 기본값으로 | DCE가 이미 `JAVA_HOME`·`HADOOP_*`를 실행 스크립트에서 뺌 (`DockerContainerExecutor.java:315-320`) | 🔧 03 §7 설명 정정 (원래 불필요) |

## 4. Hadoop/YARN 설정 — 맥 VM에서 그대로 넘어온 값

| 설정 | Hadoop 기본 | 우리 | 근거 | 상태 |
|---|---|---|---|---|
| `yarn.scheduler.minimum-allocation-mb` | **1024** | **256** | 05에 "그대로, 논문에 값 없음"이라고만 적음 — 맥 VM(3GB) 값이 남은 것 | 🔧 11/06 기본값 1024로 (§9). 이유: 컨테이너 크기 올림 단위가 바뀜: 기본이면 executor 1g → 2048MB, 우리는 1536MB. 시작 크기·RM 배정에 영향 |
| `yarn.scheduler.maximum-allocation-mb` | 8192 | 28672 | 예비 실험(16GB 힙) 대비 [우리] (05) | ✅ (Flex는 1.5GB 요청이라 실험엔 영향 작음, **추측**) |
| `yarn.nodemanager.vmem-check-enabled` | true | false | 기록 없음 | ✅ 유지, 이유를 yarn-site 주석에 기록 (11/06). 켜면 Flex(-Xmx16g) 컨테이너가 가상 메모리 초과로 죽을 수 있음 (**추측**) |
| `mapred-site` 메모리 (AM·map·reduce 512MB, -Xmx384m) | 1024 등 | 512 | 맥 VM 값 | 🔧 11/06 기본값으로. MR만 해당 (pi, HiBench 데이터 생성). Fig 6(a) Spark엔 영향 없음 |
| `dfs.replication` | 3 | 1 | 단일 노드 | ✅ (01 §5의 "2"는 3대 구성 계획) |

## 5. 워크로드 (HiBench · Spark)

| 항목 | 논문 / 원 코드 | 우리 | 근거 | 상태 |
|---|---|---|---|---|
| HiBench 버전 | 없음 | 6.0 | 원 저자 로그(2017-02) 시점 최신 **추측** (07) | ✅ 저자 문의 후보 |
| HiBench 빌드 대상 Spark | — | 2.0.0 (`-Dspark=2.0`)로 빌드, 실행은 2.0.1 | HiBench 6.0 pom | ✅ 차이 작음 (**추측**) |
| Spark 패키지 | Spark 2.0.1 [p.265] | `spark-2.0.1-bin-hadoop2.7` | 호스트 Hadoop 2.7.3에 맞춤 [우리] | ✅ |
| 실행 모드 | 없음 | `yarn-client` (driver는 호스트 JDK 8) | HiBench 기본 (08) | ✅ |
| executor 수 | Table 1 Small = 1 [p.265] | 1 | — | ✅ |
| executor 코어 | 없음 | **1** | "Spark·Hadoop 기본 설정" 문장 [p.265] 해석 [우리] (08) | ✅ 랩미팅 보고 항목 |
| driver 메모리·parallelism | 없음 | Spark 기본 (HiBench 덮어쓰기 제거) | 같은 문장 (08) | ✅ |
| 입력 크기 | Table 1 Small [p.265] | 1/4 (`pfq`), 10에서만 PR 2배 | 노드 1/4에 맞춤 [우리] | ✅ 11/04부터 다시 Table 1 비율 |
| KM·PR 세부 파라미터 | 없음 | HiBench 기본 (KM k 10·반복 5, PR 반복 3) | 논문 규모 값이 HiBench 프로파일과 같음 **추측** (08) | ✅ |
| 실행 클래스·옵션 | — | `fig6a.sh`가 HiBench `run-spark-job`과 같은 클래스·옵션으로 직접 제출 | HiBench 6.0 `run.sh` 대조 (11/05) | ✅ |

## 6. Fig 6(a) 실행 절차 · 그래프

| 항목 | 논문 | 우리 | 근거 | 상태 |
|---|---|---|---|---|
| 제출 순서 | PR → KM1 → KM2 "one by one" [p.265] | 같음 | — | ✅ |
| 제출 간격 | 6(a)엔 없음. Fig 7은 120초 [p.266] | 09~12: 120초 → 13·14: **0초**(앞 job 앱 ID 받은 직후) | 논문 그래프상 셋 다 0초 근처 시작 (10 §6) | 🔧 120초는 다른 그림 값 → 0초로 |
| 실행 횟수 | 6(a) 1회로 보임, Fig 7은 5회 [p.266] | 대부분 1회, 14 조건만 4회 | — | ⚠️ 14 조건 4회: kill 3~7로 편차 큼 (13 §반복) |
| 메모리 값 | "real memory usage" | cgroup `memory.usage_in_bytes` (2초 간격) | 원 코드도 같은 파일로 판단 (`ContainerImpl.java:1125`) | ✅ (page cache 포함 값) |
| 세로축 | 노드 120GB | 28GB, 오른쪽 축에 ×120/28 환산 | 그래프 비교용 [우리] | ✅ |
| shrink 표시 | "shrinked" 1곳 | slacking 뒤 1GB 이상 감소, 종료 ±15초 제외 | 표시 기준 [우리] (`plot-fig6a.py`) | ✅ 표시용 |

## 7. 해석 · 추측 중 틀렸거나 고친 것

| 내용 | 처음 | 바로잡음 |
|---|---|---|
| puff 간격 4~5초의 이유 (06 §7) | "OCM 판정 후 다음 heartbeat라 두 주기" **추측** | 🔧 실제 라운드 3초(`yarn-default.xml`) — 06 정정 (11/06) |
| shrink 대기 (06 §7·§8) | "5라운드(약 15초)" | 🔧 카운터가 0 미만일 때 빠져서 실제 **6라운드** (11) — 06 정정 (11/06) |
| shrink와 "2분" 관계 (06 §7) | 별개 동작 **추측** | 🔧 2026-11-02 정정 |
| backoff | 논문과 다름 | 🔧 논문 본문 p.265와 일치 (06 §8) |
| KM 비중 | "KM 23%, KM heavy" | 🔧 철회 (27GB는 억눌린 크기) |
| 논문 swap 장치 | HDD RAID-5 | 🔧 swap은 SSD [p.268] — 01·04 정정 (11/06) |
| env-whitelist 필요성 | JDK 맞추려면 필요 | 🔧 DCE가 이미 제외 → 불필요 — 03 정정 (11/06) |

## 8. 아직 확인 못 한 것

- VM 디스크 HDD/SSD 여부 (교수님 답 없음)
- `kill` 뒤 약 10초 만의 재시작 원인 (RM의 "실제 여유 ≥ 요청×2" 조건 **추측**, 10 §5)
- 원 저자 실험 때 `yarn-site.xml` (주기 2초를 따로 넣었는지)
- 같은 조건 반복 시 결과 차이

## 9. 맥(ARM) 환경에서 넘어온 것 (2026-11-06 점검)

### 실험 결과에 영향 가능

| 항목 | 지금 값 | 맥에서 정한 이유 | x86에서 | 제안 |
|---|---|---|---|---|
| `minimum-allocation-mb` | ~~256~~ → 기본 1024 | 맥 VM 3GB라 작게 | executor 1g 컨테이너 1536 → **2048MB** [실측] | 🔧 11/06 기본값 |
| `mapred-site` 메모리 | ~~512MB, -Xmx384m~~ → 기본 | 맥 VM 3GB | MR만 (pi·데이터 생성) | 🔧 11/06 기본값 |
| `vmem-check-enabled` | false | 기록 없음 | Flex `-Xmx16g`면 가상 메모리 검사에 걸릴 수 있음 (**추측**) | 유지, 이유(**추측**)를 yarn-site 주석에 기록 |
| 호스트 JDK (NM·RM) | OpenJDK 8u292 | 맥 빌드·실행 환경이 JDK 8 | 원 저자 호스트 JDK는 논문·README에 없음 | 그대로 + [우리]로 기록 |
| YARN jar 13개 | 맥 ARM VM에서 OpenJDK 8로 빌드 (Java 7 클래스) | 원 저자는 jar를 공개 안 함 | 바이트코드라 x86에서도 같음 | 🔧 `install-host.sh` 문구 고침 (옛 step 문서는 그대로) |

### 실험 영향 없음 — 🔧 11/06 정리

- 🔧 이미지 이름 → `local/hadoop-docker:2.4.0-sequenceiq`, sequenceiq 빌드는 2.7.3 tar 안 만듦
- 🔧 `install-host.sh` 안내를 x86·맥 따로
- 🔧 VM: 옛 이미지 태그·이름 없는 이미지·`dl/centos7` 삭제 (백업 `inner273-backup`·`nm-jar-orig`는 유지)
- 맥 전용 파일(`prepare-base-image.sh`·`Dockerfile.jdk7/8`·arm64 분기)은 arm-mac 기록용으로 남김

정리 전 목록:

- `install-host.sh` 마지막 안내가 "prepare-base-image → build-image **jdk7**" — x86 순서와 다름
- `prepare-base-image.sh`·`Dockerfile.jdk7`·`Dockerfile.jdk8`·arm64 분기 — 맥 전용
- `conf/yarn-site.xml` image-name 기본값 `2.7.3-jdk7`, 맥 VM 주석 (빌드 때 덮어써짐)
- 이미지 이름 `local/hadoop-docker:2.7.3-sequenceiq` — 안쪽이 이제 2.4.0이라 이름이 틀림
- VM 남은 파일: `~/legacy/dl/centos7`(jdk7 이미지용, 21MB), 이름 없는 옛 이미지 2개(각 1.2GB), `inner273-backup` 이미지, `nm-jar-orig`, `yarn-site.before-1105.xml`
