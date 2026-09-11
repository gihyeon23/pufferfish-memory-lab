# 증거 자료: swap 포화 → OCM 미감지 → OOM-kill (3차 실습)

## 이 문서의 목적

"delta_swap_current=0이 문제였다는 게 진짜냐, 아니면 화면 출력(디스플레이)
문제 아니냐"는 질문에 답하기 위한 원본 증거.

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

당시 OCM 판정 로직(`over_limit AND swap_activity`)은 `delta_swap_current`가
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
