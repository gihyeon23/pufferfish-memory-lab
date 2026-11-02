# 03. task 이미지 — 원 저자 이미지 sequenceiq/hadoop-docker:2.4.0 사용 (2026-11-01)

> 표기: [사실] 원 README·코드·이미지에서 확인 / **추측**

## 1. 목적

- 교수님 지시("하드웨어는 원논문에 최대한 맞출 것")에 맞춰 컨테이너 안쪽 OS·JDK도 원 저자와 맞춤
- 맥(ARM)에서는 CentOS 6 ARM64판이 없어 CentOS 7 + OpenJDK 7로 대신했음. x86에서는 이 제약이 없음

## 2. 결정 — A안

| 안 | 구성 | 결과 |
|---|---|---|
| **A** | 원 이미지 + 우리 Hadoop 2.7.3 교체본 | **채택** — OS·JDK 모두 원본과 같음 |
| B | CentOS 6.5 rootfs + OpenJDK 7 직접 구성 | JDK가 Oracle이 아님 |
| C | CentOS 7 + OpenJDK 7 (기존) | OS 다름 |

- 태그는 **2.4.0** [사실]: 원 README "We have tested `/sequenceiq/hadoop-docker:2.4.0`", 원 코드 기본값 `YarnConfiguration.java:1009`
- 논문에는 태그가 적혀 있지 않음 (p.265)
- **JDK 7/8 비교는 하지 않음** (2026-11-01): 10/26 랩미팅 검증 계획(같은 워크로드를 JDK 7/8 이미지로 비교)을 취소하고, 원 저자와 같은 JDK 7(7u51)로만 진행. x86에서 jdk8 이미지는 만들지 않음

## 3. 이미지 내용 확인 [사실: 레지스트리 매니페스트·레이어]

| 항목 | 2.4.0 (채택) | 2.7.1 (최신 태그, 참고) |
|---|---|---|
| OS | CentOS 6.5 (`/etc/centos-release`) | CentOS 6 계열 |
| JDK | **Oracle JDK 7u51** (`/usr/java/jdk1.7.0_51`) | Oracle JDK 7u71 |
| 안쪽 Hadoop | 2.4.0 | 2.7.1 |
| 생성일 | 2014-11-05 | 2015-12-13 |

- **기존 문서 정정**: arm-mac 02·04·05에 원 저자 JDK를 "7u71"로 적었는데, 7u71은 2.7.1 태그 기준임. 원 저자가 테스트한 2.4.0 태그는 7u51 → 해당 문서 수정함

## 4. 설계 · 받는 방법

- 문제
  - Docker 1.12.1: 지금은 Docker Hub에서 pull 불가
  - 최신 Docker(맥, 29.x): 이 이미지 manifest가 옛 형식(schema v1)이라 pull 불가
- 해결: [../../setup/fetch-sequenceiq-image.py](../../setup/fetch-sequenceiq-image.py)
  - 레지스트리 API로 레이어를 직접 받고, sha256으로 검증
  - `docker load`용 legacy 형식(`<id>/json`, `layer.tar`, `repositories`)으로 묶음 → 원본의 레이어·ENV가 그대로 유지됨
  - 2.4.0 매니페스트는 최상위 레이어가 두 번 들어 있음 → 중복은 건너뜀 (레이어 49개 → 48개)
- 빌드: [../../setup/Dockerfile.sequenceiq](../../setup/Dockerfile.sequenceiq)
  - 원 이미지를 `FROM`으로 쓰고, 그 위에 `/opt/hadoop-2.7.3` 교체본을 추가함
  - `HADOOP_*` 환경변수는 교체본을 가리키도록 덮어씀
  - `JAVA_HOME`은 원본 값(`/usr/java/default`, 7u51)을 그대로 씀
- [../../setup/build-image.sh](../../setup/build-image.sh)
  - amd64에서는 기본 변형을 `sequenceiq`로 바꿈
  - 호스트 `yarn-site.xml`의 `image-name`을 이번에 빌드하는 이미지로 맞춤

## 5. 실행 방법 (VM)

```bash
python3 ~/legacy/setup/fetch-sequenceiq-image.py ~/legacy/dl/sequenceiq   # 약 450MB 다운로드 → 813MB tar
docker load -i ~/legacy/dl/sequenceiq/sequenceiq-hadoop-docker-2.4.0.tar
bash ~/legacy/setup/build-image.sh            # amd64 기본 = sequenceiq
bash ~/legacy/setup/hadoop.sh start
```

- VM에서 Docker Hub에 접속이 안 되면, 맥에서 같은 스크립트를 실행한 뒤 tar를 `scp`로 옮김
  - 맥의 python.org판 Python은 인증서 오류가 나므로 `/usr/bin/python3`를 씀

## 6. 확인 포인트

```bash
docker images | grep -E "sequenceiq|local/hadoop-docker"
docker run --rm sequenceiq/hadoop-docker:2.4.0 cat /etc/centos-release           # CentOS release 6.5
docker run --rm local/hadoop-docker:2.7.3-sequenceiq bash -c 'java -version; hadoop version | head -1'   # 1.7.0_51, Hadoop 2.7.3
grep -A1 image-name /opt/hadoop-2.7.3/etc/hadoop/yarn-site.xml                   # 2.7.3-sequenceiq
```

- CentOS 6(glibc 2.12)이 호스트 커널 4.4에서 문제없이 실행되는지 → 위 `docker run`으로 확인 (**추측**: 16.04 커널 기본 설정에서는 문제없음)

## 7. 남은 차이

- 안쪽 Hadoop 2.4.0 → 2.7.3 교체본 (arm-mac 05 §2 결정 유지)
  - 원 저자는 이미지 안의 2.4.0을 그대로 썼을 가능성 있음 (**추측**)

### 예정: 안쪽 Hadoop을 원본 2.4.0으로 되돌리기 (2026-11-02 결정, 미실행)

- 원인: 맥(ARM)에선 원 이미지를 못 써서 "안쪽 Hadoop = 호스트 2.7.3"으로 정했고(arm-mac 05), x86에서 원 이미지를 쓰게 된 뒤에도 이 결정을 다시 검토하지 않고 공통 `setup/`에 그대로 둠
  - JDK는 이미 원본(7u51)을 쓰게 맞춤 (`env-whitelist`에서 `JAVA_HOME` 제외) — Hadoop만 같은 처리를 안 함
- 방법 (원 코드 수정 없이 설정만)
  1. [../../setup/Dockerfile.sequenceiq](../../setup/Dockerfile.sequenceiq): 교체본 `ADD`·`HADOOP_*` ENV 덮어쓰기 제거 → 원 이미지의 `/usr/local/hadoop`(2.4.0) 사용
  2. [../../setup/conf/yarn-site.xml](../../setup/conf/yarn-site.xml) `yarn.nodemanager.env-whitelist`에서 `HADOOP_*` 제거 → NM이 호스트 경로를 컨테이너에 넣지 않게 (`ContainerLaunch.java:682-687`)
  3. 확인: pi(DCE) → Spark Flex([06](06-spark-flex.md)) → Fig 6(a) 재실행([09](09-fig6a-puff.md))
- 확인할 위험: 컨테이너 안 Hadoop 2.4.0 + 호스트 YARN 2.7.3 혼합 (2.x끼리는 대체로 호환, **추측**)
- 그때까지의 결과(06~09)는 "안쪽 Hadoop만 2.7.3"인 조건으로 해석 — Pufferfish 동작은 컨테이너 바깥(NM·cgroup), Spark executor는 자기 jar를 써서 영향 작음 (**추측**)

## 8. 검증 결과

- 맥: 받아서 묶기까지 확인 (레이어 48개, CentOS 6.5, `jdk1.7.0_51`)
- VM (2026-11-01): Docker Hub에 직접 접속해서 받음 — 맥에서 옮길 필요 없음

| 확인 | 결과 |
|---|---|
| `fetch-sequenceiq-image.py` | 블롭 32개 sha256 검증 통과, 813MB tar |
| `docker load` (Docker 1.12.1) | 레이어 48개 로드, legacy 형식 그대로 읽힘 |
| `sequenceiq/hadoop-docker:2.4.0` 실행 | `CentOS release 6.5 (Final)` — 커널 4.4에서 문제없음 |
| `build-image.sh` (기본 = sequenceiq) | `local/hadoop-docker:2.7.3-sequenceiq` 1.171GB |
| 빌드한 이미지 안 | `java version "1.7.0_51"` (Java HotSpot 64-Bit Server VM 24.51-b03), `Hadoop 2.7.3` |

- 호스트 `yarn-site.xml`의 `image-name` = `local/hadoop-docker:2.7.3-sequenceiq` 확인

## 9. pi 실패 — 맥 VM 값이 설정에 고정돼 있었음

- 증상
  - `hadoop.sh start`가 아무것도 출력하지 않음
  - pi 실행 시 `java.net.UnknownHostException: pf16-worker1` 발생
  - `docker ps -a`에 컨테이너 없음
- 원인 [사실: `setup/conf`]
  - `fs.defaultFS`·`yarn.resourcemanager.hostname`에 맥 VM 호스트명 `pf16-worker1`이 들어 있음. 이 VM 호스트명은 `ubuntu`
  - `hadoop.tmp.dir`이 `/home/gihyeon/hadoop-data`. 이 VM 사용자는 `inuos`
  - `hadoop.sh`는 namenode 포맷 출력을 `/dev/null`로 버리고 `set -e`로 종료함 → 실패가 안 보였음 (**추측**: 포맷 실패로 데몬을 하나도 안 띄우고 종료)
- 수정
  - `conf/*.xml`의 값을 `@HOST@`·`@HOME@`으로 바꿈
  - `build-image.sh`가 `hostname`·`$HOME`으로 채워서 호스트와 이미지에 같이 넣음 (image-name도 같은 단계에서 설정)
  - `hadoop.sh`: 포맷 로그를 `logs/format.log`에 남기고, 실패하면 메시지를 출력한 뒤 중단
- 주의: 3대 클러스터로 넘어가면 `@HOST@` 자리가 master 주소여야 함 → 그때 다시 정함

## 10. 재실행 (VM)

```bash
scp -r ~/pufferfish-memory-lab/original-hadoop2.7/setup labvm:legacy/   # 맥에서
bash ~/legacy/setup/hadoop.sh stop; jps                                  # 떠 있는 데몬 정리
bash ~/legacy/setup/build-image.sh                                       # 설정 생성 + 이미지 재빌드
grep -A1 -E "defaultFS|tmp.dir|resourcemanager.hostname" /opt/hadoop-2.7.3/etc/hadoop/{core,yarn}-site.xml
bash ~/legacy/setup/hadoop.sh start
cd /opt/hadoop-2.7.3 && bin/yarn jar share/hadoop/mapreduce/hadoop-mapreduce-examples-2.7.3.jar pi 2 10
```

### 결과 (2026-11-01) — pi 성공

| 확인 | 결과 |
|---|---|
| 생성된 설정 | `fs.defaultFS=hdfs://ubuntu:9000`, `hadoop.tmp.dir=/home/inuos/hadoop-data`, `resourcemanager.hostname=ubuntu` |
| task 컨테이너 | `local/hadoop-docker:2.7.3-sequenceiq`로 `container_1793510223414_0001_01_000001`(AM) 기동 — DCE가 원 이미지를 씀 |
| 잡 | `application_1793510223414_0001` QuasiMonteCarlo — **FINISHED / SUCCEEDED**, 100% |
| 잡 종료 후 | `docker ps -a`에서 컨테이너가 정리됨 |

- map 컨테이너는 짧게 돌고 끝나서 `docker ps`로는 못 잡음 → 다음에는 NM 로그로 컨테이너 수·이미지 확인
- RM 주소가 `ubuntu/127.0.1.1:8032` (16.04 `/etc/hosts`의 `127.0.1.1 ubuntu`) → 단일 노드는 문제없지만, 3대 구성 때는 실제 IP로 바꿔야 함
