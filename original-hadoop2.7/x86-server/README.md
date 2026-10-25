# x86-server — 연구실 x86 VM (정식 실험)

> 2026-10-25 교수님이 할당 결정 (Ubuntu 16.04.7 server). 요청 사양: 최소 4 vCPU / 16GB / 100GB, 권장 8 / 32 / 200.
> 단계 기록은 이 폴더의 `steps/`에 번호로 남긴다.

## 수령 직후 확인

```bash
uname -r      # 4.4.x 인지 (16.04 기본 커널)
nproc         # 할당한 vCPU 수가 다 보이는지 (맥 VM은 1개만 보였음)
uname -m      # x86_64
```

## 환경 구성 (설치 스크립트, [../setup/](../setup/))

```bash
# 맥에서: setup 폴더 복사 (yarn-jars/는 git 미추적 — 로컬 사본 사용)
scp -r original-hadoop2.7/setup <user>@<vm>:legacy/
# VM에서
bash ~/legacy/setup/install-host.sh        # JDK 8, Docker 1.12.1, swapaccount=1, Hadoop 2.7.3 + YARN jar 교체
sudo reboot                                # swapaccount 적용 (스크립트가 필요할 때 안내)
bash ~/legacy/setup/prepare-base-image.sh  # local/centos:7, local/ubuntu:16.04 (Docker Hub 없이)
bash ~/legacy/setup/build-image.sh jdk7    # task 이미지 local/hadoop-docker:2.7.3-jdk7
bash ~/legacy/setup/hadoop.sh start        # HDFS/YARN 단일 노드
```

- 스크립트는 arm64·amd64를 자동 판별. amd64 다운로드 경로는 2026-10-25 전부 HTTP 200 확인
- 원 저자 YARN jar 13개는 Java 바이트코드(네이티브 코드 없음)라 맥 VM 빌드본을 그대로 씀 — `setup/yarn-jars.sha256`으로 검증

## 남은 결정

- task 이미지: 원 `sequenceiq/hadoop-docker:2.4.0`을 다른 PC에서 받아 `docker save`로 반입 vs CentOS 6.5 + JDK 7 직접 구성 (x86이라 둘 다 가능)
