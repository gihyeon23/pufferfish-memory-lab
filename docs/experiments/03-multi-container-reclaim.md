# 3차: 다중 컨테이너 puff/reclaim 실습

## 목적

`puff_manager.reclaim()`/`reclaim_host()`는 2차에서 CLI로 검증했지만, 컨테이너
하나만으로는 "여러 컨테이너 중 무엇을 줄일지 정한다"는 reclaim 본연의 목적이
드러나지 않는다. 여러 컨테이너를 동시에 puff시켜 호스트 예산
(`HOST_STOP_RATIO=0.8`)에 가깝게 채운 뒤, `reclaim_host`가 **가장 최근에
puff한 컨테이너부터** 순서대로 줄이는지 확인한다.

## 사전 확인: 호스트 예산 계산

```bash
cd ~/pufferfish-memory-lab/controller
python3 -c "from puff_manager import get_host_memory_total_mb; print(get_host_memory_total_mb(), 'MiB')"
```

`get_host_assigned_mb()`는 실제 호스트 메모리 사용량이 아니라 **떠 있는
컨테이너들의 `memory.max` 합**이다. 즉 이 실습에서 "호스트가 빠듯해진다"는
실제 RAM을 다 채운다는 뜻이 아니라, 컨테이너 한도 합이
`host_total × HOST_STOP_RATIO`에 가까워진다는 뜻이다.

## 1) 기존 정리

```bash
cd ~/pufferfish-memory-lab
docker rm -f pf-test pf-test-1 pf-test-2 pf-test-3 2>/dev/null
rm -f controller/state/*.json
```

## 2) 컨테이너 3개를 시차를 두고 실행

`MAX_ALLOCATION_MB`를 크게 잡아 계속 자라게 하고, `-Xmx`는 그보다 크게 준다.
5초 텀을 두는 이유는 `state/<container>_memory.json`의 mtime을 서로 다르게
만들어 `reclaim_host`의 "최근 puff 우선" 순서를 눈으로 확인하기 위함이다.

`CHUNK_SIZE_MB=8`을 쓴다 — 아래 "시행착오"에서 다루듯 `32`는 청크 버스트로
puff가 못 따라가 OOM-kill될 위험이 있다(2026-09-05 재현 테스트에서도
`32`로 돌렸다가 3개 다 죽는 것을 다시 확인했다). "검증 결과" 절의 로그는
`32`로도 우연히 성공한 기록이지만, 재현성 있게 돌리려면 `8`을 쓴다.

```bash
docker run -d --name pf-test-1 \
  --memory=256m --memory-swap=768m \
  -e CHUNK_SIZE_MB=8 -e INTERVAL_SECONDS=2 -e MAX_ALLOCATION_MB=1024 \
  -e JAVA_OPTS="-Xmx1200m" \
  pufferfish/workload-java:latest

sleep 5

docker run -d --name pf-test-2 \
  --memory=256m --memory-swap=768m \
  -e CHUNK_SIZE_MB=8 -e INTERVAL_SECONDS=2 -e MAX_ALLOCATION_MB=1024 \
  -e JAVA_OPTS="-Xmx1200m" \
  pufferfish/workload-java:latest

sleep 5

docker run -d --name pf-test-3 \
  --memory=256m --memory-swap=768m \
  -e CHUNK_SIZE_MB=8 -e INTERVAL_SECONDS=2 -e MAX_ALLOCATION_MB=1024 \
  -e JAVA_OPTS="-Xmx1200m" \
  pufferfish/workload-java:latest
```

## 3) 컨테이너마다 monitor를 백그라운드로 붙이기

```bash
cd controller
python3 container_monitor.py pf-test-1 --interval 0.5 > monitor-1.log 2>&1 &
python3 container_monitor.py pf-test-2 --interval 0.5 > monitor-2.log 2>&1 &
python3 container_monitor.py pf-test-3 --interval 0.5 > monitor-3.log 2>&1 &
```

## 4) 실시간으로 세 로그 동시에 보기

```bash
tail -f monitor-1.log monitor-2.log monitor-3.log
```

## 5) 호스트 예산 대비 진행 상황 수시 확인

```bash
python3 -c "from puff_manager import get_host_assigned_mb, get_host_memory_total_mb; a=get_host_assigned_mb(); t=get_host_memory_total_mb(); print(f'assigned={a}MiB budget={t*0.8:.0f}MiB total={t}MiB')"
```

`assigned`가 `budget`에 가까워지면 monitor 로그에 `호스트 여유 없음, puff
건너뜀`이 찍히기 시작한다 — 이 시점이 reclaim이 필요해지는 상황이다.

## 6) reclaim-host로 회수 확인

```bash
python3 puff_manager.py reclaim-host --target-free-mb 500
```

`state/*_memory.json`의 mtime이 가장 최근인 컨테이너(=가장 나중에 puff된
컨테이너)부터 원래 한도(floor)까지 순서대로 줄어드는지 로그로 확인한다.

## 확인 포인트

- [x] 컨테이너 3개 모두 OCM 감지 → puff 자동 적용 로그 확인
- [x] `assigned`가 budget(`host_total × 0.8`)에 근접하면 puff가 거부되는지 확인
- [ ] `reclaim-host` 호출 시 가장 최근 puff된 컨테이너부터 줄어드는지 확인 (아직 실습 안 함 — 아래 "다음에 할 일" 참고)
- [ ] floor(원래 한도) 아래로는 절대 안 내려가는지 확인 (위와 동일)

## 시행착오: 발견한 문제 두 가지

이 실습을 실제로 돌리면서 코드 버그를 두 개 발견해 고쳤다. 둘 다 "컨테이너가
왜 죽었는가"를 로그로 역추적하는 과정에서 나왔다.

### 문제 1 — 청크 버스트 레이스 컨디션

`CHUNK_SIZE_MB=32`로 처음 돌렸을 때, 3개 중 2개(`pf-test-1`, `pf-test-2`)가
실행 65초 만에 `OOMKilled=true, ExitCode=137`로 죽고 `pf-test-3` 혼자
살아남았다. 원인은 [02-puff-reclaim-single.md](02-puff-reclaim-single.md#자동-puff-검증-container_monitorpy-연동)에
정리한 것과 동일 — `Arrays.fill()`이 32MiB를 한 번에 터치하면서 128MiB
swap 헤드룸을 폴링 주기(500ms)보다 빠르게 넘겨버렸다. `CHUNK_SIZE_MB=8`로
줄여서 재시도했더니 이 문제는 사라졌다(3개 다 첫 ramp‑up을 넘김).

### 문제 2 — OCM 판정 로직의 blind spot (swap 포화)

청크를 줄인 뒤에도 이번엔 3개가 **비슷한 시점에 동시에** 죽었다. 로그를 보면
공통적으로:

```
current=698.4MiB swap=127.9MiB max=701.0MiB delta_swap_current=0
current=701.0MiB swap=127.9MiB max=701.0MiB
current=700.7MiB swap=127.8MiB ... events: oom=1, oom_kill=1
```

`swap.current`가 `swap.max`(128MiB, `SWAP_HEADROOM_MB`)에 이미 도달해 더
늘어날 수 없는 상태가 되면 `delta_swap_current`가 영구히 0이 된다. 당시
OCM 판정(`over_limit AND swap_activity`)은 이걸 "swap 활동 없음 = 안전"으로
오판해서, `current`만 조용히 `memory.max`까지 올라가다가 puff 한 번 못
받아보고 그대로 OOM-kill당했다.

`container_monitor.py`의 `evaluate_ocm()`을 수정해 `swap_current >=
swap_max × 0.95`(포화 상태)도 OR 조건으로 추가했다(`SWAP_SATURATION_RATIO`).
자세한 내용은 [01-ocm-suspend.md의 OCM 판정 로직](01-ocm-suspend.md#ocm-판정-로직)
참고.

## 검증 결과 (수정 후 재실행)

`CHUNK_SIZE_MB=32, INTERVAL_SECONDS=2, MAX_ALLOCATION_MB=1024`로 3개
컨테이너를 다시 5초 간격 실행했다. 이번엔 순수하게 **호스트 예산 경쟁** 때문에
한 개가 죽었다 — 감지 로직 버그가 아니라 이 실습이 원래 확인하려던 상황
자체가 재현됐다.

> ⚠️ 이 절의 로그는 `CHUNK_SIZE_MB=32`로 성공한 기록이지만, 2026-09-05에
> 5차(admission) 실습을 위해 같은 값으로 다시 돌렸을 때는 3개 다 청크
> 버스트로 죽었다 — `32`는 타이밍에 따라 성공하기도 실패하기도 하는
> **재현성 없는 값**이다. 위 2)번 실행 명령은 `8`로 갱신해뒀다.

- `pf-test-1`, `pf-test-3`는 puff를 여러 차례 반복하며 계속 살아있었다:
  ```
  pf-test-1: 256 → 358 → 501 → 701 → 981 → 1157 → 1619 MiB
  pf-test-3: 256 → 358 → 501 → 701 → 981 → 1373 MiB
  ```
  `981 → 1157`처럼 정확히 40%가 아닌 puff가 나온 건, `puff()`가
  `step = min(현재 × 40%, 남은 호스트 여유)`로 계산하기 때문 —
  ([puff_manager.py:135](../../controller/puff_manager.py#L135)) 여유가
  빠듯해지면 40%를 다 못 채우고 남은 만큼만 부분적으로 늘어난다.
- `pf-test-2`는 OCM을 정상적으로 재감지했다(`swap_saturated=True`로,
  즉 수정한 로직이 실제로 작동함):
  ```
  [container_monitor] pf-test-2: OCM 감지 (swap_saturated=True)
  [puff_manager] pf-test-2: 호스트 여유 없음 (assigned=3119MiB budget=3119MiB), puff 건너뜀
  ```
  세 컨테이너의 `memory.max` 합이 호스트 예산(`3119MiB = 3899MiB × 0.8`)에
  정확히 도달해 `puff()`가 거부됐고, 몇 초 뒤 `pf-test-2`는 swap도 이미
  포화 상태라 도망갈 곳이 없어 `OOMKilled=true, ExitCode=137`로 죽었다.

**결론**: OCM 감지·puff 자체는 의도대로 동작했다. 문제는 **호스트 예산이
꽉 찼을 때 아무도 자동으로 reclaim을 안 해준다는 것**이다. `puff()`가
거부되는 걸 감지한 시점에 다른(예: 가장 최근에 puff된) 컨테이너를 자동으로
reclaim해줬다면 `pf-test-2`는 살 수 있었을 것이다. 이게 지난 대화에서 얘기한
"호스트 레벨 reclaim 데몬"이 필요한 이유를 실제 장애로 보여준 사례다.

## 다음에 할 일

- [ ] 위 시나리오를 살아남은 두 컨테이너 상태에서 `reclaim-host --target-free-mb`로
      수동 회수해보고, 가장 최근 puff된 컨테이너부터 줄어드는지 + floor 아래로
      안 내려가는지 확인
- [ ] `puff()`가 "호스트 여유 없음"으로 거부되는 순간을 감지해 자동으로
      `reclaim_host()`를 호출하는 호스트 레벨 데몬 설계·구현 (지난 대화에서
      논의한 NodeManager 레벨 에이전트 개념)

## 정리

```bash
docker rm -f pf-test-1 pf-test-2 pf-test-3
kill %1 %2 %3 2>/dev/null
rm -f controller/state/*.json controller/monitor-*.log
```
