# 10차: swap 여유(`SWAP_HEADROOM_MB`) 128 → 512

## 목적

`puff_manager.SWAP_HEADROOM_MB`를 128MiB에서 512MiB로 올린다. 이 값은
`docker update --memory-swap = --memory + SWAP_HEADROOM_MB` 형태로 컨테이너별
swap 상한(`memory.swap.max`)을 결정한다.

## 원인 — 128MiB가 만든 문제 3가지

### (1) 실수요를 잘랐다 (실측)

[04-swap-headroom-increase-experiment.md](../evidence/04-swap-headroom-increase-experiment.md)에서
상한만 512로 올려 같은 워크로드를 돌렸더니 swap이 **183~191MiB에서 안정화**됐고
두 컨테이너 다 생존했다. 즉 128MiB는 워크로드의 실제 수요보다 작았고, 넘치는
분량이 `memory.current`로 쌓여 OOM-kill로 이어졌다.

### (2) puff가 기동 시 설정을 도리어 **줄이고** 있었다 (코드 수준 사실)

실습 기동 명령은 `--memory=256m --memory-swap=768m`이므로 시작 시점의
`memory.swap.max`는 **512MiB**다. 그런데 첫 puff가
`docker update --memory 358m --memory-swap 486m`을 실행하면서 swap 상한이
**128MiB로 축소**된다([puff_manager.py](../../controller/puff_manager.py)의
`_apply_docker_memory_update`, 3차 로그 12번째 줄 `puff 적용 256MiB -> 358MiB`).

- 메모리 한도를 늘려주는 동작(puff)이 swap 한도는 1/4로 깎는, 의도치 않은 부작용
- 512로 맞추면 기동 설정과 puff 이후 설정이 **일치**한다

### (3) 포화 조건(`swap_saturated`)은 이 축소의 뒤처리였다

3차 원본 로그([03-swap-saturation-raw-monitor-2.log](../evidence/03-swap-saturation-raw-monitor-2.log),
422줄)를 다시 집계한 결과:

| 항목 | 값 |
|---|---:|
| `swap_saturated=True` 폴링 | 99 |
| 그중 `over_limit`까지 참이라 OCM으로 잡혔을 폴링 | 45 |
| `over_limit AND saturated` 최초 성립 | 375번째 줄 (`current=855.7MiB`) |
| `oom_kill=1` 최초 | 417번째 줄 |
| → 확보 가능했던 경고 시간 | 42폴링 × 0.5s ≈ **21초** |

한편 512로 올려 돌린 로그
([04-swap-headroom-512-pf-swap-1.log](../evidence/04-swap-headroom-512-pf-swap-1.log), 882줄)에서는
`swap_saturated=True`가 **0줄**이고 OCM 감지 5회가 전부 `delta > 0`로 잡혔다.
즉 상한이 충분하면 포화 조건은 발화 자체를 하지 않는다.

## 귀속 주의 — 512는 논문 값이 아니다

| 출처 | swap 설정 |
|---|---|
| 논문 본문 | **구체적 수치 미명시** |
| 원 저자 공개 구현 | 최초 `--memory-swap -1`(호스트 범위 내 무제한), 갱신 후 `memory + 131072`MiB ≈ 128GiB |
| 이 프로젝트 (이전) | 128MiB 고정 |
| 이 프로젝트 (10차) | **512MiB 고정 — 여전히 이 프로젝트의 선택** |

"논문이 swap을 크게 잡았다"고 쓰면 안 된다. 근거는 **원 공개 구현**이며,
512는 그 무제한 정책과 128MiB 사이에서 이 VM 규모에 맞춰 고른 값이다
([pufferfish-architecture.md](../pufferfish-architecture.md) §2.5).

## 호스트 안전성 계산

현재 VM: RAM 3899MiB, swap 3899MiB(`/swap.img`).

| 항목 | 값 |
|---|---:|
| puff 천장 (`HOST_STOP_RATIO=0.8`) | 약 3119MiB |
| 컨테이너 3대 기준 swap 최대 총량 | 3 × 512 = 1536MiB |
| 호스트 swap 총량 대비 | 1536 / 3899 = **39%** |

3대 구성(03/05/09차와 동일)에서는 여유가 있다. 다만 컨테이너 수가 7대를
넘으면 호스트 swap을 다 쓰게 되므로, 대수를 늘리는 실험에서는 이 계산을
다시 해야 한다.

## 변경 내용

- [controller/puff_manager.py](../../controller/puff_manager.py) —
  `SWAP_HEADROOM_MB = 128` → `512` (변경 사유를 주석으로 남김)
- 이 상수를 참조하는 [controller/admission.py](../../controller/admission.py)의
  신규 컨테이너 기동 경로도 자동으로 같은 값을 쓴다 (코드 변경 없음)

## 실행 방법 (재검증)

```bash
cd controller

docker run -d --name pf-test-1 --memory=256m --memory-swap=768m \
  -e CHUNK_SIZE_MB=8 -e INTERVAL_SECONDS=2 -e MAX_ALLOCATION_MB=1024 \
  -e JAVA_OPTS="-Xmx1200m" pufferfish/workload-java:latest
# pf-test-2, pf-test-3 동일하게 5초 간격으로 기동

python3 container_monitor.py pf-test-1 --interval 0.5 > monitor-1.log 2>&1 &
python3 container_monitor.py pf-test-2 --interval 0.5 > monitor-2.log 2>&1 &
python3 container_monitor.py pf-test-3 --interval 0.5 > monitor-3.log 2>&1 &

# puff 직후 swap 상한이 유지되는지 확인
docker inspect pf-test-1 --format 'mem={{.HostConfig.Memory}} swap={{.HostConfig.MemorySwap}}'
```

## 확인 포인트

- [x] 첫 puff 이후에도 `memory.swap.max`가 512MiB로 유지되는가 (128로 줄지 않는가)
- [x] swap 사용량이 128MiB를 넘어가는가
- [x] `swap_saturated=True`가 한 번이라도 찍히는가 (예상: 0회)
- [x] `memory.events`의 `oom_kill`이 0으로 유지되는가
- [x] 컨테이너 swap 합계가 상한 총량(3 × 512 = 1536MiB)을 넘지 않는가

## `swap_saturated` 조건은 어떻게 할 것인가

**지금은 지우지 않는다.** 근거:

- 512 구성에서는 발화하지 않으므로 **판정 결과를 바꾸지 않는다**(무해)
- 상한을 다시 줄이거나 워크로드가 커지는 실험에서는 다시 유일한 신호가 된다
- 대신 확인 포인트에 "0회"를 넣어, 이 조건이 dead code임을 **로그로 증명**한다

다만 3차 로그 분석에서 드러난 더 근본적인 문제는 따로 남는다: `swap_saturated`는
`over_limit`과 AND로 묶여 있어, 포화 99폴링 중 54폴링은 `over_limit=False`라
어차피 잡히지 않았다. swap이 상한에 고정되면 `current + swap > max`는 사실상
`current > max − swap상한`이 되어 **너무 늦게** 참이 된다. 이 구조는 별도
과제로 남긴다.

## 검증 결과

**검증 완료 (2026-09-21).** 위 절차대로 `pf-test-1/2/3`을 5초 간격으로 띄우고
각각 monitor를 붙여 워크로드가 1024MiB를 전부 할당할 때까지(약 13분) 돌렸다.
원본 로그: [10-swap-headroom-512-pf-test-1.log](../evidence/10-swap-headroom-512-pf-test-1.log),
[-2](../evidence/10-swap-headroom-512-pf-test-2.log),
[-3](../evidence/10-swap-headroom-512-pf-test-3.log).

### 1. swap 상한이 puff 이후에도 유지됐다 (핵심)

```
기동 직후 : memory.max=256MiB  memory.swap.max=512MiB
첫 puff 후 : memory.max=358MiB  memory.swap.max=512MiB   ← 이전 코드였다면 128MiB
최종      : memory.max=981MiB  memory.swap.max=512MiB
```

`puff 적용 256 → 358 → 501 → 701 → 981MiB`로 네 번 커지는 동안 swap 상한은
한 번도 줄지 않았다. 128MiB 시절의 "puff가 기동 설정을 깎는" 부작용이 사라졌다.

### 2. 3대 모두 생존 — OOM-kill 0

| 컨테이너 | 로그 줄 | OCM 감지 | puff | `swap_saturated=True` | swap 최대 | 최종 memory.max | OOMKilled |
|---|---:|---:|---:|---:|---:|---:|---|
| pf-test-1 | 1860 | 103 | 4 | **0** | 347.1MiB | 981MiB | false |
| pf-test-2 | 1708 | 45 | 5 | **0** | 385.9MiB | 1157MiB | false |
| pf-test-3 | 1901 | 110 | 4 | **0** | 325.5MiB | 981MiB | false |

세 컨테이너 모두 `누적 1024MiB` 할당을 끝내고 대기 상태로 살아남았다. 동일
구성의 3차 실습(상한 128MiB)에서는 `oom_kill=1`로 종료됐다.

### 3. `swap_saturated`는 예상대로 한 번도 발화하지 않았다

5469줄(3대 합계) 전체에서 0회. 512 구성에서 이 조건은 dead code이며, OCM 감지는
전부 `delta_swap_current > 0`로 이뤄졌다. 조건을 남겨둬도 판정 결과가 달라지지
않음을 로그로 확인했다.

### 4. 예상보다 swap 실수요가 컸다 (새로 알게 된 것)

04 실험(2대)에서는 183~191MiB였는데, 이번 3대 구성에서는 **317~386MiB**까지
올라갔다. puff로 `memory.max`가 981~1157MiB까지 커지면서 JVM이 실제로 더 많이
쓴 결과다. 즉 **swap 수요는 워크로드 고정값이 아니라 puff 결과에 따라 같이
커진다.** 512MiB는 이번 구성에서 상한에 닿지 않았지만(최대 386MiB, 여유 25%),
여기서 컨테이너를 더 키우면 다시 상한에 닿을 수 있다.

### 5. 호스트 압박은 실제로 커졌다 (trade-off 확인)

| 시점 | Mem used | Swap used | available |
|---|---:|---:|---:|
| 실험 전 | 1590MiB | 0MiB | 2309MiB |
| 최대 부하 | 3787MiB | 2110MiB | 112MiB |
| 컨테이너 제거 후 | 874MiB | 1049MiB | 3025MiB |

컨테이너 swap 합계는 1041MiB로 상한 총량(1536MiB) 안에 있었지만, 호스트 전체
swap 사용량은 2110MiB(총량의 54%)까지 올라갔다 — 컨테이너 외 프로세스도 함께
밀려난 결과다. `available`이 112MiB까지 떨어졌으므로, **컨테이너를 더 늘리는
실험에서는 호스트 여유부터 다시 계산해야 한다**. §2.5의 trade-off(컨테이너
생존성 ↔ 호스트 안전성)가 수치로 다시 확인된 셈이다.

### 6. 운영 메모: suspend된 컨테이너는 `docker rm -f`가 막힌다

실험 종료 후 `docker rm -f`가
`container ... is zombie and can not be killed`로 실패했다. CPU가 1%로 묶여 있어
컨테이너가 종료 신호를 처리하지 못하기 때문이다. **정리 전에
`python3 suspend_manager.py resume <이름>`을 먼저 실행**하면 정상적으로 제거된다.
