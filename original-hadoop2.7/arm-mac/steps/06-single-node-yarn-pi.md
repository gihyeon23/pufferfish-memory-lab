# Legacy 5 — 원 구현 단일 노드 기동 + pi 예제

> 랩미팅: 2026-10-26 / 이전: [05-hadoop-dist-task-image.md](05-hadoop-dist-task-image.md)
>
> 표기: **[사실]** 실측·원 코드 확인 / **[추측]** 내 해석

## 목적

**한 줄 요약: 원 구현(YARN 2.7.3 + Pufferfish)을 VM 한 대에서 띄우고, task가 DockerContainerExecutor(DCE)로 Docker 컨테이너에서 도는지 pi로 확인한다.**

- **정식 결과는 JDK 7 이미지**(`local/hadoop-docker:2.7.3-jdk7`, CentOS 7 + OpenJDK 7, 05 §7 결정)
- JDK 8 이미지(`2.7.3-jdk8`) 실행은 정해 둔 순서(JDK 7 이미지 → pi)를 어기고 먼저 돌린 **실행 경로 확인용** — 비교 참고로만 남김
- 비교 기준: reimpl-hadoop3 Step 3의 `pi 2 10` 5회 반복

## 실행 방법

SSH-to-localhost가 없어 `start-dfs.sh` 대신 데몬을 직접 띄움.

```bash
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-arm64; cd /opt/hadoop-2.7.3
bin/hdfs namenode -format -nonInteractive
sbin/hadoop-daemon.sh start namenode;  sbin/hadoop-daemon.sh start datanode
sbin/yarn-daemon.sh start resourcemanager; sbin/yarn-daemon.sh start nodemanager
bin/hdfs dfs -mkdir -p /user/gihyeon
bin/yarn jar share/hadoop/mapreduce/hadoop-mapreduce-examples-2.7.3.jar pi 2 10
```

## JDK 7 task 이미지 만들기

```bash
# 맥에서
scp -r -P 2214 original-hadoop2.7/setup gihyeon@127.0.0.1:legacy/
# VM에서 (기본 jdk7)
bash ~/legacy/setup/build-image.sh jdk7
```

- 구성: [Dockerfile.jdk7](../../setup/Dockerfile.jdk7) — `local/centos:7` + vault 저장소 + `java-1.7.0-openjdk-devel` + `which` + 교체본 tar + conf
- 이미지 이름: `local/hadoop-docker:2.7.3-jdk7` (yarn-site `image-name`), 1차 JDK 8 이미지는 `2.7.3-jdk8` 태그로 보존
- yarn-site에 `yarn.nodemanager.env-whitelist`를 `JAVA_HOME` 뺀 값으로 지정 (05 §6) — 호스트 NM은 JDK 8, task는 이미지 ENV의 JDK 7

### 만들면서 생긴 문제 [사실]

| 문제 | 원인 | 해결 |
|---|---|---|
| CentOS 컨테이너 안에서 root도 파일 생성 불가 (`Operation not permitted`) | CentOS rootfs 파일에 SELinux 확장 속성(xattr)이 붙어 있음, Docker 1.12 aufs가 복사 시 실패 [추측: 알려진 aufs 문제와 일치] | `tar --no-xattrs --no-selinux --no-acls`로 풀었다가 다시 묶어 `docker import` (파일 내용은 같음) |
| 이미지 안 `hadoop` 명령 실패 | 최소 CentOS에 `which` 없음 | `which` 설치 |
| 이미지 안 `hadoop` 명령이 JDK 8 경로 사용 | 호스트용으로 `*-env.sh`에 덧붙인 `JAVA_HOME=…java-8…` 줄이 tar에 포함 | Dockerfile에서 해당 줄 삭제 |

### JDK 7 확인 [사실]

- `OpenJDK 64-Bit Server VM (build 24.261-b02, mixed mode)` — **JIT 포함, Zero VM 아님**
- 2억 회 루프 104ms (Zero VM이면 수 초 이상)
- 이미지 안 YARN jar 13개 sha256이 호스트와 동일
- JDK 8로 컴파일한 원 저자 YARN jar(class 51)가 JDK 7에서 문제없이 동작 (pi 기준)

## 검증 결과 [사실]

| 항목 | 결과 |
|---|---|
| HDFS | NameNode + DataNode, Live datanodes 1 |
| YARN | RM + NM, `pf16-worker1.local` RUNNING, `<memory:2048, vCores:8>` |
| NM 로그 ERROR | 0건 |
| task 실행 위치 | AM·map×2·reduce 모두 `local/hadoop-docker:2.7.3-jdk7` 컨테이너, 프로세스는 `/usr/lib/jvm/java-1.7.0-openjdk/bin/java` |
| pi 2 10 (JDK 7) | **6/6 SUCCEEDED** (1회 + 5회 반복), `Estimated value of Pi is 3.8` |

| 이미지 | 5회 wall time (초) | 평균 ± 표준편차 |
|---|---|---|
| **JDK 7 (정식)** | 16.69 / 22.22 / 23.11 / 21.93 / 21.88 | **21.17 ± 2.55** |
| JDK 8 (참고) | 15.60 / 21.66 / 21.65 / 21.61 / 21.68 | 20.44 ± 2.71 |
| reimpl-hadoop3 (3.5.0) | — | 13.00 ± 1.33 |

- 두 이미지 모두 1회차만 빠르고 2회차부터 약 22초 — [추측] 컨테이너 기동 비용(docker run) 또는 NM heartbeat 주기와 맞물린 대기. 원인 확인은 후순위
- 전체 누적: 13/13 SUCCEEDED (JDK 8 7회 + JDK 7 6회)

### VM이 CPU를 1개만 씀 [사실] — 결정 필요

- VirtualBox 설정은 2 vCPU인데 게스트 커널(4.4.0-186)이 `Brought up 1 CPUs` → `nproc` 1
- 04 문서의 "2 vCPU"는 VM 설정값이었고, 실제 게스트는 1개
- 영향: CPU 1개면 JVM이 서버급으로 판단하지 않아 **JDK 7·8 모두 기본 GC가 Serial** → 05 §7의 "JDK 7 = Parallel GC" 차이가 이 VM에서는 안 나타남. suspend의 `--cpuset-cpus 0` 효과도 1코어라 구분이 약함 [추측]
- 논문 노드는 8코어 Xeon × 2 [논문 p.265], 커널 버전은 미명시 ("Ubuntu-16.04"만)

#### HWE 커널(4.15) 시도 → 실패, 4.4로 복귀 (2026-10-25) [사실]

- 결정: 16.04 공식 HWE 커널로 2 CPU 인식 시도 (실패 시 4.4 복귀 조건)
- 절차: Hadoop 데몬 중지 → VirtualBox 라이브 스냅샷 `pre-hwe-kernel` → `apt-get install linux-generic-hwe-16.04` (4.15.0-142, `linux-modules-extra` 포함, `swapaccount=1` 유지) → 재부팅
- 결과: **부팅이 Ubuntu 16.04 스플래시(점 반복)에서 멈춤**, 8분 이상 SSH 응답 없음 (원인 미확인 — `quiet splash`로 메시지가 가려짐)
- 복귀: 강제 종료 → 스냅샷 복원
  - ⚠️ 라이브 스냅샷의 메모리 상태 로드 실패 (`Failed to load unit 'virtio-scsi' (VERR_SSM_LOADED_TOO_LITTLE)`) → `VBoxManage discardstate` 후 스냅샷 디스크로 콜드 부팅
  - 복귀 후 확인: 커널 4.4.0-186, JDK 7 이미지·conf 그대로, HDFS/YARN 재기동 + pi 성공 (16.70초)
- 교훈: 이 VirtualBox(ARM) 환경에선 **라이브 스냅샷의 메모리 상태를 쓸 수 없음** → 스냅샷은 VM을 끈 상태에서 찍을 것
- 남은 선택지: ① 4.4 유지(1 CPU, 차이로 기록) ② `quiet splash` 빼고 4.15 재시도해 멈춘 원인 확인 ③ VirtualBox ARM 쪽 CPU/ACPI 설정 조사

## 확인된 사실

### 1. 모든 컨테이너가 REGULAR(normal) — puff/suspend 대상 아님 [사실]

- NM 로그: 컨테이너 전부 `set to be normal` (JDK 8 실행 기준 28개, JDK 7에서도 flexible 0개), 실제 `-Xmx`도 conf 값 384m (Flex면 `balloon.jvm-mb` 64GB로 치환됨)
- Flex 판정 경로 (원 코드):
  1. RM `RMAppManager.java:330-360` — **AM 리소스 요청의 node label expression이 `flex`일 때만** `isFlex=true`
  2. RM `ResourceTrackerService.java:374-381` → heartbeat로 Flex app 목록을 NM에 전달
  3. NM `ContainerManagerImpl.java:841-847` — 목록에 있는 app의 **AM이 아닌** 컨테이너만 `setFlexible()`
- MapReduce 2.7.3에는 AM node label을 지정하는 설정이 없음 (MR 모듈에 `node-label-expression` 0건) → `-Dmapreduce.job.am.node-label-expression=flex`로 실행해도 normal
  - [추측] 이 설정은 Hadoop 2.8.0부터
- 원 README는 "MapReduce는 FLEX로 인식하도록 하드코딩해 두었다"고 하지만, **공개 저장소에는 해당 코드가 없음** (MR 모듈·yarn-client 변경 0건, `git diff 86ae43c HEAD`)
- Spark는 `spark.yarn.am.nodeLabelExpression flex`로 지정 가능 (원 README)
- ⇒ **공개 코드로 puff/suspend를 시험하려면 Spark 필요** — Spark 2.0.1을 "pi 이후 추가"에서 **다음 단계 필수**로 앞당김

### 2. lazy reclaim 경로는 동작 [사실]

- 컨테이너 launch마다 `try to reclaim memory for new container` → `NodeMemoryManager: memory reclaim called, current assigned: 0 current used: 0 request: 512`, `limit: 1843.2`
- `limit 1843.2` = NM 2048MB × `balloon.reclaim` 0.9 [추측: 값 일치 기준]
- 메모리 여유가 있어 실제 회수는 없음

### 3. root 소유 파일로 정리 실패 (05 결정 J의 예상대로) [사실]

- 컨테이너가 root로 쓴 `jobSubmitDir/`, `output/attempt_*` 파일이 NM(gihyeon)에서 삭제 안 됨 → `Failed to delete ... it still exists` WARN
- job 성공에는 영향 없음, local-dir에 잔여 파일 누적
- 대응 후보 (원 코드 수정 없이): 주기적으로 `sudo rm`으로 정리 / NM을 root로 실행 — 실험 반복 전 결정

## 남은 단계

1. ~~task 이미지 CentOS 7 + OpenJDK 7 (Server VM 여부 확인) → pi 재실행~~ ✅
2. VM CPU 1개 문제 — HWE 4.15 부팅 실패로 4.4 복귀, 다음 방향 결정 (위 선택지 ①~③)
3. **Spark 2.0.1 on YARN** + `spark.yarn.am.nodeLabelExpression flex` → Flex 컨테이너에서 OCM·suspend·puff 로그 확인
4. root 소유 잔여 파일 처리 방식 결정
5. 3대 구성 → baseline(YARN만) vs Pufferfish
