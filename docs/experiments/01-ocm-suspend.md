# 1차: OCM 감지 및 CPU 1% 제한

## 목적

메모리가 부족해 swap이 발생하는 컨테이너(OCM: On-Container Memory
pressure)를 감지하면, 컨테이너를 종료하지 않고 `docker update`로 CPU를
1%(코어 0번만)로 제한해 heartbeat만 유지시킨다. `docker pause`는 사용하지
않는다 — Pufferfish의 suspend는 완전 정지가 아니라 소량의 CPU를 남겨두는
방식이기 때문이다.

## 컨테이너 이미지 빌드 및 실행

```bash
cd workload-java
docker build -t pufferfish/workload-java:latest .

docker run -d --name pf-test \
  --memory=256m --memory-swap=768m \
  -e JAVA_OPTS="-Xmx700m" \
  pufferfish/workload-java:latest
```

- RAM 한도는 256MiB(`--memory`), RAM+swap 합산 한도는 768MiB(`--memory-swap`)로
  설정한다. 즉 swap 여유는 512MiB다. 768MiB는 논문의 값이 아니라 이 워크로드가
  OOM-kill 전에 OCM으로 감지될 수 있도록 잡은 PoC용 헤드룸이며, 이후
  unrestricted 실행에서 실제 peak 사용량을 측정해 조정할 수 있다.
- `--memory-swappiness`는 사용하지 않는다. cgroup v2에서는 이 옵션 대신 실제
  swap 가능 여부(`memory.swap.max`)와 `memory.stat`으로 상태를 직접 확인한다.
- `JAVA_OPTS`로 JVM 플래그를 주입할 수 있다. 컨테이너 메모리 한도(256MiB) 내에서
  JVM이 기본으로 잡는 최대 힙은 그보다 작아서, 힙이 cgroup 메모리 한도를
  실제로 넘어서게 하려면 `-Xmx`를 명시적으로 크게 잡아야 한다.

## controller 명령어

```bash
cd controller
python3 cgroup_precheck.py pf-test     # 사전 점검
python3 swap_preflight.py pf-test      # swap 발생 여부 dry-run
python3 container_monitor.py pf-test   # OCM 감지 + 자동 suspend + 자동 puff

# 수동 suspend/resume
python3 suspend_manager.py suspend pf-test
python3 suspend_manager.py resume pf-test
```

## 직접 실습해보기 (단계별)

터미널 창 2개를 띄워두고 따라 하면 편하다. 창 A에서 컨테이너 실행과 모니터를,
창 B에서 결과 확인을 한다.

### 창 A

```bash
# 0) 저장소 루트에서 시작
cd ~/pufferfish-memory-lab

# 1) 이미지 빌드
cd workload-java
docker build -t pufferfish/workload-java:latest .
cd ..

# 2) 컨테이너 실행 (이미 떠 있다면 먼저 정리)
docker rm -f pf-test 2>/dev/null
docker run -d --name pf-test \
  --memory=256m --memory-swap=768m \
  -e CHUNK_SIZE_MB=32 -e INTERVAL_SECONDS=2 -e MAX_ALLOCATION_MB=512 \
  -e JAVA_OPTS="-Xmx700m" \
  pufferfish/workload-java:latest

# 3) 로그로 워크로드가 정상 동작하는지 잠깐 확인 (Ctrl+C로 스트리밍만 중단, 컨테이너는 계속 실행됨)
docker logs -f pf-test

# 4) 반드시 controller 디렉터리로 이동한 뒤 모니터 실행
cd controller
python3 container_monitor.py pf-test --interval 0.5
```

`container_monitor.py`를 저장소 루트에서 그대로 실행하면
`can't open file '.../container_monitor.py': No such file or directory`
에러가 난다 — 흔한 실수이니 4번 단계에서 `cd controller`를 빼먹지 않는다.

> **팁: 2)와 4) 사이에 시간이 걸리면 증가 과정을 놓친다**
> `CHUNK_SIZE_MB=32`, `INTERVAL_SECONDS=2` 기준으로 컨테이너 실행 후 약
> 16초(8번째 할당) 만에 `memory.current`가 이미 256MiB 근처에 도달한다.
> 컨테이너를 띄우고 모니터를 붙이는 사이에 시간이 걸리면, 모니터 첫
> 스냅샷부터 `current`가 이미 255MiB 근처로 찍혀서 0MiB부터 올라가는
> 과정을 못 보게 된다. `&&`로 묶어 컨테이너 실행 직후 곧바로 모니터를
> 붙이면 이를 피할 수 있다.
> ```bash
> docker rm -f pf-test 2>/dev/null
> docker run -d --name pf-test \
>   --memory=256m --memory-swap=768m \
>   -e CHUNK_SIZE_MB=32 -e INTERVAL_SECONDS=2 -e MAX_ALLOCATION_MB=512 \
>   -e JAVA_OPTS="-Xmx700m" \
>   pufferfish/workload-java:latest \
> && cd controller && python3 container_monitor.py pf-test --interval 0.5
> ```

모니터 로그에 다음 순서가 찍히면 정상 동작이다 (32MiB씩 쌓이다 256MiB를
넘는 시점, 대략 16번째 할당 전후에서 발생).

```
[container_monitor] pf-test: OCM 감지 (method=swap_current_delta_fallback, ...)
[suspend_manager] pf-test: 원래 CPU 설정 저장 ...
[suspend_manager] pf-test: suspend 적용 (--cpus 0.01 --cpuset-cpus 0)
[suspend_manager] pf-test: cgroup cpu.max='1000 100000' cpuset.cpus='0'
```

이미 `MAX_ALLOCATION_MB`까지 다 채우고 "최대 누적 할당량에 도달" 상태인
컨테이너로 모니터를 새로 실행하면, swap이 이미 정체 상태라 새로운 swap
activity가 안 잡혀 OCM이 감지되지 않을 수 있다 — 그럴 땐 컨테이너를 2번
단계로 다시 띄운다.

### 창 B (모니터는 창 A에서 계속 켜둔 채로)

```bash
# CPU 실사용률 확인 — suspend 이후 ~1%대로 떨어져야 한다
docker stats pf-test --no-stream

# cgroup 파일 직접 확인 (docker inspect의 CpuQuota/CpusetCpus는 부정확할 수 있어 신뢰하지 않는다)
PID=$(docker inspect --format '{{.State.Pid}}' pf-test)
CG=$(sed -n 's/^0:://p' /proc/$PID/cgroup)
cat /sys/fs/cgroup$CG/cpu.max      # 1000 100000 => 1%
cat /sys/fs/cgroup$CG/cpuset.cpus  # 0 => 0번 코어만
```

### 정리

```bash
docker rm -f pf-test
rm -f controller/state/*.json
```

## OCM 판정 로직

`memory.current + memory.swap.current > memory.max` 이면서
(swapping activity가 있거나, swap이 이미 포화 상태일 때) OCM으로 판정한다.
swapping activity는 우선 `memory.stat`의 `pswpin`/`pswpout` delta로 판단하되,
이 커널 버전처럼 해당 키가 없는 cgroup v2 환경에서는 `memory.swap.current`의
delta > 0을 fallback으로 사용한다(이 프로젝트의 실험 환경, 커널 6.8에서 실제로
확인됨). `workingset_refault_anon`은 판정에 쓰지 않고 참고용으로만 로그에
남긴다.

> **업데이트 (3차 다중 컨테이너 실습 중 발견)**: `memory.swap.current`가 이미
> `memory.swap.max`에 도달해 더 늘어날 수 없는 상태가 되면 delta가 영구히
> 0이 되어 "swapping activity 없음"으로 오판됐다. 이 경우 실제로는 가장 위험한
> 상황(swap도 꽉 찼는데 `memory.current`만 한도로 계속 올라가는 중)인데도 OCM이
> 재감지되지 않아 puff 없이 그대로 OOM-kill당하는 게 실제로 관찰됐다. 그래서
> `swap_current >= swap_max × 0.95`(포화 상태)도 OCM 조건에 OR로 추가했다
> (`container_monitor.py`의 `evaluate_ocm()`, `SWAP_SATURATION_RATIO=0.95`).
> 자세한 재현 과정은 [03-multi-container-reclaim.md](03-multi-container-reclaim.md)
> 참고.

## 검증 결과

`--memory=256m --memory-swap=768m -e JAVA_OPTS="-Xmx700m"`로
실행한 워크로드가 256MiB를 넘어서며 swap이 발생하고, `container_monitor.py`가
fallback 방식으로 OCM을 감지해 `suspend_manager.suspend()`를 호출, 실제
cgroup(`cpu.max`가 `1000 100000`, `cpuset.cpus`가 `0`)에 CPU 1% 제한이
적용되는 것을 확인했다. 제한 이후에도 컨테이너/JVM은 종료되지 않고 계속
동작하며(단, 진행 속도는 크게 느려짐), `resume()`은 저장해둔 원래 cgroup
상태(`cpu.max`, `cpuset.cpus`)로 정확히 복구한다.
