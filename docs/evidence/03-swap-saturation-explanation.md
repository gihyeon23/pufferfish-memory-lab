# 증거 자료: swap 포화 → OCM 미감지 → OOM-kill (3차 실습)

## 이 문서의 목적

"delta_swap_current=0이 문제였다는 게 진짜냐, 아니면 화면 출력(디스플레이)
문제 아니냐"는 질문에 답하기 위한 원본 증거.

> ⚠️ **귀속 주의 (먼저 읽을 것)**: 아래에서 다루는 `delta_swap_current` 기반
> 판정과 128MiB swap 상한은 **모두 이 프로젝트의 cgroup v2 재현 구현에서
> 나온 것**이며, Pufferfish 원본의 동작이 아니다.
> - 논문(§3.2)은 OCM을 `mem+swap > limit AND swapping activities`로만
>   서술하고 **측정 방법을 명시하지 않는다**
> - 원 저자 공개 구현(`ContainerImpl.getIsOutofMemory()`)은
>   `memory+swap > limit` **단일 조건만** 쓰고 delta를 전혀 쓰지 않는다
> - 원 구현의 swap 여유는 최초 `--memory-swap -1`(무제한), 갱신 후
>   약 128GiB로 우리(128MiB)보다 1024배 크다
>
> 자세한 대조: [pufferfish-architecture.md](../pufferfish-architecture.md) §2.5

- 원본 로그 전체: [03-swap-saturation-raw-monitor-2.log](03-swap-saturation-raw-monitor-2.log)
  (422줄, 컨테이너 `pf-test-2`를 500ms 간격으로 폴링한 실제 기록)
- git 커밋 `e81c26b`(`docs: 3차 다중 컨테이너 실습 로그 갱신`)에서 그대로
  복원한 것 — 사후에 조작되거나 재구성된 게 아니라, 그 실험 직후 커밋된
  원본이다.

## 왜 "디스플레이 문제"가 아닌가 — 3가지 근거

### 1. `cpu.usage_usec`가 단조 증가

전 구간에서 이 값이 계속 커진다(예: 1616725 → 1621045 → 1626054 → ... →
2048371 → 2053076 → 2058591 → 2063916). 이건 리눅스 커널이 실제로 누적
집계하는 CPU 사용 시간 카운터라, 화면 출력 버그로는 이렇게 계속 늘어날
수 없다 — 폴링이 실시간으로 실제 값을 읽고 있었다는 증거.

### 2. `oom`/`oom_kill`은 우리 코드가 만든 값이 아니라 커널의 값

이 필드는 컨테이너 cgroup의 `memory.events` 파일을 그대로 읽은 것이다
(`cgroup_utils.read_events()`). 즉 "우리 Python 스크립트가 잘못 계산해서
1이라고 출력한 것"이 아니라 **리눅스 커널이 그 cgroup에서 실제로 OOM
killer를 발동시켰다고 직접 기록한 값**이다.

### 3. `current`가 실제로 붕괴 — 프로세스가 물리적으로 죽었다는 증거

마지막 구간:

```
current=980.7MiB ... oom_kill=1
current=932.9MiB
current=883.0MiB
current=853.1MiB
current=0.3MiB
[container_monitor] pf-test-2: cgroup을 더 이상 읽을 수 없습니다 (컨테이너 종료 또는 OOM-kill로 추정)
```

메모리 사용량이 980MiB대에서 몇 번의 폴링 만에 0.3MiB로 떨어지고, 그
다음 폴링에서 cgroup 파일 자체를 못 읽게 된다(컨테이너가 실제로
사라졌다는 뜻). 화면 출력 버그라면 이런 물리적 붕괴 패턴이 나올 수
없다.

## 이 로그가 증명하는 것 / 증명하지 않는 것

| | 내용 |
|---|---|
| ✅ 증명함 | swap이 128MiB 부근에서 **정체**하고 `memory.current`는 계속 증가했다 |
| ✅ 증명함 | 커널이 **실제로** OOM-kill했다 (`memory.events` `oom_kill=1`, `current` 붕괴) |
| ✅ 증명함 | 화면 출력·버퍼링 문제가 아니다 (`cpu.usage_usec` 단조 증가) |
| ❌ 증명하지 **않음** | "**128MiB 상한이 원인**"까지는 이 로그만으로 말할 수 없다 |

마지막 항목이 중요하다. 이 로그는 **"swap이 128MiB에서 멈췄다"**는
현상까지만 보여준다. **"128MiB가 부족했기 때문이다"**라는 인과는
swap 상한을 풀어보는 별도 실험
([04-swap-headroom-increase-experiment.md](04-swap-headroom-increase-experiment.md))과
합쳐야 성립한다:

```
[실험 1: 이 로그]  swap 128MiB 정체 + current 상승 + 실제 OOM-kill
[실험 2: 상한 확대] 상한 풀면 실제로 183~191MiB까지 사용
        ↓ 두 실험을 합치면
128MiB 상한 → 필요한 swap을 못 씀 → memory.current 증가
            → memory.max 도달 → OOM-kill
```

## 핵심 구간: swap 포화 → OCM 미감지 상태 지속

```
current=719.9MiB swap=128.0MiB max=981.0MiB delta_swap_current=7544832 swap_saturated=True
current=723.1MiB swap=128.0MiB max=981.0MiB delta_swap_current=0       swap_saturated=True
current=727.1MiB swap=128.0MiB max=981.0MiB delta_swap_current=0       swap_saturated=True
...
current=980.7MiB swap=127.8MiB max=981.0MiB delta_swap_current=0       swap_saturated=True  oom=1 oom_kill=1
```

`swap`이 128MiB 근처(사실상 상한)에서 멈춘 채로 `delta_swap_current`(직전
폴링 대비 증가량)가 계속 0으로 찍히는데, `current`(swap이 아닌 실제
메모리)는 719→980MiB까지 계속 올라간다. swap이 이 시점 이후로 더는
못 늘어나니(포화), 늘어나는 메모리 수요가 고스란히 `current`로 쌓이다가
`memory.max`(981MiB)에 닿아 OOM-kill됐다.

당시 **이 프로젝트의** OCM 판정 로직(`over_limit AND swap_activity`)은
`delta_swap_current`가
0이면 "swap 활동 없음 = 문제없음"으로 오판했다 — 실제로는 "더 도망갈
곳이 없어서 활동을 못 하는 것"인데. 이 blind spot을 고치기 위해
`swap_saturated`(swap.current가 swap.max의 95% 이상) 조건을 OR로
추가했다.

## 참고: "swap=127.9가 진짜 값이냐"는 추가 질문에 대해

이 raw 값 자체도 사실은 **상한(swap.max=128MiB, `SWAP_HEADROOM_MB`)에
막힌 값**이지, 워크로드가 실제로 원한 swap 양이 아니다. 이 부분의 별도
검증(SWAP_HEADROOM_MB를 키워서 실제 수요가 128MiB보다 컸는지 확인하는
실험)은 [04-swap-headroom-increase-experiment.md](04-swap-headroom-increase-experiment.md)
참고.
