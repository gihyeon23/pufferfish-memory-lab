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
OLD (우리 초기 cgroup v2 해석) : over_limit AND swap_activity(delta 기반)
NEW (우리 보완 로직)            : over_limit AND (swap_activity OR swap_saturated)
```

> ⚠️ **귀속 주의**: 여기서 비교하는 OLD/NEW는 **둘 다 이 프로젝트의 구현**
> 이다. Pufferfish 원본과는 다음과 같이 다르다:
> - 논문(§3.2)은 `mem+swap > limit AND swapping activities`로만 서술하고
>   **측정 방법을 명시하지 않는다**
> - 원 저자 공개 구현(`ContainerImpl.getIsOutofMemory()`)은
>   `memory+swap > limit` **단일 조건만** 쓰며 **delta를 전혀 쓰지 않는다**
>   → 원 구현에는 `delta=0` 사각지대가 애초에 존재하지 않는다
>
> 즉 이 실험은 **"논문/원 구현의 결함을 발견한 것"이 아니라, "논문의
> swapping activity 문장을 delta로 해석한 우리 초기 구현의 사각지대를
> 확인하고 보완한 것"**이다.
> ([pufferfish-architecture.md](../pufferfish-architecture.md) §2.5)

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

### 이 실험이 증명하는 것 / 증명하지 않는 것

| | 내용 |
|---|---|
| ✅ 증명함 | 우리 초기 판정(`over_limit AND delta_swap>0`)에 사각지대가 있었다 |
| ✅ 증명함 | 우리 `swap_saturated` 보완이 이 실험에서 실제로 작동해 puff를 유발했다 |
| ❌ 증명하지 **않음** | 원 저자 공개 구현도 `delta=0` 때문에 OCM을 놓친다 (원 구현은 delta를 안 씀) |
| ❌ 증명하지 **않음** | 원 Pufferfish 알고리즘의 결함을 발견했다 |

## ⚠️ 함께 발견된 한계 — **고정 95% 포화 판정의 경계 조건**

> **표현 주의**: 이것은 "puff가 없는 환경의 한계"가 **아니다.** puff 부재는
> 원인이 아니라 이 사각지대가 **드러난 조건**일 뿐이다. 원인은
> **`SWAP_SATURATION_RATIO = 0.95`라는 고정 임계값 자체의 경계 조건**이다.
>
> 또한 이 한계는 **논문의 한계가 아니라 이 프로젝트가 추가한 보완 로직의
> 한계**다 — 논문은 포화 임계값 개념을 제시하지 않으며, 원 공개 구현에도
> 없다(원 구현은 `memory+swap > limit` 단일 조건).

실험 1·2(puff 없이 관찰만)에서는 **불일치가 0회**였다. 이유:

- `SWAP_SATURATION_RATIO=0.95` → 포화 판정 기준은 `128 × 0.95 = 121.6MiB`
- 실험 1에서 swap은 **121.5MiB**에서 멈췄다 — 기준선보다 **0.1MiB 모자라서**
  `swap_saturated`가 끝내 발화하지 않았다
- 실험 2에서는 한도 초과(`over=1`) 폴링 166회 중 **158회를 두 로직 모두
  미감지**했다

즉 이 보완은 **swap이 상한의 95%를 실제로 넘겼을 때만 작동**하며, 그 바로
아래(예: 94.9%)에서 멈추면 사각지대가 그대로 남는다 — **고정 비율
임계값이 갖는 구조적 경계 조건**이다.

puff가 함께 도는 환경(실험 3)에서는 `memory.max`가 계속 커지며 swap을
반복적으로 상한까지 밀어붙이므로 포화가 자주 발생해(266회) 이 경계 문제가
잘 드러나지 않았고, puff 없이 관찰만 한 실험 1·2에서 비로소 드러났다.
**즉 puff 부재가 원인이 아니라, 임계값 경계가 원인이고 puff 부재는 그것이
노출된 조건이다.**

**향후 개선 방향(미구현, 전부 이 프로젝트의 아이디어)**:

- 커널이 직접 주는 신호로 교체 — `memory.swap.events`의 `max`/`fail`
  (swap 할당 실패), `memory.events`의 `max`, PSI
  (95% 포화 비율은 이런 직접 신호를 못 쓸 때의 **fallback**이다)
- `SWAP_SATURATION_RATIO` 하향 조정
- `memory.current` 상승 추세: **OCM 단독 근거가 아니라** 조기 경고 또는
  puff 크기 결정 보조값으로만.
  ⚠️ 논문의 `M(t+δ)/M(t)`는 **ϕ(puff 비율) 결정 방법**이므로(p.263),
  이를 "논문이 제시한 OCM 개선 방법"으로 쓰면 안 된다.
- 논문 충실 재현 방향으로는, 원 공개 구현과 동일한 판정
  (`memory+swap > limit` 단일 조건)을 별도 기준으로 두고 비교하는 실험
