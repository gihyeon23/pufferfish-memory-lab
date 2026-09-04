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
- 현재 구현([container_monitor.py](../controller/container_monitor.py))이 이 조건을
  그대로 따름. 단 `swap_saturated` OR 조건은 **논문에 없는, 이 프로젝트의
  cgroup v2 재현 과정에서 발견한 blind spot 보완**(3차 실습, swap delta가
  포화 후 0으로 고정되는 문제 대응)이다.

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

## 3. 이 저장소 구현과의 관계 정리

| 구분 | 논문 (p.260~264) | 현재 구현 | 성격 |
|---|---|---|---|
| OCM 판정 | mem+swap > limit AND swap activity | 동일 + swap_saturated 보완 | 논문 재현 + cgroup v2 보완 |
| puff 트리거 | 2초 고정 주기 별도 루프 | OCM 감지 즉시(500ms 폴링에 종속) | 논문과 다르지만 목적은 동일 |
| puff 비율 | ϕ=40%, backoff 있음 | 40%, backoff 없음 | 단순화 (컨테이너 수 적어 아직 불필요) |
| **reclaim 트리거** | **신규 컨테이너 admission 실패 시 (lazy)** | **호스트 할당량 90% 초과 시 주기적 폴링** (`host_reclaim_daemon.py`) | **논문 재현 아님 — 이 프로젝트가 OOM 예방용으로 독자 설계한 확장 정책** |
| reclaim 대상 선정 | 최저 우선순위 OCM 컨테이너 (EJF/SJF) | 가장 최근에 puff된 컨테이너(mtime) | 우선순위 개념 없어 대체 휴리스틱 사용 |

**결론**: 04번(`host_reclaim_daemon.py`)은 논문의 reclaim 메커니즘이 아니다.
논문에 가깝게 재현하려면 "신규 컨테이너 실행 요청 → 가용 메모리 부족 확인 →
부족하면 reclaim → 컨테이너 실행" 흐름을 admission 경로에 넣어야 한다
(자세한 제안은 [docs/papers/pufferfish-reclaim-review-context.md](papers/pufferfish-reclaim-review-context.md)
참고).
