# 실험 01 — swap 차단(쿠버네티스 조건)과 할당 응답시간

**실행일**: 2026-09-18 | **상위**: [../2026-09-21.md](../2026-09-21.md) 작업 1

## 목적

교수님 피드백 2건을 하나의 실험으로 검증한다.

1. **쿠버네티스는 swap을 막는다** → swap을 끈 조건에서 OOM killer가 실제로 도는가?
2. **응답시간을 timestamp로 측정** → swap을 쓰면 디스크 I/O 때문에 시간이 늘어나는가?

## 설계 — 왜 조건이 4개인가

`fill()`(전 페이지 터치) 소요시간을 늘리는 원인은 **두 가지**이고, 여기에
**용량이라는 교란변수**가 하나 더 있다.

- **swap 디스크 I/O** ← 측정 대상
- **CPU 1% suspend** ← Pufferfish가 OCM 시 거는 스로틀 (C로 분리)
- **총 메모리 용량** ← 많으면 그냥 더 오래 산다 (D로 통제)

| 조건 | RAM | swap | 총 용량 | suspend | 역할 |
|---|---:|---:|---:|---|---|
| **A** | 256MiB | 512MiB | 768MiB | ❌ | swap 사용 |
| **B** | 256MiB | **0** | 256MiB | ❌ | 쿠버네티스 조건 |
| **C** | 256MiB | 512MiB | 768MiB | ✅ | 교란변수(suspend) 크기 |
| **D** | **768MiB** | 0 | **768MiB** | ❌ | **A와 용량 동일, RAM만** ← 핵심 대조군 |

> **D가 왜 필요한가**: A와 B만 비교하면 A가 더 오래 사는 게 당연하다 —
> 용량이 3배니까. 실제로 아래 "폐기한 주장"에서 보듯 생존 시간은 용량으로
> 100% 설명된다. **총 용량을 768MiB로 맞춘 D**가 있어야 "같은 용량인데
> RAM이냐 swap이냐"만 남는다.

> **호스트 swap을 끌 필요 없음(sudo 불필요)**: `--memory-swap`을 `--memory`와
> 같게 주면 컨테이너 swap이 0이 된다(B·D 샘플러에서 `swap.max=0.0MiB` 확인).

A·B·D는 suspend/puff를 하지 않는 **관찰 전용 샘플러**([passive_sampler.py](passive_sampler.py))를
사용했다. C만 실제 `container_monitor.py`를 붙였다.

## 코드 변경

기존 워크로드는 초 단위 timestamp만 찍고 **할당 1회 소요시간을 재지 않았다.**
`Arrays.fill()`이 전 페이지를 터치하는 구간이 swap 지연이 나타나는 지점이므로
여기를 `System.nanoTime()`으로 감쌌다.

```java
long startNanos = System.nanoTime();
byte[] chunk = new byte[(int) chunkSizeBytes];
fill(chunk);                                     // 전 페이지 터치 = page fault 지점
long elapsedMicros = (System.nanoTime() - startNanos) / 1_000L;
```

타임스탬프도 초 → **밀리초**(`HH:mm:ss.SSS`), 로그에 `alloc_fill=N.NNNms` 추가.
이미지 태그 `pufferfish/workload-java:timing`.

공통 설정: `CHUNK_SIZE_MB=8`, `INTERVAL_SECONDS=2`, `MAX_ALLOCATION_MB=1024`, `-Xmx1200m`

---

## ⚠️ 먼저: 처음에 세웠다가 폐기한 주장

> ~~"swap이 있으면 2.4배 더 오래 산다(130초 vs 55초)"~~ → **의미 없는 주장이라 폐기**

생존 시간이 용량만으로 완전히 설명되기 때문이다. 워크로드는 2초마다 8MiB씩
= **4MiB/s 고정 속도**로 할당한다.

| | 누적 할당량 | 용량만으로 예측한 수명 | 실측 수명 |
|---|---:|---:|---:|
| A | 512MiB | 512 ÷ 4 = **128초** | ~130초 |
| B | 208MiB | 208 ÷ 4 = **52초** | ~55초 |

게다가 수명의 대부분은 우리가 정한 `sleep(2초)`다:

| | sleep 총합 | 실제 작업시간 |
|---|---:|---:|
| A | 128.0초 (**98.8%**) | 1.59초 (1.2%) |
| B | 52.0초 (**99.3%**) | 0.38초 (0.7%) |

즉 **swap 지연이 수명에 기여한 몫은 1% 남짓**이고, "2.4배 오래 살았다"는
"2.5배 용량이 많았다"의 재진술일 뿐이다. 그래서 **용량을 맞춘 D**를 추가했다.

---

## 결과 1 — swap을 막으면 OOM killer는 확실히 돈다 ✅

| | A (RAM256+swap512) | B (RAM256, swap 0) | D (RAM768, swap 0) |
|---|---|---|---|
| `OOMKilled` | true (137) | true (137) | true (137) |
| 누적 할당량 | 512MiB | 208MiB | 712MiB |
| 최종 cgroup | `swap=503/512MiB` | `swap=0/**0**MiB` | `swap=0/**0**MiB` |

**B(쿠버네티스 조건)는 `memory.max`에 닿는 즉시 도망갈 곳이 없어 바로
OOM-kill됐다.** A는 swap이 흡수하다가 swap.max(512MiB)까지 차고 나서야 죽었다:

```
current=251.4MiB swap=0.0MiB                     <- 한도 도달 직전
current=255.8MiB swap=132.4MiB                   <- swap 시작
current=255.8MiB swap=322.8MiB
current=255.9MiB swap=503.3MiB  oom=2 oom_kill=1 <- swap도 소진 -> OOM
```

## 결과 2 — 같은 용량에서 swap 구간은 2.7~3.6배 느리다 ✅ (A vs D)

총 용량을 768MiB로 맞춘 A와 D를 **같은 누적 할당 구간에서** 비교:

| 누적 구간 | A (swap 사용) | D (순수 RAM) | 배율 |
|---|---:|---:|---:|
| 0~256MiB (**둘 다 RAM**) | 6.97ms | 7.71ms | **0.9x** |
| 256~384MiB (A만 swap) | 14.45ms | 5.40ms | **2.7x** |
| 384~512MiB (A만 swap) | 22.91ms | 6.44ms | **3.6x** |

- **0~256 구간에서 차이가 없다(0.9x)** — 둘 다 RAM만 쓰는 구간이므로 같아야
  하고, 실제로 같았다. **실험 통제가 제대로 됐다는 증거**다.
- swap이 시작되는 256MiB 이후부터만 벌어지고, **깊어질수록 심해진다**
  (2.7x → 3.6x).

## 결과 3 — swap으로 채운 용량은 실효 용량이 28% 적다 ✅ (새 발견)

같은 768MiB인데 실제로 할당해낸 양이 다르다:

| | 총 용량 | 실제 할당한 누적량 | 실효율 |
|---|---:|---:|---:|
| A (RAM256 + swap512) | 768MiB | **512MiB** | 67% |
| D (RAM768) | 768MiB | **712MiB** | 93% |

swap 512MiB를 줬지만 그만큼 다 쓰지 못하고 죽었다. (원인은 미검증 —
swap 계정 방식/JVM 런타임 오버헤드 등이 섞였을 것으로 **추정**)

## 결과 4 — ⚠️ 진짜 큰 지연은 swap이 아니라 CPU 1% suspend였다

| C 조건 | 중앙값 | 평균 | 최대 |
|---|---:|---:|---:|
| suspend 적용 전 | 9.87ms | 23.82ms | 161.33ms |
| **suspend 적용 후 (CPU 1%)** | **849.80ms** | 2,802.51ms | **35,398.82ms** |

동일한 8MiB 할당이 suspend 직후 **약 86배** 느려졌고, 최악의 경우 **한 번의
할당에 35초**가 걸렸다.

| 지연 원인 | 중앙값 배율 | 최대 |
|---|---:|---:|
| swap 디스크 I/O (A vs D, 같은 용량) | **2.7~3.6배** | 402ms |
| CPU 1% suspend (C 전후) | **약 86배** | **35,399ms** |

➡️ **suspend가 swap보다 약 24~32배 큰 지연을 만든다.** monitor를 켠 채로만
측정했다면(=C만 봤다면) 1800ms 지연을 통째로 "swap 탓"으로 잘못 귀속했을
것이다. **A/D 분리가 이 실험의 핵심 설계다.**

C는 puff도 함께 돌아 `memory.max`가 256 → 358 → 501MiB로 늘었고, 관찰
종료(200초)까지 **살아 있었다** — Pufferfish 설계대로 생존했다.

---

## 결론

1. **쿠버네티스처럼 swap을 막으면 OOM killer가 확실히 돈다.** 컨테이너 단위로
   `--memory-swap == --memory`를 주면 호스트 swap을 끄지 않고도 동일 조건을
   만들 수 있다(sudo 불필요).
2. **같은 용량이라도 swap으로 채우면 할당 지연이 2.7~3.6배 늘고, 깊이
   들어갈수록 악화된다.** 다만 자릿수가 바뀔 정도(10배 이상)는 아니었다.
3. **같은 용량이라도 swap 기반은 실효 용량이 28% 적었다**(512 vs 712MiB).
4. **Pufferfish 환경에서 체감 지연의 주범은 swap(3.6배)이 아니라 CPU 1%
   suspend(86배)다.** 이는 논문 §3.2가 thrashing 억제를 위해 의도한 동작이므로
   **부작용이 아니라 설계된 대가**다.
5. **"생존 시간" 지표는 쓰지 말 것** — 고정 할당 속도(4MiB/s)와 고정
   sleep(2초) 때문에 용량의 재진술에 불과하다.

## 남은 의문 / 후속 과제

- swap 지연이 예상(자릿수 변화)보다 완만한 이유 — VM swap이 Mac SSD 기반이라
  빠른 건지, kswapd 비동기 회수 비중이 큰 건지 **분리 검증 안 됨**
- `memory.stat`의 `pgmajfault`(major page fault)를 수집하면 "몇 번이 실제
  디스크 왕복이었는지" 직접 셀 수 있다 — **이번엔 미수집**
- swap 실효율이 67%인 원인 미규명
- `INTERVAL_SECONDS`를 줄이면(sleep 비중 축소) 지연이 처리량에 미치는 영향을
  직접 볼 수 있다 — 미실행

## 원본 로그

| 파일 | 내용 |
|---|---|
| [A-workload.log](A-workload.log) / [A-sampler.log](A-sampler.log) | A: swap 사용, swap 0→503MiB 증가 추이 |
| [B-workload.log](B-workload.log) / [B-sampler.log](B-sampler.log) | B: 쿠버네티스 조건, `swap.max=0` 확인 |
| [C-workload.log](C-workload.log) / [C-monitor.log](C-monitor.log) | C: suspend 후 지연 폭증, puff 이력 |
| [D-workload.log](D-workload.log) / [D-sampler.log](D-sampler.log) | D: RAM 768MiB 대조군 |
| [passive_sampler.py](passive_sampler.py) | suspend/puff 없이 cgroup만 관찰하는 스크립트 |
