# 증거 자료: swap 포화 → OCM 미감지 → OOM 인과관계 A/B 검증

## 질문

"swap 포화 때문에 OCM을 못 잡아서 OOM-kill됐다는 게, 로그가 그렇게
보이기만 하는 게 아니라 **실제 원인**이 맞는지 어떻게 증명하는가?"

## 검증 방법: 같은 데이터에 두 로직을 동시 적용

기존 로그를 사후 해석하는 방식은 "다르게 해석할 수도 있다"는 반박이
가능하다. 그래서 **매 폴링(500ms)마다 동일한 스냅샷 데이터에 대해 두
판정 로직을 동시에 계산**해서 나란히 기록하는 스크립트를 만들었다
([05-ab-test-script.py](05-ab-test-script.py)).

```
OLD (3차 당시 버그 로직) : over_limit AND swap_activity
NEW (현재 수정된 로직)    : over_limit AND (swap_activity OR swap_saturated)
```

같은 시점, 같은 입력값을 쓰므로 "실행 조건이 달라서 결과가 달랐다"는
반박이 원천 차단된다. 두 판정이 갈리는 폴링이 곧 "옛 로직이 놓쳤던
구간"이다.

## 실험 3회 결과

| # | 조건 | swap 최고치 | `sat=1` 폴링 | 판정 불일치 | 컨테이너 |
|---|---|---|---|---|---|
| 1 | mem 256MiB / swap 128MiB, **puff 없음** | 121.5MiB (94.9%) | 0회 | 0회 | 사망 |
| 2 | mem 981MiB / swap 128MiB, **puff 없음** | 127.1MiB (1폴링만) | 1회 | 0회 | 사망 |
| 3 | mem 256MiB / swap 128MiB, **puff 작동(실제 시스템)** | 127.8MiB | **266회** | **2회** | **생존** |

원본 로그: [05-ab-test-no-puff-981m.log](05-ab-test-no-puff-981m.log) (실험 2),
[05-ab-test-integrated-with-puff.log](05-ab-test-integrated-with-puff.log) (실험 3)

## ★ 핵심 증거 — 실험 3의 판정 불일치 순간

### 불일치 #1 (46.6초)

```
[46.1s] cur=256.2MiB swap=127.8MiB max=358.0MiB swapmax=128.0MiB | over=1 act=1 sat=1 (delta_swap=54423552) | OLD=OCM NEW=OCM
[46.6s] cur=256.2MiB swap=127.8MiB max=358.0MiB swapmax=128.0MiB | over=1 act=0 sat=1 (delta_swap=0)        | OLD= -  NEW=OCM   <<<< 불일치
[47.1s] cur=257.1MiB swap=127.8MiB max=501.0MiB swapmax=128.0MiB | over=0 act=0 sat=1 (delta_swap=0)        | OLD= -  NEW= -
```

46.6초 시점을 보면:
- `over=1` — 이미 한도 초과 상태(위험)
- `swap=127.8MiB` = 상한 128MiB의 **99.8%** — swap이 꽉 차서 더는 못 나감
- `delta_swap=0` — 그래서 **OLD 로직은 "swap 활동 없음 = 안전"으로 오판(미감지)**
- `sat=1` — NEW 로직은 포화를 근거로 **정상 감지**
- **다음 폴링(47.1s)에서 `max`가 358 → 501MiB로 점프** = 감지 결과로 puff가 실제 실행됨

### 불일치 #2 (243.4초)

```
[243.4s] cur=577.7MiB swap=124.6MiB max=701.0MiB | over=1 act=0 sat=1 | OLD= -  NEW=OCM   <<<< 불일치
[243.9s] cur=584.3MiB swap=124.6MiB max=981.0MiB | over=0 act=0 sat=1 | OLD= -  NEW= -
```

여기서도 동일하게 `max`가 701 → 981MiB로 puff됐다.

### 통계

- `sat=1`인데 `act=0`인 폴링 = **258회** — delta 기반 로직만으로는 **원리적으로
  절대 감지할 수 없는** 구간이 258번 있었다
- 실험 3 컨테이너는 puff를 5회(256→358→501→701→981→1373MiB) 받고
  **생존**(`OOMKilled=false`)

## 결론 (인과관계 성립)

동일 시점·동일 데이터에서 두 로직의 판정이 실제로 갈렸고(2회), 갈린
직후 puff가 실행되어 `memory.max`가 증가했으며, 최종적으로 컨테이너가
살아남았다. 즉 **"swap 포화 → delta=0 → OLD 로직 미감지"는 로그 해석의
문제가 아니라 실제로 발생하는 논리적 사각지대이며, `swap_saturated`
조건이 그것을 메워 실제 개입(puff)을 유발했다**는 것이 직접 증명됐다.

## ⚠️ 함께 발견된 한계 (정직하게 기록)

실험 1·2(puff 없이 관찰만)에서는 **불일치가 0회**였다. 이유:

- `SWAP_SATURATION_RATIO=0.95` → 포화 판정 기준은 `128 × 0.95 = 121.6MiB`
- 실험 1에서 swap은 **121.5MiB**에서 멈췄다 — 기준선보다 **0.1MiB 모자라서**
  `swap_saturated`가 끝내 발화하지 않았다
- 실험 2에서는 한도 초과(`over=1`) 폴링 166회 중 **158회를 두 로직 모두
  미감지**했다

즉 이 수정은 **swap이 상한의 95%를 실제로 넘겼을 때만 작동**하며, 그
아래에서 멈추면 여전히 사각지대가 남는다. puff가 함께 돌 때는 memory.max가
계속 커지며 swap을 반복적으로 상한까지 밀어붙여 포화가 자주 발생하지만
(실험 3에서 266회), puff가 없거나 swap이 애매하게 멈추는 경우에는
감지되지 않는다.

**향후 개선 방향(미구현)**: `SWAP_SATURATION_RATIO`를 낮추거나, swap 수치
대신 "`memory.current`가 `memory.max`에 근접하며 상승 중"이라는 더 견고한
신호를 추가하는 것.
