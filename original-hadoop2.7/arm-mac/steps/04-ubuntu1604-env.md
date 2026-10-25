# Legacy 3 — Ubuntu 16.04 + Docker 1.12.1 환경 구축 (논문 환경 맞추기)

> 랩미팅: 2026-10-26 / 이전: [03-ubuntu1604-boot-test.md](03-ubuntu1604-boot-test.md) / 차이표: [02-env-diff.md](02-env-diff.md)
>
> 표기: **[사실]** 실측 / **[추측]** 내 해석

## 목적

**한 줄 요약: 논문 환경(Ubuntu 16.04 · Docker 1.12.1 · YARN 2.7.3)을 맥(M4) VM 한 대에 그대로 구성하고, 원 코드 빌드 환경을 24.04(`pf-worker1`)에서 이쪽으로 옮긴다.**

- 결정 (2026-10-24): "그때 환경으로 하는 게 목표" → 16.04 전체 설치 후 이전
- VM: `u1604-test` (호스트명 `pf16-worker1`), 2 vCPU / 3GB / 20GB, NAT, SSH `127.0.0.1:2214`
- 기존 pf-* VM 3대(3.5.0)는 미변경

## 1. 16.04 자동 설치 (preseed)

- 화면 출력이 안 되므로(03 참고) **시리얼 콘솔 + preseed 자동 설치**
- 맥에서 `python3 -m http.server 8000`으로 `preseed.cfg` 제공 → VM은 NAT 게이트웨이 `10.0.2.2:8000`으로 접근
- GRUB 명령줄 부팅 인자:
  ```
  linux /install/vmlinuz auto=true priority=critical url=http://10.0.2.2:8000/preseed.cfg \
    locale=en_US.UTF-8 keyboard-configuration/layoutcode=us hostname=pf16-worker1 domain=local \
    interface=auto console=ttyAMA0,115200 ---
  initrd /install/initrd.gz
  boot
  ```
- preseed 핵심: 미러 `ports.ubuntu.com/ubuntu-ports`(xenial 아직 제공 [사실]), 자동 파티션(atomic), 사용자 `gihyeon`, `openssh-server`, 설치 후 커널 옵션 `console=ttyAMA0,115200`, late_command로 SSH 공개키 + `NOPASSWD` sudo
- NIC는 virtio로 변경(03의 e1000은 인식 줄이 없었음) → 네트워크 정상
- 콘솔 로그인 비밀번호는 맥 `~/VirtualBox VMs/u1604-test/credentials.txt`(권한 600)에만 보관
- 결과 [사실]: `Ubuntu 16.04.7 LTS`, `4.4.0-186-generic`, aarch64, SSH 키 로그인·sudo 정상, **cgroup v1 기본**(`/sys/fs/cgroup`이 tmpfs + memory/cpu/cpuset … 디렉터리)

## 2. Docker 1.12.1 — 논문과 같은 버전 ✅

- 16.04 저장소에는 `1.10.3`(출시판)과 `18.09.7`만 있음 [사실]
- **Launchpad 보관소에 2016-10-14 배포된 xenial arm64 빌드가 남아 있음** [사실] → 같은 날 배포된 세트로 설치
  ```bash
  wget https://launchpad.net/ubuntu/+archive/primary/+files/docker.io_1.12.1-0ubuntu13~16.04.1_arm64.deb
  wget https://launchpad.net/ubuntu/+archive/primary/+files/containerd_0.2.3-0ubuntu1~16.04_arm64.deb
  wget https://launchpad.net/ubuntu/+archive/primary/+files/runc_1.0.0~rc1-0ubuntu1~16.04_arm64.deb
  sudo apt-get install -y ./containerd_*.deb ./runc_*.deb ./docker.io_*.deb
  sudo apt-mark hold docker.io containerd runc   # 자동 업그레이드 방지
  ```
- `docker info` [사실]: Server Version 1.12.1, Cgroup Driver **cgroupfs**, Storage Driver aufs
- containerd/runc를 최신(1.2.6 / rc7)으로 쓰지 않은 이유: Docker 1.12는 containerd 0.2.x API용 [추측]

### Docker Hub 이미지는 못 받음 → 로컬 이미지로 우회

- `docker pull busybox` → `missing signature key` [사실] — 2016년 클라이언트가 현재 Docker Hub 형식을 처리 못함 [추측]
- 우회: Ubuntu 16.04 ARM64 기본 파일시스템을 직접 import
  ```bash
  wget https://cdimage.ubuntu.com/ubuntu-base/releases/16.04/release/ubuntu-base-16.04.6-base-arm64.tar.gz
  sudo docker import ubuntu-base-16.04.6-base-arm64.tar.gz local/ubuntu:16.04
  ```
- task 이미지는 `local/ubuntu:16.04` 위에 JDK 8 + Hadoop 2.7.3으로 제작 예정

### 쉽게 설명 — task용 Docker 이미지 문제

**1) 이미지가 왜 필요한가**

- Docker 이미지 = 컨테이너를 만드는 **틀**(OS 파일 + Java·Hadoop 같은 프로그램이 미리 설치된 묶음). 보통 Docker Hub에서 `docker pull`로 받음
- 원 Pufferfish는 YARN task(map/reduce, Spark executor)를 **Docker 컨테이너 안에서** 실행 → 컨테이너마다 cgroup으로 메모리 puff/reclaim, CPU 1% suspend 가능
- 컨테이너 안에서 task가 돌려면 그 안에 Java·Hadoop이 있어야 함 → 논문은 Docker Hub의 `sequenceiq/hadoop-docker`를 사용 (p.265)

```
[YARN NodeManager (원 저자 수정본)]
      │ docker run <이미지> ...      ← DockerContainerExecutor
      ▼
[컨테이너: Java + Hadoop]  ← map/reduce task 실행
      ▲
  cgroup으로 메모리 조절 / CPU 1% suspend (Pufferfish) — 컨테이너 "바깥"에서 일어남
```

- 이미지 이름은 설정값 `yarn.nodemanager.docker-container-executor.image-name` [사실: `YarnConfiguration.java:1006`], 원 코드 기본값은 `sequenceiq/hadoop-docker:2.4.0` [사실: `YarnConfiguration.java:1009`] — 논문은 태그 미명시

**2) 원래 이미지를 못 쓰는 이유**

- **A. CPU 종류가 다름** [사실]: `sequenceiq/hadoop-docker`는 x86(amd64) 전용, 마지막 갱신 2015-12-13. 우리 VM은 ARM → 실행 불가
- **B. Docker 1.12.1이 너무 오래됨**: `docker pull busybox`조차 `missing signature key`로 실패 [사실]. Docker Hub가 그사이 이미지 포맷·서명 방식을 바꿨기 때문 [추측]. 비유: 2016년 폰으로 지금 앱스토어 접속
- ⇒ 받을 수도 없고, 받아도 실행이 안 됨

**3) 원래 이미지 구성** (공개 Dockerfile, master 기준) [사실]

| 항목 | 내용 |
|---|---|
| 베이스 | `sequenceiq/pam:centos-6.5` (CentOS 6.5) — CentOS 6은 ARM64판 없음 |
| JDK | Oracle JDK 7u71 (x64 RPM) |
| Hadoop | 2.7.1 (`/usr/local/hadoop`) + x64 네이티브 라이브러리 |
| 기타 | 비밀번호 없는 SSH(포트 2122), 의사 분산 모드 설정, `/etc/bootstrap.sh` |

- 원 코드 기본 태그 `2.4.0`은 Hadoop 2.4.0이 들어 있는 이전 판 [추측: 태그 이름 기준]

**4) 해결 — 직접 만든다**

1. Ubuntu 공식 **16.04 ARM64 최소 파일시스템**(39MB) → `docker import` → `local/ubuntu:16.04` ✅ 완료
2. 그 위에 JDK 8 + Hadoop 2.7.3 설치 → `sequenceiq/hadoop-docker`와 **같은 역할** 이미지 (예정)
3. 설정에서 `docker-container-executor.image-name`을 이 이미지로 지정

**5) 결과에 미치는 영향**

- 다른 점: 컨테이너 **안쪽** OS(CentOS 6.5 → Ubuntu 16.04), JDK(7u71 → 8), 안쪽 Hadoop(2.4.0 또는 2.7.1 → 2.7.3)
- Pufferfish 동작(OCM 감지·suspend·puff·reclaim)은 컨테이너 **바깥**(NodeManager + cgroup)에서 일어나므로 영향 작음 [추측]
- 단, task가 컨테이너 안의 Hadoop jar로 실행될 수 있어 **task 쪽 Hadoop 버전**은 달라짐 [추측: DCE 실행 방식 확인 필요] → 2.7.3으로 통일하는 편이 오히려 일관됨

## 3. 원 코드가 쓰는 cgroup·Docker 기능 확인 ✅

`docker run -d --memory=256m --memory-swap -1 --oom-kill-disable` 컨테이너로 확인 [사실]:

| 원 코드가 쓰는 것 | 결과 |
|---|---|
| `/sys/fs/cgroup/memory/docker/<id>/` 경로 (`ContainerImpl.java:764`) | ✅ 존재 |
| `/sys/fs/cgroup/cpu/docker/<id>/`, `/cpuset/docker/<id>/` | ✅ 존재 |
| `memory.limit_in_bytes` | ✅ 268435456 (256MB) |
| `--oom-kill-disable` | ✅ `oom_kill_disable 1` |
| suspend: `docker update --cpu-quota 1000 --cpuset-cpus 0` | ✅ `cpu.cfs_quota_us=1000`, `cpuset.cpus=0` |
| puff: `docker update --memory 512m` | ✅ `536870912` |
| swap 사용량 (`memory.stat`의 swap, `memory.memsw.*`) | ❌ → ✅ 커널 옵션 `swapaccount=1` 추가 후 생성 |

- **swap accounting**: 16.04 커널 4.4는 기본값이 꺼져 있음 [사실] → `/etc/default/grub`의 `GRUB_CMDLINE_LINUX`에 `swapaccount=1` 추가 → `update-grub` → 재부팅. 원 코드 OCM 판정(`memory+swap > limit`)에 필수

## 4. 빌드 도구

| 항목 | 버전 | 비고 |
|---|---|---|
| JDK | OpenJDK 1.8.0_292 (xenial-updates) | 2016년 당시는 8u1xx [추측]. 같은 JDK 8 계열 |
| Maven | 3.3.9 (xenial) | |
| protoc | 2.5.0 (ARM64 패치 빌드) | 방법은 [01-legacy-build.md](01-legacy-build.md) §3과 동일 |

## 5. 원 코드 빌드 (진행 중)

- 24.04에서는 dist 단계가 테스트 jar 문제로 실패했음 → 두 단계로 나눔
  1. `mvn install -DskipTests -Dmaven.test.skip=true` — 테스트 컴파일 없이 전 모듈 설치 (원 저자 테스트 코드 `MockNodes.java` 컴파일 오류 회피)
  2. `mvn package -Pdist -Dtar -DskipTests -rf :hadoop-mapreduce-client-jobclient` — MapReduce부터는 테스트 jar까지 만들어 dist 묶음 생성
- 결과 [사실]: 1단계 BUILD SUCCESS(9분, YARN jar 확보) / 2단계 dist는 실패(`hadoop-yarn-server-tests` tests jar 없음, `dist-layout-stitching.sh` 실패)
- → 공식 2.7.3 바이너리 + YARN jar 교체로 전환: [05-hadoop-dist-task-image.md](05-hadoop-dist-task-image.md)

## 남은 단계

1. ~~빌드 결과 확인 → `hadoop-2.7.3.tar.gz`(원 저자 수정본) 확보~~ ✅ 05
2. ~~task용 Docker 이미지 제작 (`local/ubuntu:16.04` + JDK 8 + Hadoop 2.7.3)~~ ✅ 05
3. 단일 노드로 원 구현 YARN 기동(`DockerContainerExecutor`) → pi 예제
4. OCM/suspend/puff 로그 확인 (실험은 시험 이후)
5. 확인되면 VM 복제로 3대 구성
