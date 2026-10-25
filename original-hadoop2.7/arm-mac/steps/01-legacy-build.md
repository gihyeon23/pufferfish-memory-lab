# Legacy 1 — 원 저자 코드(Hadoop 2.7.3) 빌드 환경 구성

> 랩미팅: 2026-10-26 / 배경: [10월 7일 피드백](../../../common/lab-meetings/2026-10-05/2026-10-05.md) 후속 — "B안: 원 코드 그대로 재현" 결정
>
> 표기: **[사실]** 원 코드·실행 결과로 확인 / **[추측]** 내 해석

## 목적

**한 줄 요약: 원 저자 Pufferfish 코드(Hadoop 2.7.3 기반)를 지금 VM(ARM64, Ubuntu 24.04)에서 빌드할 수 있는지 확인한다.**

- 10/7 피드백: 외부 데몬(A안) 중단, 원 코드 활용 → 먼저 "원 구현이 제대로 동작하는지" 재현
- 최신 Hadoop 3.5.0 환경(Step 0~3)은 C안(포팅)용으로 스냅샷 보존

## 진행 기록

### 0. 기존 환경 보존 (2026-10-13)

```bash
# 맥에서, VM 3대 모두 꺼진 상태로
for v in pf-control pf-worker1 pf-worker2; do
  VBoxManage snapshot $v take "step3-hadoop350-yarn-ok" \
    --description "2026-10-13 Hadoop 3.5.0 + JDK17, Step 3 YARN OK. C안 복귀용"
done
```

- 복귀: `VBoxManage snapshot <vm> restore step3-hadoop350-yarn-ok`
- 빌드는 메모리가 가장 큰 `pf-worker1`(3.5 GB) 한 대에서만 진행 (맥 swap 4.0/5.1 GB 사용 중이라 3대 동시 기동 회피)

### 1. 원 코드 분석 (맥 로컬, `~/legacy-src/pufferfish`)

- 저장소: <https://github.com/yncxcw/pufferfish> — 커밋 131개, 2016-11-02 ~ 2018-09-30, Apache-2.0 [사실]
- `86ae43c initial commit` = 바닐라 Hadoop 2.7.3 import (pom `version>2.7.3`) [사실]
- **원 저자 수정 규모** (`git diff 86ae43c HEAD`, md 제외) [사실]
  - 전체 73파일 +6146 / −122, 이 중 로그·테스트 파일(`Memory-monirot/*.log`, `memory_test/*`) 약 3,700줄
  - **실제 Java 코드 수정 ≈ 2,400줄 / 약 45파일**
  - 핵심: `ContainerImpl.java` +872, `NodeMemoryManager.java` 신규 497, `LeafQueue.java` +118, `DockerContainerExecutor.java` +81
  - NM뿐 아니라 **RM(스케줄러: `LeafQueue`, `SchedulerNode`, `CapacityScheduler`)과 heartbeat 프로토콜(proto)까지 수정** → C안 포팅 시 NM만 고쳐서는 안 됨
- **cgroup v1 전제가 코드에 하드코딩** [사실] (`ContainerImpl.java:764-766`)
  ```java
  memoryPath= "/sys/fs/cgroup/memory/docker/"+dockerId+"/";
  cpuPath   = "/sys/fs/cgroup/cpu/docker/"+dockerId+"/";
  cpuSetPath= "/sys/fs/cgroup/cpuset/docker/"+dockerId+"/";
  ```
  - 읽는 파일: `memory.limit_in_bytes`, `memory.usage_in_bytes`, `memory.stat`, `cpuset.cpus` → 전부 **cgroup v1 인터페이스**
  - 경로 `/docker/<id>` → Docker **cgroupfs 드라이버** 전제 (systemd 드라이버면 `system.slice/docker-<id>.scope`)
  - `docker run --oom-kill-disable`도 cgroup v2에서는 Docker가 지원하지 않음 [사실: Docker 문서] → v1 필수
  - ⇒ 기존 [pufferfish-architecture.md](../../../common/pufferfish-architecture.md) §2.5의 "cgroup 버전: 코드에 명시된 근거 없음"을 **"원 공개 구현은 cgroup v1 하드코딩"으로 정정**
- suspend 구현 [사실]: `docker update --cpu-quota 1000` + `--cpuset-cpus 0` (CPU 1% + 단일 코어) — 논문 p.260과 일치

### 2. 빌드 도구 설치 (`pf-worker1`)

```bash
sudo apt-get install -y openjdk-8-jdk-headless maven build-essential \
  autoconf automake libtool zlib1g-dev pkg-config
```

- JDK 8: `8u504-ga-1ubuntu1~24.04.3` (Ubuntu universe), Maven 3.8.7
- 기존 JDK 17은 그대로 두고 빌드 시 `JAVA_HOME=/usr/lib/jvm/java-8-openjdk-arm64`로 지정

### 3. protoc 2.5.0 — ARM64 패치 빌드 ✅

- 문제: Hadoop 2.7.3 빌드는 **정확히 `libprotoc 2.5.0`** 요구, 그런데 2.5.0은 aarch64 미지원(atomicops 없음) [사실]
- 해결: 2.6.1의 `atomicops_internals_arm64_gcc.h`를 가져와 2.5.0에 이식

```bash
cd ~/legacy
curl -sSLO https://github.com/protocolbuffers/protobuf/releases/download/v2.5.0/protobuf-2.5.0.tar.gz
curl -sSLO https://github.com/protocolbuffers/protobuf/releases/download/v2.6.1/protobuf-2.6.1.tar.gz
tar xzf protobuf-2.5.0.tar.gz && tar xzf protobuf-2.6.1.tar.gz
cd protobuf-2.5.0/src/google/protobuf/stubs
cp ~/legacy/protobuf-2.6.1/src/google/protobuf/stubs/atomicops_internals_arm64_gcc.h .
# platform_macros.h: __QNX__ 앞에 aarch64 분기 추가
sed -i "s|^#elif defined(__QNX__)$|#elif defined(__aarch64__)\n#define GOOGLE_PROTOBUF_ARCH_AARCH64 1\n#define GOOGLE_PROTOBUF_ARCH_64_BIT 1\n#elif defined(__QNX__)|" platform_macros.h
# atomicops.h: ARM 앞에 AARCH64 include 추가
sed -i "s|^#elif defined(GOOGLE_PROTOBUF_ARCH_ARM)$|#elif defined(GOOGLE_PROTOBUF_ARCH_AARCH64)\n#include <google/protobuf/stubs/atomicops_internals_arm64_gcc.h>\n#elif defined(GOOGLE_PROTOBUF_ARCH_ARM)|" atomicops.h
cd ~/legacy/protobuf-2.5.0 && ./configure --prefix=/usr/local && make -j3 && sudo make install && sudo ldconfig
protoc --version   # libprotoc 2.5.0
```

### 4. 원 코드 Maven 빌드

```bash
# ~/legacy/build.sh (nohup 백그라운드)
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-arm64
export MAVEN_OPTS="-Xmx1536m"
cd ~/legacy/pufferfish
mvn -B package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true > ~/legacy/build.log 2>&1
```

- `-Pnative` 제외 (네이티브 라이브러리는 Java fallback 사용, 기능 재현에는 불필요 [추측])
- 1차: **실패** — 원 저자 테스트 코드 컴파일 오류 (`MockNodes.java:99`, `getCurrentRealMemory()` 미구현). 본 코드(NM 포함)는 통과
- 2차 (`-Dmaven.test.skip=true -rf :hadoop-yarn-server-resourcemanager`): **dist 단계 실패** — `hadoop-mapreduce-dist`가 `tests` jar를 요구
- 확보한 것: 원 저자 수정 YARN jar 10개 (`hadoop-yarn-{api,common,client,registry}`, `hadoop-yarn-server-{common,nodemanager,resourcemanager,web-proxy,applicationhistoryservice,sharedcachemanager}-2.7.3.jar`)
- 다음 방법(보류 중): 공식 `hadoop-2.7.3.tar.gz`를 받아 YARN jar만 교체 — 원 저자 수정은 YARN 모듈에만 있어 결과는 동일 [사실: diff에 HDFS·MapReduce 변경 없음]

## 남은 단계 (B안)

> 진행 범위: **`pf-worker1` 한 대**(단일 노드)에서 원 구현 동작 확인까지. control·worker2는 미변경(3.5.0 그대로). 환경 차이는 [02-env-diff.md](02-env-diff.md)

1. 공식 2.7.3 바이너리 + YARN jar 교체 (보류 중)
2. Ubuntu 24.04 → cgroup v1 부팅 전환 (`systemd.unified_cgroup_hierarchy=0`, systemd 255라 가능 [추측, 확인 예정])
3. Docker 설치 + cgroupfs 드라이버 설정
4. 3대에 배포 → 원 구현 YARN 기동 → pi 예제로 동작 확인
5. 원 구현 OCM/suspend/puff 로그 확인 (실험은 시험 이후)
