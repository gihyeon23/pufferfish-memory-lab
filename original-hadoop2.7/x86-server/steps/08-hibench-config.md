# 08. HiBench 설정 — 실행 조건 · 데이터 1/4 규모 (2026-11-01)

> 표기: [논문 p.NN] 논문 명시 / [README] 원 저자 README / [우리] 논문·원 코드에 없어 우리가 정한 값 / **추측**
> 단일 노드(worker1). 설정 파일: [../../setup/hibench-conf/](../../setup/hibench-conf/)

## 1. 목적

- HiBench 6.0([07](07-hibench.md))으로 논문 §5.2 단일 노드 실험을 돌릴 실행 조건과 데이터 규모를 정함
- 원칙: 논문 "We follow the **default configuration of Spark and Hadoop, except we change the application heap size**" [p.265]
  → 논문에 있는 값만 지정, 나머지는 Spark·Hadoop 기본값

## 2. 설계 — 실행 조건 (`spark.conf`)

| 항목 | 값 | 근거 | HiBench 템플릿 |
|---|---|---|---|
| executor 수 | **1** | Table 1 Small = executor 1개, 단일 노드 실험은 Small [p.265] | 2 |
| executor 코어 | **1** | [우리] 논문에 없음 → "기본 설정" 문장에 따라 Spark on YARN 기본값 1 (**추측** 해석) | 4 |
| executor 메모리 | **1g** | MIN_CONT 4GB [p.265]의 1/4. MIN_CONT = `spark.executor.memory` [README 62-63행] | 4g |
| Flex | `spark.yarn.am.nodeLabelExpression flex` | [README], [06](06-spark-flex.md) | — |
| driver 메모리 | Spark 기본 (1g) | 기본 설정 원칙 → 템플릿 값 뺌 | 4g |
| `spark.default.parallelism`, `spark.sql.shuffle.partitions` | Spark 기본 | 기본 설정 원칙 → 템플릿의 덮어쓰기(= map.parallelism 8) 뺌 | 8 |
| master | `yarn-client` | 06과 같은 client 모드 | 같음 |

- Flex 컨테이너의 실제 힙은 NM이 `-Xmx16384m`(MAX_HEAP 16GB)으로 바꿈 — executor 메모리 1g는 **컨테이너 시작 크기**(1536MB = 1024 + 오버헤드 384)
- 코어 수가 결과에 주는 영향 (**추측**)
  - 코어 = 한 executor JVM 안에서 동시에 도는 task 수
  - 코어 ↑ → 실행 시간 ↓, 메모리 증가 속도 ↑(OCM·puff가 더 일찍·촘촘히), task별 작업 메모리 합 ↑
  - cache 데이터 크기와 Pufferfish 규칙(OCM 판정, ×1.4, ×1.1)은 그대로
  - Pufferfish와 baseline을 같은 설정으로 비교하면 상대 비교(Fig 7 정규화 makespan)는 유효
  - 1코어로 너무 오래 걸리면 다시 결정

## 3. 설계 — 데이터 규모 (`pufferfish.conf`, 프로파일 `pfq`)

| 워크로드 | 논문 Small [p.265] | HiBench 기본 프로파일과 비교 [사실] | `pfq` (1/4) | 논문에 없는 파라미터 (HiBench 기본값) |
|---|---|---|---|---|
| Spark-WC | 100GB | 없음 (huge 32GB, gigantic 320GB) | 25GB (`25000000000` 바이트) | — |
| Spark-KM | 1×10⁸ 샘플 | = huge | 2.5×10⁷ | 차원 20, 클러스터 5, k 10, 반복 5, 파일당 샘플 5×10⁶ |
| Spark-PR | 5×10⁶ 페이지 | = huge | 1.25×10⁶ | 반복 3, block_width 16 |
| Spark-NW | 1×10⁷ 엣지 | = large | 2.5×10⁶ | degree 3, max_out_edges 30, 파티션 8 |

- 1/4은 시작값 — [01](01-cluster-spec-and-scaling.md) §6.1 예비 실험으로 조정 가능
- **추측**: 논문 값 대부분이 HiBench 프로파일과 같음 → 논문도 HiBench 기본 파라미터를 썼을 가능성
- `hibench.default.map.parallelism` 8은 그대로 — Spark 실행이 아니라 **데이터 생성 MR 작업의 map/reduce 수**(`NUM_MAPS`·`NUM_REDS`)와 NW 앱 파티션 인자에 쓰임
  - 생성 파일 수가 Spark 입력 파티션 수에 영향을 줄 수 있음 (**추측**) — 생성 후 확인
- conf 로딩: `conf/*.conf`를 이름순으로 읽고 나중 값이 덮어씀, 변수는 다 읽은 뒤 치환 (`bin/functions/load_config.py:149-170`) → `pufferfish.conf`가 `hibench.conf` 뒤에 읽혀 `scale.profile`을 `pfq`로 바꿈

## 4. 실행 방법

```bash
# 맥 → VM
scp -r original-hadoop2.7/setup/hibench-conf original-hadoop2.7/setup/install-hibench.sh labvm:legacy/setup/
ssh labvm 'bash ~/legacy/setup/install-hibench.sh'      # 빌드돼 있으면 건너뛰고 conf만 복사
# 최종값 확인 (VM)
cd /opt/HiBench-6.0
python2 bin/functions/load_config.py conf conf/workloads/ml/kmeans.conf bin/workloads/ml/kmeans/spark
cat report/kmeans/spark/conf/kmeans.conf report/kmeans/spark/conf/sparkbench/spark.conf
```

- 추가 설치: `python-minimal`(Python 2.7.12) — HiBench 6.0 스크립트가 `#!/usr/bin/env python2`, VM엔 Python 3만 있었음

## 5. 검증 결과

- 4개 워크로드 최종값 확인 (`report/<워크로드>/spark/conf/`):
  - WC `DATASIZE=25000000000` / KM `NUM_OF_SAMPLES=25000000`, `SAMPLES_PER_INPUTFILE=5000000` / PR `PAGES=1250000`, `NUM_ITERATIONS=3` / NW `EDGES=2500000`, `NUM_PARTITION=8`
  - `YARN_NUM_EXECUTORS=1`, `YARN_EXECUTOR_CORES=1`, `SPARK_YARN_EXECUTOR_MEMORY=1g`
  - sparkbench용 `spark.conf`엔 `spark.executor.memory 1g`, `spark.yarn.am.nodeLabelExpression flex` 두 줄만 — parallelism·driver 메모리 덮어쓰기 없음
- 데이터 생성: 아직 (다음)

## 6. 랩미팅 보고 항목 (논문에 없어 우리가 정한 값)

| 항목 | 정한 값 | 근거 | 결과에 주는 영향 |
|---|---|---|---|
| HiBench 버전 | 6.0 | 원 저자 로그(2017-02) 시점 최신 ([07](07-hibench.md) §2) | 워크로드 구현 차이 (작음, **추측**) |
| executor 코어 | 1 | "Spark 기본 설정" 문장 → 기본값 1 | 실행 시간, OCM·puff 시점 (§2) |
| parallelism | Spark 기본 (HiBench 덮어쓰기 제거) | 같은 문장 | task당 데이터 크기 → task별 메모리 |
| driver 메모리 | Spark 기본 1g | 같은 문장 | 작음 (driver는 호스트에서 실행) |
| KM·PR·NW 세부 파라미터 | HiBench 기본값 | 논문 규모 값이 HiBench 프로파일과 같음 | — |
