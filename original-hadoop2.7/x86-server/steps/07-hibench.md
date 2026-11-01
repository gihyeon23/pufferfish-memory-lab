# 07. HiBench 설치 (2026-11-01)

> 표기: [사실] 논문·원 코드·로그 확인 / **추측**
> 단일 노드(worker1)에서 진행. 3대 구성은 VM 추가 할당 대기 중

## 1. 목적

- 논문 워크로드(Spark-WC·KM·PR·NW, "from HiBench [22]" [p.265])를 돌릴 HiBench 준비
- 다음 단계: 데이터 1/4 생성 → [01](01-cluster-spec-and-scaling.md) §6.1 입력 규모 예비 실험 → §5.2 Fig 6(a) 재현

## 2. 버전 근거 — 논문·원 코드에 HiBench 버전 없음

| 출처 | HiBench 버전 | 관련 단서 |
|---|---|---|
| 논문 | **없음** — 참고문헌 [22]는 2010년 HiBench 원 논문 (ICDEW) | Spark 2.0.1, Docker 1.12.1, `sequenceiq/hadoop-docker` 명시 [p.265] |
| 원 저자 README | **없음** | Hadoop 2.7.3 기반, protoc 2.5.0 |
| 원 저자 저장소 `Memory-monirot/kmeans-{large,huge}.log` | **없음** (NodeManager 로그만, 앱 정보 없음) | 로그 날짜 **2017-02-06** |
| HiBench GitHub 태그 (커밋 날짜) | 5.0: 2015-11-01 / 6.0: 2016-11-21 / 7.0: 2017-11-08 | 6.0·7.0 모두 `-Psparkbench -Dspark=2.0` 지원 (`spark.version` 2.0.0) |

- **추측**: 원 저자 KMeans 로그(2017-02) 시점엔 7.0이 없었음 → 그때 HiBench를 썼다면 6.0
- **추측**: 그 로그가 논문 실험인지는 알 수 없음 (논문은 2019-11) → 이후 실험에 7.0을 썼을 가능성도 있음
- 저자 문의 메일 질문 후보: HiBench 버전

## 3. 결정 — HiBench 6.0 (2026-11-01)

- 원 저자 로그(2017-02) 시점 최신 버전인 6.0으로 결정 (§2 추측 근거, 사용자 결정)
- 처음엔 7.0으로 빌드했다가(§5) 버전 근거 확인 후 6.0으로 바꿈

## 4. 설치 ([../../setup/install-hibench.sh](../../setup/install-hibench.sh))

- Maven: `apt-get install maven` → 3.3.9 (Ubuntu 16.04 패키지)
- 소스: GitHub 태그 아카이브 `HiBench-6.0.tar.gz` (공식 체크섬 없음)
  - sha256 `179f5415903f4029bd0ea1101a3d4c67faf88ca46a993d8179582299ad730f79` (2026-11-01 받은 파일)
- 빌드: `mvn -Psparkbench -Dspark=2.0 clean package -DskipTests` → `/opt/HiBench-6.0`
  - 6.0은 `-Dspark=2.0`이면 Scala 2.11.8 자동 (`-Dscala` 옵션 없음, `sparkbench/pom.xml` `spark2.0` 프로파일)

```bash
scp original-hadoop2.7/setup/install-hibench.sh labvm:legacy/setup/
ssh labvm 'bash ~/legacy/setup/install-hibench.sh'
```

## 5. 검증 결과

- 6.0 빌드 성공 (exit 0). 산출물:
  - `autogen/target/autogen-6.0-jar-with-dependencies.jar` (데이터 생성)
  - `sparkbench/assembly/target/sparkbench-assembly-6.0-dist.jar` (90MB)
- 의존성: `spark-core_2.11` 2.0.0, `spark-mllib_2.11` (`~/.m2`)
- 논문 워크로드 4개 모두 있음: WC `micro/wordcount`, KM `ml/kmeans`, PR `websearch/pagerank`, NW `graph/nweight` (`conf/workloads/`)
- Maven 경고 `Invalid cookie header` 다수 — 쿠키 만료 형식 경고일 뿐 빌드에 영향 없음
- 7.0 빌드본(sha256 `89b01f3a…e847`)도 빌드는 성공했으나 6.0 결정 후 VM에서 삭제 (`/opt/HiBench-7.0`, 아카이브)
- 미완: `conf/hadoop.conf`·`spark.conf` 설정, 데이터 1/4 생성
