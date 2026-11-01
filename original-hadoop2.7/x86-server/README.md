# x86-server — 연구실 x86 VM (정식 실험)

> 2026-10-25 교수님이 할당 결정 (Ubuntu 16.04.7 server).
> 2026-10-26 사양 확정: master 4 vCPU / 8GB / 100GB, worker ×2 각 8 vCPU / 32GB / 200GB — 축소 근거·실험 초기안은 [steps/01](steps/01-cluster-spec-and-scaling.md)
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
python3 ~/legacy/setup/fetch-sequenceiq-image.py ~/legacy/dl/sequenceiq   # 원 task 이미지 (steps/03)
docker load -i ~/legacy/dl/sequenceiq/sequenceiq-hadoop-docker-2.4.0.tar
bash ~/legacy/setup/build-image.sh         # local/hadoop-docker:2.7.3-sequenceiq
bash ~/legacy/setup/hadoop.sh start        # HDFS/YARN 단일 노드
```

- 스크립트는 arm64·amd64를 자동 판별. amd64 다운로드 경로는 2026-10-25 전부 HTTP 200 확인
- 원 저자 YARN jar 13개는 Java 바이트코드(네이티브 코드 없음)라 맥 VM 빌드본을 그대로 씀 — `setup/yarn-jars.sha256`으로 검증

## 결정 사항

- task 이미지: 원 `sequenceiq/hadoop-docker:2.4.0` 반입 (A안) — [steps/03](steps/03-task-image-sequenceiq.md). JDK 7/8 비교는 하지 않음 (2026-11-01 결정, steps/03 §2) — `jdk7`·`jdk8` 변형은 arm-mac 기록용으로만 남김
- HiBench 6.0 — 논문·원 코드에 버전 없음, 원 저자 로그(2017-02) 시점 최신으로 선택 (2026-11-01) — [steps/07](steps/07-hibench.md)
- HiBench 실행 조건: executor 1개 · **1코어**(논문에 없음, "Spark 기본 설정" 문장 따름) · 1g, parallelism·driver 메모리는 Spark 기본값 (2026-11-01) — [steps/08](steps/08-hibench-config.md) §6 랩미팅 보고 항목
