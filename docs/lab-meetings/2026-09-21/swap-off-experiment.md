# 실험: swap 차단(쿠버네티스 조건) + 응답시간 측정 (A/B/C)

**실행일**: 2026-09-18 | **관련**: [2026-09-21.md](2026-09-21.md) 작업 1

## 목적

교수님 피드백 2건을 하나의 실험으로 검증한다.

1. **쿠버네티스는 swap을 막는다** → swap을 끈 조건에서 OOM killer가 실제로 도는가?
2. **응답시간을 timestamp로 측정** → swap을 쓰면 디스크 I/O 때문에 시간이 크게 늘어나는가?

## 설계 — 왜 3개 조건인가 (교란변수 분리)

`fill()`(전 페이지 터치) 소요시간을 느리게 만드는 원인은 **두 가지**다:

- **swap 디스크 I/O** ← 측정하고 싶은 것
- **CPU 1% suspend** ← Pufferfish가 OCM 감지 시 거는 스로틀

둘을 같이 켜면 "느려진 게 swap 때문인지 CPU 때문인지" 구분할 수 없다.
그래서 suspend를 끈 A/B로 **swap 효과만 분리**하고, C는 참고용으로 둔다.

| 조건 | swap | suspend/puff | docker 옵션 | 목적 |
|---|---|---|---|---|
| **A** | 512MiB | ❌ 끔 | `--memory=256m --memory-swap=768m` | 순수 swap 지연 |
| **B** | **0** | ❌ 끔 | `--memory=256m --memory-swap=256m` | 쿠버네티스 조건 / 기준선 |
| **C** | 512MiB | ✅ 켬 | A와 동일 + `container_monitor.py` | 교란변수 크기 확인 |

> **호스트 swap을 끌 필요가 없다(sudo 불필요).** Docker에서 `--memory-swap`을
> `--memory`와 같은 값으로 주면 그 컨테이너의 swap 할당량이 0이 되어
> 쿠버네티스와 동일한 조건이 된다(B 샘플러 로그에서 `swap.max=0.0MiB` 확인).

A·B는 suspend/puff를 하지 않는 **관찰 전용 샘플러**([passive_sampler.py](passive_sampler.py))로
cgroup 상태만 기록했다.

## 코드 변경

기존 워크로드는 초 단위 timestamp만 찍고 **할당 1회 소요시간을 재지 않았다.**
`Arrays.fill()`이 전 페이지를 터치하는 구간이 바로 swap 지연이 나타나는 곳이므로
여기를 `System.nanoTime()`으로 감쌌다.

```java
long startNanos = System.nanoTime();
byte[] chunk = new byte[(int) chunkSizeBytes];
fill(chunk);                                     // 전 페이지 터치 = page fault 발생 지점
long elapsedMicros = (System.nanoTime() - startNanos) / 1_000L;
```

- 타임스탬프 해상도도 초 → **밀리초**(`HH:mm:ss.SSS`)로 상향
- 로그에 `alloc_fill=N.NNNms` 필드 추가
- 이미지 태그: `pufferfish/workload-java:timing`

공통 워크로드 설정: `CHUNK_SIZE_MB=8`, `INTERVAL_SECONDS=2`,
`MAX_ALLOCATION_MB=1024`, `-Xmx1200m`

---

## 결과 1 — swap 차단 시 OOM killer는 실제로 돈다 ✅

| | A (swap 512MiB) | B (swap 0, 쿠버네티스) |
|---|---|---|
| `OOMKilled` | **true** (ExitCode 137) | **true** (ExitCode 137) |
| 죽을 때까지 할당한 누적량 | **520MiB** | **208MiB** |
| 생존 시간 | 약 130초 | **약 55초** |
| 최종 cgroup 상태 | `current=255.9` `swap=503.3`/512MiB | `current=255.8` `swap=0.0`/**0**MiB |

**swap이 0이면 2.5배 적게 할당하고 2.4배 빨리 죽는다.** B는 `memory.max`(256MiB)에
닿는 즉시 도망갈 곳이 없어 바로 OOM-kill됐다.

A의 swap 사용 추이(샘플러 로그) — `current`는 256MiB에 고정된 채 swap이 흡수:

```
current=251.4MiB swap=0.0MiB      <- 한도 도달 직전
current=255.8MiB swap=132.4MiB    <- swap 시작
current=255.8MiB swap=253.2MiB
current=255.8MiB swap=322.8MiB
current=256.0MiB swap=448.1MiB
current=255.9MiB swap=503.3MiB  oom=2 oom_kill=1   <- swap.max(512) 임박 -> OOM
```

## 결과 2 — swap을 쓰면 할당 시간이 늘어난다 ✅ (단, 생각보다 완만)

`alloc_fill` (8MiB 할당 + 전 페이지 터치 1회 소요시간)

| 구간 | 중앙값 | 평균 | 최대 |
|---|---|---|---|
| A: 누적 ≤256MiB (swap 전) | 6.97ms | 16.67ms | 228.69ms |
| **A: 누적 >256MiB (swap 구간)** | **18.10ms** | **33.09ms** | **401.83ms** |
| B: 전 구간 (swap 없음) | 8.15ms | 14.75ms | 76.62ms |

- swap 구간은 **중앙값 2.2~2.6배**, **최대값 5.2배**(76ms → 402ms) 느려짐
- 방향은 교수님 예측대로지만 **자릿수가 바뀔 정도는 아니었다.**
  VirtualBox VM의 swap이 Mac SSD 기반이라 디스크가 빠르고, 커널이
  kswapd로 상당 부분을 **비동기 회수**하기 때문으로 보인다(추정)

## 결과 3 — ⚠️ 진짜 큰 지연은 swap이 아니라 CPU 1% suspend였다

| C 조건 | 중앙값 | 평균 | 최대 |
|---|---|---|---|
| suspend 적용 전 | 9.87ms | 23.82ms | 161.33ms |
| **suspend 적용 후 (CPU 1%)** | **849.80ms** | **2,802.51ms** | **35,398.82ms** |

`container_monitor.py`가 OCM을 감지해 CPU를 1%로 떨어뜨린 직후, 동일한 8MiB
할당이 **약 86배** 느려졌고 최악의 경우 **한 번의 할당에 35초**가 걸렸다.

### 세 조건 비교 (핵심)

| 지연 원인 | 중앙값 배율 | 최대값 |
|---|---|---|
| swap 디스크 I/O (A vs B) | **약 2.2배** | 402ms |
| CPU 1% suspend (C, 전후) | **약 86배** | **35,398ms** |

➡️ **suspend가 swap보다 약 40배 큰 지연을 만든다.** 만약 monitor를 켠 채로
측정했다면(=C만 봤다면), 1800ms짜리 지연을 "swap 때문"으로 잘못 귀속했을
것이다. **A/B로 분리한 것이 이 실험의 핵심 설계 포인트다.**

C는 puff도 함께 돌아 `memory.max`가 256 → 358 → 501MiB로 늘었고, 관찰
종료(200초) 시점까지 **살아 있었다** — Pufferfish의 실제 동작대로 생존했다.

---

## 결론

1. **쿠버네티스처럼 swap을 막으면 OOM killer가 확실히, 그리고 훨씬 빨리 돈다**
   (208MiB/55초 vs 520MiB/130초). 컨테이너 단위로 `--memory-swap == --memory`를
   주면 호스트 swap을 끄지 않고도 동일 조건을 만들 수 있다.
2. **swap은 "시간을 대가로 생존을 사는" 거래다.** 2.5배 더 오래 버티는 대신
   할당 지연 중앙값이 2.2배, 꼬리 지연이 5배 늘었다.
3. **다만 Pufferfish 환경에서 체감 지연의 주범은 swap이 아니라 CPU 1%
   suspend였다(86배).** 이는 논문 §3.2가 의도한 동작이기도 하다 — suspend는
   thrashing을 억제하려고 일부러 CPU를 뺏는 것이므로, 느려지는 것은
   **부작용이 아니라 설계된 대가**다.

## 남은 의문 / 후속 과제

- swap 지연이 예상보다 완만한 이유 — VM 디스크가 SSD 기반이라 그런지,
  아니면 kswapd 비동기 회수 비중이 커서인지 **분리 검증 안 됨**
- 더 큰 청크(32/64MiB)나 더 짧은 간격에서는 동기 회수 비중이 커져
  swap 지연이 더 크게 나타날 가능성 (미검증)
- `memory.stat`의 `pgmajfault`(major page fault) 카운터를 함께 수집하면
  "몇 번이 실제 디스크 왕복이었는지" 직접 셀 수 있다 (이번엔 미수집)

## 원본 로그

| 파일 | 내용 |
|---|---|
| [A-workload.log](A-workload.log) | A 워크로드 출력 (alloc_fill 포함) |
| [A-sampler.log](A-sampler.log) | A cgroup 관찰 (swap 증가 추이) |
| [B-workload.log](B-workload.log) | B 워크로드 출력 |
| [B-sampler.log](B-sampler.log) | B cgroup 관찰 (`swap.max=0` 확인) |
| [C-workload.log](C-workload.log) | C 워크로드 출력 (suspend 후 지연 폭증) |
| [C-monitor.log](C-monitor.log) | C `container_monitor.py` 출력 (suspend/puff 이력) |
