# Step 3 — YARN 기동, worker 2대 인식

> 로드맵: [2026-10-05.md](2026-10-05.md) §3 Step 3 / 이전 단계: [02-step2-hdfs.md](02-step2-hdfs.md)
>
> ✅ **완료 (2026-10-06)** — 확인 포인트 4개 모두 통과

## 목적

**한 줄 요약: 기본 YARN(Pufferfish 없음)이 클러스터에서 job을 실제로 스케줄링·실행하는지 확인한다.**

### 왜 하는가

- YARN = 논문 실험의 **자원 관리자**. job을 받아 worker에 컨테이너(메모리·CPU가 고정된 JVM)를 띄운다
- Pufferfish는 YARN **위에** 붙는 메모리 관리 기능이다. 논문 비교 구도 = **YARN만(baseline) vs YARN + Pufferfish**
- 1~10차는 controller가 Docker로 YARN 역할을 **흉내** 냈다 → 이제 진짜 YARN으로 바꾸는 첫 단계
- worker 2대가 살아 있는지는 이미 Step 1(SSH)·Step 2(DataNode 2대)에서 확인함.
  Step 3은 그 위에서 **"job → 컨테이너 할당 → 실행 → 완료"** 스케줄링 경로를 확인하는 단계

### 뒤 단계가 이 단계에 기대는 것

| 단계 | YARN이 필요한 이유 |
|---|---|
| Step 4 | Spark를 `--master yarn`으로 실행 |
| Step 5~6 | HiBench Kmeans가 YARN 컨테이너 안에서 실행 |
| Step 7 | **baseline = YARN 기본 동작** (자원이 남아도 job이 대기) — 논문이 문제 삼는 지점 |
| Step 8 | controller가 YARN 컨테이너 cgroup을 감시·조절 (Pufferfish 적용) |

### 이 단계에서 일부러 하지 않는 것

- cgroup 제어(Step 8), Spark(Step 4), Pufferfish 연결(Step 8)
- 이유: 기본 YARN만 먼저 통과시켜 두면 뒤에서 문제가 생겼을 때 원인을 좁히기 쉽다.
  cgroup 설정에서 오래 막혀도 Step 7 baseline은 확보할 수 있다

### 참고 — YARN은 따로 설치하지 않는다

- Step 2에서 설치한 Hadoop 3.5.0 배포판에 HDFS·MapReduce와 함께 포함돼 있음
  (`$HADOOP_HOME/sbin/start-yarn.sh`, `$HADOOP_HOME/bin/yarn`). 이 단계는 **설정 + 기동**만 한다

### `pi` 예제란

- Hadoop 배포판에 기본 포함된 MapReduce 예제 (`share/hadoop/mapreduce/hadoop-mapreduce-examples-3.5.0.jar`)
- **원주율 π를 확률로 추정** — 준몬테카를로(Quasi-Monte Carlo) 방식, 그래서 앱 이름이 `QuasiMonteCarlo`
  1. 한 변이 1인 정사각형 안에 점을 고르게 찍는다
  2. 내접원 안에 들어간 점의 비율 ≈ π/4
  3. 비율 × 4 = π 추정값
- `pi 2 10` = map 2개 × 점 10개(합계 20개) + reduce 1개가 합산 → 점이 적어 값이 거칠다(3.8)
- 쓰는 이유: 계산은 가볍지만 **YARN 전체 경로**를 다 거친다
  (AM 컨테이너 할당 → map 컨테이너 → reduce 컨테이너 → HDFS 읽기·쓰기) → YARN 동작 확인의 표준 테스트

## 설계

| 항목 | 값 | 이유 |
|---|---|---|
| RM 위치 | `yarn.resourcemanager.hostname=pf-control` | 로드맵 확정 사항 |
| NM 목록 | 기존 `workers` 파일 재사용 (`pf-worker1`, `pf-worker2`) | `start-yarn.sh`도 같은 파일을 읽음 |
| Container executor | `DefaultContainerExecutor` (명시) | cgroup은 아직 끔 — 변수 최소화. Step 8에서 LCE + cgroup v2로 교체 |
| NM 메모리 | `resource.memory-mb=2048` | worker available ≈ 2830 MB (Step 2 측정) − NM JVM 몫 |
| NM vCPU | `resource.cpu-vcores=3` | VM vCPU 수와 동일 |
| 할당 단위 | min 256 MB / max 2048 MB | 작은 컨테이너도 받을 수 있게 |
| vmem 검사 | `vmem-check-enabled=false` | JDK 17 JVM의 큰 가상 메모리 때문에 작은 컨테이너가 죽는 문제 회피. pmem 검사는 유지 |
| NM 작업 경로 | `~/hadoop-data/{nm-local,nm-logs}` | Step 2와 같은 규칙 (`/tmp` 회피) |
| MR 컨테이너 | AM·map·reduce 모두 512 MB, `-Xmx400m` | 기본값(AM 1536 MB)은 NM 2048 MB에 비해 큼 |
| `HADOOP_MAPRED_HOME` | `/opt/hadoop` (AM·map·reduce env) | Hadoop 3.x에서 빠지면 `MRAppMaster` 클래스를 못 찾음 |

### worker 1대 메모리 예산 (추정)

| 항목 | MB |
|---|---:|
| VM RAM | 3584 (OS 인식 3396) |
| HDFS 기동 후 used | ~566 |
| NodeManager JVM | ~300 (추정) → **실측 RSS 274** |
| **컨테이너용 선언** | **2048** |
| 남는 여유 | ~480 |

- `pi 2 10` 기준: AM 512 + map 512 × 2 = 1536 MB → 한 worker에 다 들어가도 2048 이하
- 추정치는 기동 후 `free -m`·`ps`로 실측해서 아래 검증 결과에 채운다

설정 원본: [experiments/configs/hadoop/](../../../experiments/configs/hadoop/)
(`yarn-site.xml`, `mapred-site.xml` 추가. Step 2의 `core-site.xml`·`hdfs-site.xml`·`workers`는 그대로)

## 실행 방법

```bash
# 0) VM 3대 기동 후 HDFS 먼저 (pf-control)
start-dfs.sh
hdfs dfsadmin -report | grep "Live datanodes"     # (2)

# 1) 설정 배포 (맥, 저장소 루트에서)
for h in pf-control pf-worker1 pf-worker2; do
  scp experiments/configs/hadoop/{yarn-site.xml,mapred-site.xml} $h:/opt/hadoop/etc/hadoop/
done

# 2) NM 작업 경로 (worker 2대)
mkdir -p ~/hadoop-data/{nm-local,nm-logs}

# 3) YARN 기동 (pf-control)
start-yarn.sh
jps                                                # control: ResourceManager 추가
ssh pf-worker1 jps; ssh pf-worker2 jps             # NodeManager 추가

# 4) 노드 인식 확인
yarn node -list                                    # Total Nodes:2, 둘 다 RUNNING

# 5) pi 예제 (HDFS 사용자 디렉터리 먼저)
hdfs dfs -mkdir -p /user/gihyeon
yarn jar $HADOOP_HOME/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.5.0.jar pi 2 10
yarn application -list -appStates FINISHED         # FinalStatus = SUCCEEDED

# 6) 메모리 재측정 (3대)
free -m
ps -o rss,cmd -C java | awk '{print $1/1024 " MB", $NF}'
```

- 정지 순서: `stop-yarn.sh` → `stop-dfs.sh` (pf-control) → VM 종료
- (선택) RM 웹 UI를 맥에서 보려면 포트포워딩 추가:
  ```bash
  VBoxManage natnetwork modify --netname pfnet \
    --port-forward-4 "rm-web:tcp:[127.0.0.1]:8088:[10.10.0.11]:8088"
  # → 맥 브라우저 http://127.0.0.1:8088
  ```

## 확인 포인트

아래 4가지를 **모두** 통과해야 Step 3 완료.

| # | 확인 항목 | 방법 | 기대 결과 | 의미 |
|---|---|---|---|---|
| 1 | 데몬 기동 | `jps` (3대) | control: NameNode + SecondaryNameNode + **ResourceManager**<br>worker: DataNode + **NodeManager** | 프로세스가 떴는지 |
| 2 | 노드 인식 | `yarn node -list`<br>`yarn node -status <NodeId>` | RUNNING **2대**, 각 `Memory-Capacity 2048MB / vCores 3` | RM이 worker와 그 자원을 알고 있는지 |
| 3 | job 실행 | `pi 2 10` 예제<br>`yarn application -list -appStates FINISHED` | `Estimated value of Pi is ...` 출력 + FinalStatus **SUCCEEDED**<br>(샘플이 2×10개뿐이라 값 자체는 3.14에서 멀어도 정상) | 컨테이너 할당 → 실행 → 완료가 실제로 되는지 |
| 4 | 메모리 여유 | `free -m`, `ps` (3대) | control available **300 MB 이상** (Step 2: 812 MB) | RM까지 올린 control이 버티는지 |

- 4번에서 300 MB 아래로 떨어지면 control RAM 2048 MB 상향 또는 SecondaryNameNode 중지 검토
  (Step 2 메모 이어서)

### 막히기 쉬운 지점

| 증상 | 원인 후보 | 확인/조치 |
|---|---|---|
| `yarn node -list`에 0대 | NM이 RM 주소를 못 찾음 | worker의 `yarn-site.xml` 배포 여부, NM 로그 `$HADOOP_HOME/logs/*nodemanager*.log` |
| NM이 뜨자마자 종료 | `JAVA_HOME` 미설정 | `hadoop-env.sh`에 이미 있으면 OK. 없으면 `yarn-env.sh`에도 추가 |
| `Could not find or load main class ...MRAppMaster` | `HADOOP_MAPRED_HOME` 누락 | `mapred-site.xml` 배포 여부 |
| job이 ACCEPTED에서 멈춤 | AM 크기 > NM 자원 | RM UI 또는 `yarn node -status`로 가용 메모리 확인 |
| `running beyond physical memory limits` | `-Xmx`가 컨테이너 크기에 비해 큼 | `-Xmx`를 컨테이너의 ~80%로 유지 |

## 검증 결과

2026-10-06 실행. 설정은 초안 그대로 수정 없이 통과.

| # | 확인 항목 | 결과 | 통과 |
|---|---|---|---|
| 1 | 데몬 기동 (`jps`) | control: NameNode, SecondaryNameNode, **ResourceManager**<br>worker1·2: DataNode, **NodeManager** | ✅ |
| 2 | 노드 인식 (`yarn node -list`) | `Total Nodes:2` — pf-worker1·pf-worker2 **RUNNING**, 둘 다 `2048MB / 3 vcores` | ✅ |
| 3 | job 실행 (`pi 2 10`) | `application_1791262326901_0001` **FINISHED / SUCCEEDED**, 12.3초, `Estimated value of Pi is 3.8` | ✅ |
| 4 | 메모리 여유 (control available) | **609 MB** (Step 2: 812 MB → RM 기동으로 −203 MB) | ✅ |

### `pi 2 10` 5회 반복 (2026-10-06)

- 목적: "한 번 우연히 된 것이 아님"을 확인 (안정성). **성능 지표가 아님**
- 측정값: 클라이언트 출력 `Job Finished in N seconds` (제출 ~ 완료)
- 위 검증 결과 표의 첫 실행(`_0001`, 12.315초)은 별도 — 아래 5회는 `_0002`~`_0006`

| 회차 | application | Final-State | 시간 (초) | π 추정값 |
|---:|---|---|---:|---:|
| 1 | `_0002` | SUCCEEDED | 11.130 | 3.8 |
| 2 | `_0003` | SUCCEEDED | 13.117 | 3.8 |
| 3 | `_0004` | SUCCEEDED | 13.081 | 3.8 |
| 4 | `_0005` | SUCCEEDED | 14.867 | 3.8 |
| 5 | `_0006` | SUCCEEDED | 12.809 | 3.8 |

| 성공률 | 중앙값 | 평균 ± 표준편차 | 최소 / 최대 |
|---|---:|---:|---:|
| **5/5** | **13.081 초** | 13.001 ± 1.327 초 | 11.130 / 14.867 초 |

- 최빈값은 생략: 시간은 연속값이라 같은 값이 반복되지 않음 → 대표값은 **중앙값**을 쓴다
- π 값이 매번 3.8로 같은 이유: 준몬테카를로는 무작위가 아니라 **정해진 수열(Halton)**로 점을 찍어서
  입력이 같으면 결과도 같다 → 결과값이 아니라 **시간과 성공 여부**만 비교 대상
- 편차(최대−최소 ≈ 3.7초)는 job이 10여 초로 짧아 컨테이너 기동 시간 차이가 그대로 드러난 것으로 보임 **[추측]**.
  Step 6 이후 실측 실험은 조건당 최소 5회 반복 + 중앙값 기준으로 한다

### 메모리 (YARN 기동 직후)

| 노드 | used | available | Java 프로세스 RSS |
|---|---:|---:|---|
| pf-control (1450 MB) | 840 MB | 609 MB | NameNode 219 MB, SecondaryNameNode 154 MB, **ResourceManager 264 MB** |
| pf-worker1 (3396 MB) | 756 MB | 2639 MB | DataNode 188 MB, **NodeManager 274 MB** |
| pf-worker2 (3396 MB) | 773 MB | 2623 MB | DataNode 192 MB, **NodeManager 274 MB** |

- 측정 시점: pi job 종료 직후 (컨테이너 없음), VM swap 사용 0
- worker 여유 2623~2639 MB > NM 선언 2048 MB → 컨테이너를 꽉 채워도 약 600 MB 남음.
  worker 2대 상태는 거의 동일 (비교 조건 유지)
- control 609 MB → 지금은 RAM 상향 불필요. Step 4 이후 Spark history server 등을 올리면 재측정

### 진행 중 관찰

- **VM 기동 실패 1회**: 3대를 연달아 `startvm --type headless` 하던 중 pf-worker2가
  `The VM session was aborted`로 실패 → 단독 재시도에서 정상 기동.
  VBox.log가 시작 직후에서 끊겨 원인은 특정 못 함. **[추측]** 호스트 메모리 압박 또는 연속 기동 경합.
  다음부터는 한 대씩 몇 초 간격으로 띄운다
- **호스트(macOS) swap**: VM 기동 전 3.70 GB/4 GB → YARN 기동 후 **5.78 GB/6 GB** 사용
  (macOS가 swap 파일을 늘림), memory free 36%. Step 0의 R3(호스트 메모리)가 여전히 유효 —
  Step 6 이후 측정 전에 맥의 다른 앱을 정리하고 `sysctl vm.swapusage`를 같이 기록할 것
- pi job의 Tracking URL이 `pf-worker2:19888`(JobHistory Server)을 가리키지만 JHS는 띄우지 않았음.
  job 성공에는 영향 없음. 필요해지면 `mapred --daemon start historyserver`
