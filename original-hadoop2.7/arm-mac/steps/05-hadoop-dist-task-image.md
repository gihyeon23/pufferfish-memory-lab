# Legacy 4 — 실행용 Hadoop 2.7.3 구성 + task Docker 이미지

> 랩미팅: 2026-10-26 / 이전: [04-ubuntu1604-env.md](04-ubuntu1604-env.md)
>
> 표기: **[사실]** 실측·원 코드 확인 / **[추측]** 내 해석

## 목적

**한 줄 요약: 원 코드를 수정하지 않고 실행용 Hadoop 묶음(`/opt/hadoop-2.7.3`)과 task 이미지(`local/hadoop-docker:2.7.3`)를 만든다.**

- 소스 전체 빌드는 dist 단계에서 실패함 [사실: `build-pass2/A/B.log`] → 공식 2.7.3 바이너리에 원 저자 YARN jar만 교체
- 파일: [original-hadoop2.7/setup/](../../setup/) (Dockerfile, conf, build-image.sh, cmpsig.py)

## 1. 결정 사항 (2026-10-24)

| 항목 | 결정 | 이유 |
|---|---|---|
| Hadoop 묶음 | 공식 2.7.3 + 원 저자 YARN jar 13개 교체 | 원 코드 무수정 |
| 설치 경로 | `/opt/hadoop-2.7.3` (호스트 = 이미지) | DCE가 NM 쪽 경로를 그대로 쓸 수 있음 [추측] → 같게 맞춤 |
| 이미지 안 Hadoop | 호스트와 같은 교체본 | 원 저자는 `sequenceiq/hadoop-docker:2.4.0`(Hadoop 2.4.0) 사용 [사실: 원 README] → **차이** |
| JDK | OpenJDK 8u292, `/usr/lib/jvm/java-8-openjdk-arm64` (호스트 = 이미지) | xenial에 JDK 7 없음 |
| 이미지 안 설정 | 이미지에 넣음, 바꾸면 재빌드 | DCE는 local/log/work dir만 마운트 [사실: `DockerContainerExecutor.java:210-229`] |
| 네이티브 라이브러리 | 공식 x86 `.so` 그대로 (ARM에선 Java 구현으로 대체) | ARM용 빌드 생략 |
| 컨테이너 안 계정 | root (sequenceiq와 같음) | 파일 정리 실패 여부는 기동 시 확인 |
| Spark 2.0.1 | MR pi 확인 후 추가 | 원인 분리 |

## 2. 공식 바이너리 받기

```bash
wget https://archive.apache.org/dist/hadoop/common/hadoop-2.7.3/hadoop-2.7.3.tar.gz{,.mds}
sha256sum hadoop-2.7.3.tar.gz   # d489df38…b09259c2 — .mds와 일치 [사실]
```

## 3. "공식 바이너리 + 원 저자 YARN jar = 원 저자 소스 전체 빌드" 검증

- 바이트 비교(.class sha256)는 Common/HDFS/MR도 60~100% 다름 → 의미 없음
  - 원인 [사실]: 공식 jar `Build-Jdk: 1.7.0_111`, 우리 빌드 `1.8.0_292` (class 버전은 둘 다 51)
- **javap 시그니처 비교**(클래스·필드·메서드 목록)로 전환: [cmpsig.py](../../setup/cmpsig.py), 결과 [05-cmpsig.log](05-cmpsig.log)

| 구분 | 결과 [사실] |
|---|---|
| Common / HDFS / MapReduce (12 jar, 약 7,300 class) | 4 class만 다름 — 전부 컴파일러 자동 생성 `access$NNN` (JDK 7은 `access$N14`/`$N12`, JDK 8은 `access$N02`) → **소스 동일** |
| YARN 중 무수정 9 jar | 전부 동일 |
| `hadoop-yarn-api` | `YarnConfiguration` 1개 — `balloon.*` 설정 상수 추가 |
| `hadoop-yarn-server-common` | 26 class 변경 + 2 추가 (heartbeat proto 등) |
| `hadoop-yarn-server-nodemanager` | 15 변경 + 8 추가 (`NodeMemoryManager`, `ContainerMemoryState` 등) |
| `hadoop-yarn-server-resourcemanager` | 12 변경 (`RMNode`, `SchedulerNode`, `RMContainer` 등) |

- ⇒ 원 저자 수정은 YARN 4개 jar에만 있고, 나머지는 공식과 같음. 13개 전부 교체(같은 소스에서 빌드한 세트로 통일)
- 교체 위치: `share/hadoop/yarn/` 13개뿐 (다른 폴더에 YARN jar 없음 [사실]). 원본은 `~/legacy/official-yarn-jars/`에 백업

## 4. 원 저자 설정 키 [사실: 원 `YarnConfiguration` diff, README]

| 키 (`yarn.nodemanager.` +) | 기본값 | 의미 |
|---|---|---|
| `balloon.ratio` | 0.4 | 최우선 컨테이너 puff 비율 (논문 ϕ) |
| `balloon.stop` | 0.8 (README 예시는 0.9) | 노드 메모리 이 비율 넘으면 puff 중단 |
| `balloon.reclaim` | 0.9 | 이 비율 넘으면 reclaim |
| `balloon.jvm-mb` | 65536 | Flex 컨테이너 JVM 힙(`MAX_HEAP`) |
| `balloon.memory-mb` | -1 | 정적 컨테이너 크기(테스트용) |
| (변경) `container-monitor.interval-ms` 기본값 | 3000 → 2000 | |

- 이번 conf는 balloon.* 전부 기본값 유지

## 5. task 이미지 빌드

```bash
# 맥에서
scp -r -P 2214 original-hadoop2.7/setup gihyeon@127.0.0.1:legacy/
# VM에서
bash ~/legacy/setup/build-image.sh   # 호스트 conf 반영 → tar → docker build
```

- 구성: `local/ubuntu:16.04` + `openjdk-8-jdk-headless` + 교체본 tar + conf + `JAVA_HOME`/`HADOOP_*` ENV
- conf (단일 노드, VM 3GB): NM 2048MB, 최소 할당 256MB, map/reduce/AM 512MB(`-Xmx384m`), DCE + 이미지 `local/hadoop-docker:2.7.3`

## 6. task 이미지 — 원 저자 환경과의 차이

| 항목 | 원 저자 | 우리 | 다른 이유 |
|---|---|---|---|
| 이미지 | `sequenceiq/hadoop-docker:2.4.0` [사실: 원 README "tested 2.4.0"], 논문은 태그 미명시 (p.265) | `local/hadoop-docker:2.7.3` | x86 전용 + Docker 1.12.1은 Docker Hub pull 실패 |
| 안쪽 OS | CentOS 6.5 | Ubuntu 16.04 | CentOS 6 ARM64판 없음 |
| JDK | Oracle JDK 7u71 | **OpenJDK 8u292** | xenial에 JDK 7 없음 → 아래 "JDK 7 대안" 참고 |
| 안쪽 Hadoop | 2.4.0 [추측: 태그명] | 2.7.3 (교체본) | 호스트와 통일 |
| CPU | x86 | ARM | 맥 M4 |

### NM 환경변수가 이미지 ENV를 덮어씀 [사실]

- NM은 `yarn.nodemanager.env-whitelist`의 변수(`JAVA_HOME`, `HADOOP_COMMON_HOME`, `HADOOP_HDFS_HOME`,
  `HADOOP_CONF_DIR`, `HADOOP_YARN_HOME`)를 **자기 환경값으로** 컨테이너 실행 환경에 넣음
  (앱이 따로 지정하지 않은 경우) — `ContainerLaunch.java:682-687, 742-745`, 기본값 `yarn-default.xml:757`
- launch 스크립트가 이 값을 export → 이미지 ENV보다 우선
- ⇒ 호스트와 이미지의 설치 경로를 같게(`/opt/hadoop-2.7.3`, `/usr/lib/jvm/java-8-openjdk-arm64`) 맞춘 것이 필수였음
- [추측] 원 저자는 호스트 경로를 sequenceiq와 같게(`/usr/local/hadoop`, `/usr/java/default`) 맞췄고,
  task는 **컨테이너 안 Hadoop 2.4.0 jar**로 실행됐을 가능성이 큼
- 이미지 안 경로를 다르게 쓰려면 원 코드 수정 없이 설정으로 가능: `env-whitelist`에서 해당 변수를 빼면 이미지 ENV가 쓰임

### 결과에 미칠 영향 (큰 순서) [추측]

1. **JDK 7 → 8**
   - PermGen 폐지 → Metaspace(힙 밖 네이티브 메모리)로 바뀌어 컨테이너 메모리 구성이 달라짐
   - 8u191부터 JVM이 cgroup 메모리 한도를 인식함 [사실] → `-Xmx`를 안 주면 기본 힙 기준이 "호스트 RAM"에서 "컨테이너 한도"로 바뀜
   - 우리 conf는 map/reduce/AM `-Xmx384m`을 명시해서 이 영향은 피함. Flex 컨테이너 힙(`balloon.jvm-mb`)이 어떻게 적용되는지는 확인 필요
2. **x86 → ARM**: JIT·메모리 사용량에 소폭 차이
3. **안쪽 Hadoop 2.4.0 → 2.7.3**: MR task 쪽 코드만 다름. Spark executor는 자기 jar를 따로 받아 써서 영향 작음
4. **CentOS 6.5 → Ubuntu 16.04**: glibc 차이 정도

- Pufferfish 동작(OCM 감지·suspend·puff·reclaim)은 컨테이너 **바깥**(NM + cgroup)에서 일어나 원 코드 그대로임

### JDK 7 대안 — ARM64용 OpenJDK 7 확보 가능 [사실: 2026-10-24 확인]

| 후보 | 패키지 |
|---|---|
| Ubuntu 14.04 arm64 base + OpenJDK 7 | `openjdk-7-jdk_7u211-2.6.17-0ubuntu0.1_arm64.deb` (ports.ubuntu.com), base `ubuntu-base-14.04.x-core-arm64.tar.gz` |
| CentOS 7 aarch64 + OpenJDK 7 | `java-1.7.0-openjdk-1.7.0.261-2.6.22.2.el7_8.aarch64.rpm` (vault.centos.org altarch) |

- 원 코드 jar는 class 버전 51(Java 7)이라 JDK 7에서 실행 가능 [사실]
- 확인 필요: ARM64 OpenJDK 7이 JIT 포함 Server VM인지, 인터프리터 전용 Zero VM인지 [추측: IcedTea 2.6은 AArch64 JIT 포함]
- 경로가 호스트와 다르면 `env-whitelist`에서 `JAVA_HOME`만 빼면 됨 (설정 변경)
- 결정 대기 — 교수님 확인 후 진행

## 7. 이미지 결정이 puff·reclaim·suspend에 주는 영향

### 메커니즘은 컨테이너 바깥 → 이미지와 무관 [사실: 원 구현]

- 판단·실행 주체는 NodeManager + cgroup v1 (§2.5 [pufferfish-architecture.md](../../../common/pufferfish-architecture.md))
  - OCM: `memory + swap > limit` (`ContainerImpl.getIsOutofMemory()`)
  - suspend: `docker update --cpu-quota 1000 --cpuset-cpus 0`
  - puff: `min(old×0.4, 남은여유/2)`, EJF / reclaim: 신규 컨테이너 launch 시 (`ContainerManagerImpl.java:880`)
- 컨테이너 안 OS는 커널을 공유 → cgroup 동작 같음 ⇒ **베이스 OS(CentOS/Ubuntu)는 메커니즘에 무관**

### JDK는 메커니즘의 "입력"을 바꿈

- 원 코드는 Flex 컨테이너의 `-Xmx`를 `balloon.jvm-mb`(기본 64GB)로 **강제 치환** [사실: `DockerContainerExecutor.java:353-366`]
  - 힙이 컨테이너 한도를 넘어 swap → OCM → puff로 받아내는 설계
  - ⇒ **JVM이 힙을 언제·얼마나 늘리는지**가 OCM 시점·횟수를 결정

| 차이 | JDK 7u71 (원 저자) | JDK 8u292 (현재 이미지) |
|---|---|---|
| JVM이 보는 메모리 | 호스트 RAM | **컨테이너 한도** (8u191+ cgroup 인식) [사실] |
| 기본 GC | Parallel GC (서버급) | 한도 약 1.8GB 미만이면 **Serial GC 가능** [JDK 동작, 실측 확인 필요] |
| 초기 힙 기본값 | 호스트 RAM의 1/64 | 컨테이너 한도의 1/64 |
| 클래스 메타데이터 | PermGen (힙 영역) | Metaspace (힙 밖 네이티브) |

- `-Xmx`는 64GB로 같지만 **GC 종류·힙 확장 속도**가 달라져 swap 진입 시점·양이 달라짐 [추측]
- ⚠️ 2026-10-25 실측: 현재 VM은 게스트가 CPU 1개만 인식 → JDK 7·8 모두 기본 GC가 Serial (서버급 판정 실패). 이 VM에서는 GC 차이가 안 나타남 — 06 참고

### 메커니즘별 영향 [추측]

| 메커니즘 | 판단 로직 | 입력 변화로 인한 영향 | 정도 |
|---|---|---|---|
| OCM 감지 | 같음 | 메모리+swap 증가 패턴 변화 → 감지 시점·횟수 | 중간 |
| puff | 같음 | OCM 횟수 따라 puff 횟수·최종 크기 | 중간 |
| CPU 1% suspend | 같음 | 제한 동작은 커널 기능이라 같음, 발생 횟수만 OCM 따라감 | 작음 |
| reclaim | 같음 | 트리거(launch)는 같음, 회수량은 실사용량 기준이라 간접 영향 | 작음~중간 |

### 결정 (2026-10-24)

- **task 이미지는 JDK 7 계열 사용** — 노션 계획(CentOS 7 + OpenJDK 7)대로
  - 메커니즘 입력(힙 확장 패턴)을 원 저자와 같은 계열로 유지
  - CentOS 7은 원 이미지(CentOS 6.5) 계열과도 가까움
- JDK 8 대안(설정만): `-XX:-UseContainerSupport -XX:+UseParallelGC` — "맞춤"이 아니라 "흉내"라 차선
- 전제 확인 필요: ARM64 OpenJDK 7이 JIT 포함 Server VM인지 (Zero VM이면 실험 불가 → JDK 8 + 위 옵션으로 후퇴)
  - ✅ 2026-10-25 확인: `OpenJDK 64-Bit Server VM (build 24.261-b02, mixed mode)` — 이미지 `local/hadoop-docker:2.7.3-jdk7`, 06 참고

### 검증 계획

- 같은 워크로드를 JDK 7 / JDK 8 이미지로 각각 실행 → OCM 횟수, puff 횟수, swap 최대치, 완료 시간, 실제 GC(`-XX:+PrintCommandLineFlags`) 비교
- 차이 작음 → "이미지 차이 영향 작음" 근거 / 차이 큼 → JDK 7 필수 근거

## 확인 포인트 / 검증 결과 [사실]

- [x] `docker build` 성공 — `local/hadoop-docker:2.7.3`, 705.8MB
- [x] 컨테이너 안 `java -version` = 1.8.0_292, `hadoop version` = 2.7.3 (호스트와 같음)
- [x] 컨테이너 vs 호스트 YARN jar 13개 sha256 전부 일치
- [x] `--net=host`에서 hostname = `pf16-worker1`
- [ ] YARN 기동 + DCE로 pi 실행 (다음 단계)

## 남은 단계

1. HDFS/YARN 단일 노드 기동 → pi 예제 (DCE 경유 확인)
2. root 소유 파일 때문에 local-dirs 정리가 실패하는지 확인
3. OCM/suspend/puff 로그 확인
4. Spark 2.0.1 추가 → VM 복제로 3대 구성
