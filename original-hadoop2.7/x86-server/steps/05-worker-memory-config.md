# 05. 워커 메모리 설정 적용 (2026-11-01)

## 1. 목적

- `setup/conf/yarn-site.xml`이 맥 VM(3GB) 값 그대로였음 → YARN이 31GB 워커를 2GB로만 씀
- [01](01-cluster-spec-and-scaling.md) §3 초기값을 실제 설정에 반영

## 2. 설계

| 설정 | 이전 | 적용 | 근거 |
|---|---|---|---|
| `yarn.nodemanager.resource.memory-mb` | 2048 (맥 VM) | **28672** | 01 §3 (논문 120GB의 1/4 = 30GB에서 4GB 여유) |
| `yarn.scheduler.maximum-allocation-mb` | 기본 8192 | **28672** | 컨테이너 하나가 노드 전체까지 요청할 수 있게. 07 예비 실험(16GB 힙) 대비 [우리] |
| `yarn.nodemanager.resource.cpu-vcores` | 기본 8 | 8 (명시만) | VM vCPU 8 |
| `yarn.nodemanager.balloon.jvm-mb` (MAX_HEAP) | 원 코드 기본 65536 | **16384** | 01 §3 (논문 64GB [p.265]의 1/4). 설정 이름 `YarnConfiguration.java:848` |
| `balloon.ratio/stop/reclaim/memory-mb` | 원 코드 기본 | 그대로 | 01 §4 |
| `yarn.scheduler.minimum-allocation-mb` | 256 | 그대로 | 논문에 값 없음 |

- conf는 맥·x86 공통 → 값을 `@YARN_MB@`·`@JVM_MB@`로 두고 `build-image.sh`가 채움
  - 기본값 = x86 워커 (28672 / 16384)
  - 맥 VM: `YARN_MB=2048 JVM_MB=65536 bash build-image.sh jdk7`

## 3. 실행 방법 (VM)

```bash
scp -r ~/pufferfish-memory-lab/original-hadoop2.7/setup labvm:legacy/   # 맥에서
bash ~/legacy/setup/hadoop.sh stop
bash ~/legacy/setup/build-image.sh
grep -A1 -E "resource.memory-mb|maximum-allocation-mb|cpu-vcores|balloon.jvm-mb" /opt/hadoop-2.7.3/etc/hadoop/yarn-site.xml
bash ~/legacy/setup/hadoop.sh start
```

## 4. 확인 포인트

- `hadoop.sh start` 끝의 `yarn node -list`에 노드가 RUNNING으로 보이는지
- RM REST로 자원 확인: `curl -s http://ubuntu:8088/ws/v1/cluster/metrics` (RM은 `ubuntu`=127.0.1.1에 열림 → `localhost`로는 응답 없음) → `totalMB` 28672, `totalVirtualCores` 8
- NM 로그에 jvm-mb 값이 찍히는지: `grep -i "balloon\|jvm" /opt/hadoop-2.7.3/logs/yarn-*-nodemanager-*.log | head`

## 5. 검증 결과

VM 적용 완료 (2026-11-01)

| 확인 | 결과 |
|---|---|
| 생성된 `yarn-site.xml` | memory-mb 28672, cpu-vcores 8, maximum-allocation-mb 28672, balloon.jvm-mb 16384 |
| 데몬 | NameNode·DataNode·ResourceManager·NodeManager, 노드 `ubuntu` RUNNING |
| RM metrics | `totalMB` 28672, `totalVirtualCores` 8, `activeNodes` 1 |
| `yarn node -status` | Memory-Capacity 28672MB, CPU-Capacity 8 vcores |

- `balloon.jvm-mb`가 실제로 쓰이는지는 Flex 컨테이너가 떠야 확인 가능 → 06에서 컨테이너 `-Xmx16384m` 확인
- `hadoop.sh stop` 때 NM이 5초 안에 안 꺼져 `kill -9`됨 (컨테이너 없을 때라 영향 없음). 반복되면 확인
