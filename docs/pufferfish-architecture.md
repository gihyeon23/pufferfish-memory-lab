# Pufferfish 논문 아키텍처 요약

CLAUDE.md 워크플로에 따라 논문(`docs/papers/pufferfish-paper.pdf`,
`pufferfish-paper.txt`)을 분석해 핵심 내용만 정리한 문서. 페이지 번호는
`pdftotext` 변환 텍스트 기준(원본 PDF 논문 하단 페이지 번호와 동일, 260~264).

이 문서에 없는 세부사항이나 정확한 인용문이 필요하면 논문 원문을 직접 읽는다.

## 1. OCM(On-Container Memory pressure) 식별 (p.260)

> "if the sum of the memory usage and swap usage are larger than the
> memory limit and there are swapping activities detected, the container
> should be suspended."

- 조건: `memory usage + swap usage > memory limit` **AND** `swapping activity 감지`
- OCM 컨테이너는 CPU를 1%로 낮추고 단일 코어로 CPUSET 제한 → suspend
  (task는 살아있지만 진행은 멈춤, heartbeat만 유지, p.260)
- ⚠️ **논문은 "swapping activities detected"를 어떤 카운터/지표로 측정하는지
  명시하지 않는다** (논문 텍스트에 `pswpin`/`pswpout`/delta 관련 언급 없음 —
  키워드 검색으로 확인). 따라서 "delta로 판정한다"는 것은 논문의 사실이
  아니라 **이 프로젝트가 cgroup v2 환경에서 내린 해석**이다.
- 현재 구현([container_monitor.py](../controller/container_monitor.py))의 판정
  귀속은 아래 §2.5(원 공개 구현)와 §3(비교표)에서 명확히 구분한다.

## 2. Node Memory Manager — puff()/reclaim() 두 함수 (p.262~264)

- 컴포넌트 구성: Node Memory Manager(노드당 1개, puff/reclaim 실행 주체) +
  Container Monitor(컨테이너당 1개, cgroup 조작 실행) + Cluster Scheduler
  Plugin(멀티노드 배치용, 이 프로젝트 범위 밖)

### puff() (p.263, Algorithm 1)

- **주기적으로** 실행 — heartbeat 간격인 2초마다 (NodeManager↔ResourceManager
  heartbeat와 동일 주기)
- OCM 컨테이너 집합을 대상으로 `size = size × (1 + ϕ)`, 기본 `ϕ=40%`
- 정지 조건: 모든 FLEX 컨테이너 수요 충족(OCM 없음) **또는** 노드 메모리 소진
- **Backoff 알고리즘**: 같은 노드에 여러 OCM 컨테이너가 있으면 우선순위 1위만
  기본 비율 `ϕ`, 2위는 `ϕ/Nc`, 3위는 `ϕ/Nc²`... 로 낮춰서 준다 (메모리 경쟁 완화)
- 노드 메모리가 이미 꽉 찼는데 최우선 컨테이너가 OCM이면, **최저 우선순위
  컨테이너를 kill**한다(재기동 비용이 가장 적으므로) — reclaim이 아니라 kill.
- **현재 구현과 차이**: [puff_manager.py](../controller/puff_manager.py)의
  `puff()`는 이벤트 기반(OCM 감지 시 `container_monitor.py`가 즉시 호출,
  500ms 폴링 주기에 종속)이지 논문처럼 2초 고정 주기 별도 루프가 아니다.
  또한 backoff/kill 로직은 구현돼 있지 않다(우선순위 개념 자체가 없음,
  단일 호스트에 컨테이너 몇 개뿐이라 아직 불필요했음).

### reclaim() (p.263~264) — ★ 가장 중요한 트리거 조건

> "reclaim() is called **whenever a new container is to be launched** on
> the node. At that moment, the Node Memory Manager needs to check if the
> node has enough memory. If not, it chooses one of the FLEX containers..."
> (p.263)

> "Before Pufferfish launches a container on a node, it checks if the node
> has enough memory. If not, function reclaim() is called to reclaim
> memory based on memory availability and memory demand... **Reclaiming
> starts from the OCM container with the lowest priority**... Pufferfish
> uses a **lazy approach that delays the memory reclaim until the node
> memory cannot satisfy a newly scheduled container**." (p.264)

- 트리거: **신규 컨테이너 admission(배치) 요청 시점**의 메모리 부족 체크.
  REGULAR 컨테이너는 요청 메모리 전체만큼, FLEX 컨테이너는 `MIN_CONT`만큼
  여유가 필요.
- **호스트 사용률이 특정 %를 넘었다고 주기적으로 도는 메커니즘이 아니다.**
  "lazy" reclaim — 정말 필요해질 때까지 미룬다.
- 회수 대상: 우선순위가 **가장 낮은** OCM 컨테이너부터 (REGULAR 컨테이너
  보호 목적)
- reclaim된 컨테이너는 suspend 상태 유지, 다른 컨테이너가 종료돼 메모리가
  풀리면 즉시 다시 puff됨.

### 우선순위 정책 (p.264)

- **EJF(Earliest Job First, 기본값)**: job 도착 시간 기준, 오래된 job이 먼저
  메모리를 반환할 것이라는 가정
- **SJF(Shortest Job First)**: 예상 완료 시간 기준, 짧은 job 우선 (job 소요
  시간 추정 필요, 과거 로그 기반)
- suspension tolerance(최대 suspend 허용 시간, 기본값 = job 예상 기간의 절반)
  넘으면 kill → 다른 노드에서 재기동 기대

## 2.5 원 저자 공개 구현 (논문 본문과 별개로 직접 확인한 사실)

출처: <https://github.com/yncxcw/pufferfish> (2026-09-11 직접 대조 확인).
**논문 본문에 적힌 내용이 아니라, 저자가 공개한 코드에서 확인한 사실**이다.

### OCM 판정 — delta를 쓰지 않는다

`ContainerImpl.java`의 `getIsOutofMemory()`:

```java
public boolean getIsOutofMemory(){
    if(!isRunning) return false;
    updateCgroupValues();
    if(currentUsedMemory+currentUsedSwap>limitedMemory){
        LOG.info("out of memory contianer detected...");
        return true;
    }else{
        return false;
    }
}
```

즉 원 공개 구현은 **순간값 비교 한 줄뿐**이고, 다음이 **전부 없다**:

- `delta_swap_current > 0`
- `pswpin`/`pswpout` delta
- swap 포화 비율(95%) 임계값

따라서 이 프로젝트의 초기 판정(`over_limit AND delta_swap_current > 0`)은
**원 공개 구현을 옮긴 것이 아니라, 논문의 "swapping activities" 문장을
cgroup v2 환경에서 delta로 해석한 우리 자체 구현**이다.

### swap 상한 — 사실상 무제한에 가깝다

`DockerContainerExecutor.java`의 컨테이너 최초 실행:

```java
.append("--memory="+memory+"m")
.append("--memory-swap -1")
.append("--oom-kill-disable")
```

- `--memory-swap -1` = 호스트 swap 범위 내에서 **swap 제한 없음**
- `--oom-kill-disable` = 해당 컨테이너의 **OOM killer 비활성화**
  (이 프로젝트는 이 옵션을 쓰지 않는다 — 우리 실습에서 컨테이너가
  OOM-kill되는 또 하나의 귀속 차이)

`ContainerImpl.java`의 puff 후 갱신(`DockerCommandMemory()`):

```java
Long memory_swap=memory+131072;
...
commandMemory.add("--memory-swap");
commandMemory.add(memory_swap.toString()+"m");
```

`m`(MiB) 접미사가 붙으므로 추가 swap 여유는 **131072MiB ≈ 128GiB**.
현재 프로젝트의 `SWAP_HEADROOM_MB = 128`(MiB)과 비교하면 **1024배 차이**다.

➡️ **결론: 우리 실습에서 관찰된 "128MiB swap 포화" 현상은 원 Pufferfish의
기본 동작이 아니라, 이 프로젝트가 cgroup v2 재현 과정에서 추가한 작은 swap
상한 때문에 발생한 현상이다.**

### ⚠️ cgroup 버전은 논문에 명시되지 않는다

논문 전체에서 cgroup 언급은 4곳뿐이며(p.259 "via Linux cgroup", p.260
"through the cgroup subsystem", p.263, p.266) **전부 버전 표기가 없다**
(`cgroup v1`/`v2` 문자열 검색 0건). 원 공개 구현도 Docker/YARN 기반이라
2019년 시점상 v1 추정은 가능하지만 **코드에 명시된 근거는 없다**.

따라서 발표·문서에서 **"논문은 cgroup v1 기반"이라고 단정하면 안 된다.**
정확한 표현:

| 구분 | cgroup 버전 |
|---|---|
| 논문 본문 | **미명시** |
| 원 공개 구현 | 미명시 (Docker/YARN, 2019년 시점) |
| 현재 프로젝트 | **cgroup v2** (확인됨) |

### 원 설계의 thrashing 대응은 suspend다 (trade-off 정리)

"원 구현은 swap 상한이 사실상 없으니 thrashing에 취약하다"고만 쓰면
**부정확하다.** 논문 **§3.2의 제목 자체가 "Suppressing Memory
Thrashing"**이고, p.260에 다음과 같이 명시돼 있다:

> "...its CPU resource to a very low level such that **thrashing is
> throttled**"

즉 원 설계는 **"사실상 무제한 swap + CPU 1% suspend + `--oom-kill-disable`"
이 한 세트**로 동작하며, suspend가 thrashing의 **속도**를 억제한다
(Figure 3에서 reclaim 시 2GB/s였던 디스크 I/O가 CPU 1% 적용 후 1MB/s
이하로 떨어지는 것을 실측, p.261).

다만 suspend는 **총 swap 사용량 자체를 제한하지는 않으므로**, 컨테이너
수가 늘어나면 호스트 swap 용량이라는 물리적 한계는 남는다. 두 방식의
trade-off를 정리하면:

| 방식 | 억제하는 것 | 남는 위험 |
|---|---|---|
| 무제한 swap + suspend (원 설계) | thrashing **속도** (CPU 스로틀) | 호스트 swap **총량** 고갈 |
| `SWAP_HEADROOM_MB=128` 고정 (현재 프로젝트) | 컨테이너별 swap **총량** | 컨테이너 **조기 OOM-kill** |

이 대비가 이 프로젝트의 후속 연구 질문으로 이어진다(§4.3).

### 슬랙 축소 조건 — 실사용량 기준

원 구현에도 `SLACK_FACTOR = 1.1`과
`if(limitedMemory > (currentUsedMemory+currentUsedSwap)*SLACK_FACTOR)` 형태의
축소 조건이 있다 — 즉 **실사용량을 기준으로 여유분만 줄인다**는 원칙이 코드에
직접 들어가 있다(이 프로젝트의 8차 "실사용량 안전 하한선" 수정과 같은 취지).

## 3. 이 저장소 구현과의 관계 정리

### 3.1 핵심 귀속 비교표 (논문 본문 / 원 공개 구현 / 현재 프로젝트)

가장 혼동되기 쉬운 네 항목을 세 갈래로 분리한 표. **"논문에 있다"와 "저자
코드에 있다"와 "우리가 만들었다"를 절대 섞지 말 것.**

| 구분 | 논문 본문 | 원 공개 구현 | 현재 프로젝트 |
|---|---|---|---|
| OCM 판정 | `over_limit + swapping activity`, **측정법 미명시** | `memory+swap>limit` (delta 미사용) | delta 기반 + 95% 포화 보완 |
| swap 제한 | 구체적 수치 미명시 | 최초 무제한(`-1`), 갱신 후 약 128GiB 여유 | 고정 128MiB 여유 |
| 증가율 `M(t+δ)/M(t)` 사용 | **puff 비율 ϕ 결정용** | 40% 기본 비율 | 향후 OCM 보조 신호로 검토(미구현) |
| `delta=0` 사각지대 | 직접 다루지 않음 | delta를 안 쓰므로 해당 없음 | **우리 초기 구현에서 발생** |
| OOM killer | 언급 없음 | `--oom-kill-disable`로 비활성 | 활성(기본값) |
| thrashing 대응 | **CPU 1% suspend로 억제**(§3.2) | 동일(suspend 구현) | 동일(suspend 구현) |
| cgroup 버전 | **미명시** | 미명시(Docker/YARN, 2019) | cgroup v2 |

### 3.2 기존 항목별 비교

| 구분 | 논문 (p.260~264) | 현재 구현 | 성격 |
|---|---|---|---|
| OCM 판정 | mem+swap > limit AND swap activity (측정법 미명시) | delta 기반 판정 + swap_saturated(95%) 보완 | **논문 조건의 우리 해석** — 원 공개 구현은 delta를 쓰지 않음 |
| puff 트리거 | 2초 고정 주기 별도 루프 | OCM 감지 즉시(500ms 폴링에 종속) | 논문과 다르지만 목적은 동일 |
| puff 비율 | ϕ=40%, backoff 있음 | 40%, backoff 없음 | 단순화 (컨테이너 수 적어 아직 불필요) |
| **reclaim 트리거** | **신규 컨테이너 admission 실패 시 (lazy)** | **호스트 할당량 90% 초과 시 주기적 폴링** (`host_reclaim_daemon.py`) | **논문 재현 아님 — 이 프로젝트가 OOM 예방용으로 독자 설계한 확장 정책** |
| reclaim 대상 선정 | 최저 우선순위 OCM 컨테이너 (EJF/SJF) | EJF(가장 나중에 생성된 컨테이너부터), `docker inspect .Created` 기준 | 6차에서 EJF로 교체 완료 — SJF는 job 소요시간 추정이 필요해 미구현 |
| reclaim의 회수 범위 | "여유분(slack)만 회수, 실제 수요는 안 건드림"(p.263) | `memory.current`(실사용량) + 안전마진 아래로는 안 내림 | 8차에서 추가 — 처음엔 안 지켜서 reclaim 직후 즉시 OOM-kill되는 버그가 있었음. 원 공개 구현도 `SLACK_FACTOR=1.1` 기반 실사용량 비교를 하므로 취지는 동일 |
| swap 여유(headroom) | 구체적 수치 미명시 | `SWAP_HEADROOM_MB=128`(MiB) 고정 | **논문·원 구현 어느 쪽도 아닌 우리 설정** — 원 구현은 최초 `-1`(무제한), 갱신 후 약 128GiB (§2.5) |
| OOM killer | 언급 없음 | 활성(기본값) | 원 구현은 `--oom-kill-disable`로 비활성화 — 우리 실습의 OOM-kill 관찰은 이 차이에서 비롯됨 |

**결론**: 04번(`host_reclaim_daemon.py`)은 논문의 reclaim 메커니즘이 아니다.
논문에 가깝게 재현하려면 "신규 컨테이너 실행 요청 → 가용 메모리 부족 확인 →
부족하면 reclaim → 컨테이너 실행" 흐름을 admission 경로에 넣어야 한다
(자세한 제안은 [docs/papers/pufferfish-reclaim-review-context.md](papers/pufferfish-reclaim-review-context.md)
참고).

## 4. 향후 개선 방향 (귀속 구분)

### 4.1 논문 충실 재현 방향

- 원 공개 구현과 **동일한 OCM 판정**(`memory+swap > limit` 단일 조건)을 별도
  기준으로 두고, 현재의 delta+포화 방식과 나란히 비교하는 실험
- `--oom-kill-disable`, `--memory-swap -1`을 적용해 원 구현의 실행 조건을
  재현했을 때 OOM-kill 현상 자체가 사라지는지 확인

### 4.2 현재 cgroup v2 확장 방향 (이 프로젝트 독자 아이디어)

- `memory.swap.events`의 `max`/`fail` 카운터 — swap 할당 실패를 커널이
  직접 알려주는 신호
- `memory.events`의 `max` 카운터 — 한도 도달 횟수
- PSI(Pressure Stall Information) — 메모리 압박을 직접 수치화
- **95% 포화 비율(`SWAP_SATURATION_RATIO`)은 위와 같은 직접적 커널 이벤트를
  쓰지 못할 때의 fallback**이며, 논문의 방법이 아니다
- `memory.current` 상승 추세: **OCM의 단독 근거가 아니라** 조기 경고 또는
  puff 크기 결정 보조값으로만 쓸 것.
  ⚠️ 논문의 `M(t+δ)/M(t)`는 **ϕ(puff 비율) 결정 방법**이므로(p.263),
  이를 "논문이 제시한 OCM 개선 방법"이라고 쓰면 안 된다.

### 4.3 도출된 연구 질문

§2.5의 trade-off 표(무제한 swap + suspend vs. 고정 128MiB)에서 다음 질문이
나온다:

> **컨테이너 생존성과 호스트 안전성을 동시에 만족하는 swap 정책은
> 무엇인가?**

- 원 설계(무제한 + suspend): 컨테이너는 살지만 호스트 swap 총량이 무보호
- 현재 프로젝트(128MiB 고정): 호스트는 보호되나 컨테이너가 조기 OOM-kill

후속 과제(우선순위 순):

1. `memory.swap.events`의 `max`/`fail`로 **swap 상한 충돌을 커널에서 직접
   감지** — 고정 95% 비율을 대체
2. 고정 임계값 대신 **커널 이벤트 기반 OCM 판정**으로 전환
3. **워크로드 수요에 따른 동적 swap headroom** (고정 128MiB 대신
   `memory.max`에 비례 또는 실측 수요 기반)
4. **호스트 전체 swap 예산 + 컨테이너별 상한 결합** (두 축을 동시에 제약)
5. **동일 로그에 3가지 판정 비교** — 논문/원 구현 방식(`mem+swap>limit`
   단일 조건), 우리 OLD(delta), 우리 NEW(delta+포화).
   → 이미 [docs/evidence/05-ab-test-script.py](evidence/05-ab-test-script.py)가
   OLD/NEW 2종 비교를 하므로, **판정 함수 하나만 추가하면 바로 실행
   가능**하다
