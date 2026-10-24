# Pufferfish reclaim 논문·현재 구현 비교 검토 요청

## 검토 목적

Pufferfish 논문의 `reclaim()` 트리거를 정확히 재현하고 있는지 현재 실험 코드를 검토하고 싶습니다.

- 대상 논문: **Pufferfish: Container-driven Elastic Memory Management for Data-intensive Applications** (ACM SoCC 2019)
- 현재 실험 저장소: <https://github.com/gihyeon23/pufferfish-memory-lab>
- 가장 중요한 질문: 논문의 reclaim은 **새 컨테이너를 노드에 배치하려는데 메모리가 부족할 때** 실행되는 것으로 보이는데, 현재 계획된 호스트 사용량 임계값 기반 reclaim 데몬은 논문과 다른 실험 아닌가?

---

## 먼저 확인한 결론

논문에서 `reclaim()`은 단순히 호스트 메모리 사용률이 특정 임계값을 넘었다는 이유만으로 주기적으로 실행되지 않습니다.

논문 4.3.1절의 흐름은 다음과 같습니다.

1. Pufferfish가 노드에서 **새 컨테이너를 시작하기 전** 가용 메모리를 확인한다.
2. 새 컨테이너가 요구하는 메모리를 확보할 수 없으면 `reclaim()`을 호출한다.
3. 기존에 puff된 컨테이너 중 우선순위가 낮은 OCM 컨테이너부터 메모리를 회수한다.
4. 확보한 메모리로 새 컨테이너를 시작한다.
5. 다른 컨테이너가 종료되어 메모리를 반환하면 reclaim된 컨테이너를 다시 puff하고 resume할 수 있다.

논문은 이를 **lazy reclaim**으로 설명합니다. 즉, 노드 메모리가 새로 스케줄된 컨테이너를 수용하지 못할 때까지 reclaim을 미룹니다.

```text
호스트 사용률 임계값 초과
    ≠ 논문에 명시된 직접적인 reclaim 트리거

새 컨테이너 배치 요청
+ 새 컨테이너를 실행할 가용 메모리 부족
    = 논문의 reclaim 트리거
```

### REGULAR/FLEX 컨테이너 차이

- REGULAR 컨테이너가 5GB를 요청하면 Pufferfish는 5GB의 여유 공간을 확보해야 한다.
- FLEX 컨테이너는 최소 시작 크기인 `MIN_CONT`만큼의 공간을 확보하면 된다.
- 스케줄러 플러그인은 FLEX 컨테이너를 배치할 때 메모리가 부족해 요청을 만족할 수 없으면 무의미한 reclaim을 피하기 위해 요청을 지연할 수도 있다.

---

## 논문의 전체 동작 요약

### 1. 작은 물리 메모리 한도로 FLEX 컨테이너 시작

JVM의 최대 힙은 크게 설정하지만, 컨테이너의 실제 물리 메모리 한도는 작게 시작합니다. JVM은 큰 가상 힙을 사용할 수 있고, 실제 메모리는 수요에 따라 조절됩니다.

### 2. OCM 감지 및 suspend

논문은 대략 다음 조건으로 OCM(On-Container Memory pressure)을 식별합니다.

```text
memory usage + swap usage > container memory limit
AND
swapping activity 감지
```

OCM 컨테이너는 swapping과 GC로 호스트를 방해하지 않도록 CPU를 약 1%로 제한합니다. 작업을 죽이는 것이 아니라 heartbeat와 실행 상태를 유지한 채 사실상 정지시킵니다.

### 3. 여유 메모리가 있으면 puff

호스트에 여유 메모리가 있고 OCM 컨테이너가 더 많은 메모리를 요구하면 `puff()`로 컨테이너 메모리 한도를 증가시킵니다. 여러 OCM 컨테이너가 경쟁하면 EJF 또는 SJF 등의 우선순위 정책에 따라 처리합니다.

### 4. 새 컨테이너를 위한 메모리가 부족하면 reclaim

기존 FLEX 컨테이너가 여유 메모리를 받아 puff된 상태에서 새 컨테이너가 들어오면, Pufferfish는 필요한 공간을 확보하기 위해 기존 컨테이너의 메모리 한도를 줄이고 일부 페이지를 swap으로 내보냅니다.

논문의 Figure 6(b)에서는 KMeans FLEX 컨테이너와 TPC-H REGULAR 컨테이너를 함께 실행합니다. 새로운 TPC-H 작업들이 들어오자 FLEX 컨테이너가 약 `58GB → 40GB → 32GB`로 reclaim되고, 이 메모리로 REGULAR 컨테이너들을 실행합니다.

---

## 현재 저장소 구현

### `controller/container_monitor.py`

현재 자동 흐름은 다음과 같습니다.

```text
500ms 주기 cgroup 상태 확인
→ OCM 감지
→ puff(container) 시도
→ CPU 1% suspend
```

현재 OCM 판정은 다음 조건입니다.

```text
(memory.current + memory.swap.current > memory.max)
AND
(swap activity OR swap 포화)
```

`swap_current >= swap_max × 0.95` 조건은 swap이 이미 포화되어 delta가 0으로 굳는 blind spot을 해결하기 위해 재현 실험에서 추가한 조건입니다. 논문 원문 그대로가 아니라 cgroup v2 실험에서 발견된 보완입니다.

중요한 점은 `container_monitor.py`가 `reclaim_host()`를 자동 호출하지 않는다는 것입니다.

### `controller/puff_manager.py`

구현된 함수는 다음과 같습니다.

- `puff(container)`: 현재 한도의 기본 40%만큼 증가한다. 다만 컨테이너 한도 합이 호스트 메모리의 80%를 넘지 않도록 제한한다.
- `reclaim(container, amount_mb)`: 해당 컨테이너의 한도를 줄이되 최초 한도 아래로 내리지 않는다.
- `reclaim_host(target_free_mb)`: 목표 여유 메모리가 확보될 때까지 여러 puff 컨테이너에서 회수한다.

현재 `reclaim()`과 `reclaim_host()`는 CLI에서 수동으로 실행할 수 있지만, 논문의 신규 컨테이너 배치 경로와 연결되어 있지 않습니다.

```bash
python3 controller/puff_manager.py reclaim-host --target-free-mb 500
```

### 현재 3차 다중 컨테이너 실험

현재 실험은 다음 흐름입니다.

```text
컨테이너 3개 실행
→ 각각 OCM 발생 및 반복 puff
→ 세 컨테이너 memory.max 합이 호스트 예산 80%에 도달
→ 한 컨테이너의 puff가 거절됨
→ 자동 reclaim이 없어서 해당 컨테이너 OOM-kill
```

이 실험은 다음을 검증하는 데 의미가 있습니다.

- 다중 컨테이너의 puff 경쟁
- 호스트 예산 제한
- OCM 감지 및 swap 포화 보완 로직
- 자동 reclaim이 없을 때의 OOM 발생

하지만 이것만으로는 논문의 reclaim 시나리오를 그대로 재현했다고 보기 어렵습니다. 논문의 핵심은 **새 컨테이너 admission 요청이 기존 FLEX 컨테이너의 reclaim을 유발하는 것**이기 때문입니다.

---

## 현재 제안된 호스트 reclaim 데몬과 논문의 차이

현재 다음과 같은 별도 데몬이 제안된 상태입니다.

```text
호스트 메모리 또는 memory.max 배정량을 주기적으로 확인
→ 사용량이 85~90% 같은 임계값을 넘으면
→ reclaim_host(target_free_mb) 호출
```

이 방식은 OOM을 예방하기 위한 실험용 정책으로는 타당할 수 있습니다. 그러나 논문의 reclaim 트리거를 그대로 구현한 것은 아닙니다.

| 구분 | reclaim 트리거 | 성격 |
|---|---|---|
| Pufferfish 논문 | 새 컨테이너 배치 요청을 만족할 메모리가 부족할 때 | 논문 원형의 lazy reclaim |
| 제안된 호스트 데몬 | 호스트 사용량 또는 할당량이 임계값을 넘을 때 | 선제적·주기적 확장 정책 |
| 현재 저장소 | 사용자가 CLI를 직접 실행할 때 | 함수 단위 수동 검증 |

따라서 호스트 임계값 데몬을 구현한다면, 논문 재현 부분과 분리하여 **추가적인 proactive reclaim 정책**이라고 명시해야 합니다.

---

## reclaim 대상 선정 정책의 차이도 확인 필요

논문 본문에서는 낮은 우선순위의 OCM 컨테이너부터 reclaim한다고 설명합니다. 기본 EJF 정책이라면 오래된 작업이 높은 우선순위를 가지므로, 새 작업이나 낮은 우선순위 작업이 먼저 불이익을 받을 수 있습니다.

반면 현재 `reclaim_host()`는 상태 파일 수정 시간을 기준으로 **가장 최근에 puff된 컨테이너부터** 회수합니다.

```text
논문: 낮은 우선순위 OCM 컨테이너부터 reclaim
현재 코드: 가장 최근에 puff된 컨테이너부터 reclaim
```

이 정책이 논문 저자의 공개 YARN 구현을 단순화해 옮긴 결과인지, 현재 실험에서 독자적으로 선택한 정책인지 확인해야 합니다. 논문의 EJF/SJF를 재현하려면 작업 도착 시간, 예상 종료 시간, OCM 여부 등 별도의 우선순위 정보가 필요합니다.

---

## 논문에 가까운 다음 실험 제안

다음과 같은 admission 기반 실험을 먼저 수행하는 것이 좋습니다.

```text
1. pf-flex 실행
2. pf-flex에서 OCM 유도
3. 호스트 여유 메모리로 pf-flex를 여러 번 puff
4. 새로운 pf-regular 컨테이너 실행 요청
5. pf-regular의 요청 메모리와 현재 가용 메모리 비교
6. 부족하면 기존 pf-flex에 reclaim 실행
7. 필요한 메모리가 확보되면 pf-regular 실행
8. pf-regular 종료 후 pf-flex를 다시 puff/resume
```

실험용 admission wrapper의 개념은 다음과 같습니다.

```python
def launch_container(request_memory_mb):
    free_mb = host_total_mb - get_host_assigned_mb()

    if free_mb < request_memory_mb:
        reclaim_host(target_free_mb=request_memory_mb)

    # 목표 메모리가 실제로 확보됐는지 다시 확인한 뒤 실행
    docker_run(...)
```

이 구조에서는 reclaim 판단을 개별 `container_monitor.py`에 넣기보다, 컨테이너 실행과 전체 노드 메모리를 관리하는 NodeManager 역할의 호스트 레벨 컴포넌트에 두는 것이 자연스럽습니다. 다만 이는 `주기적 임계값 데몬`이 아니라 **컨테이너 admission 이벤트에 연결된 호스트 레벨 관리자**여야 논문의 흐름과 일치합니다.

---

## Claude에게 요청할 검토 사항

첨부한 논문 원문과 현재 저장소 전체를 다시 확인하고 아래 질문에 답해주세요.

1. 논문에서 `reclaim()`이 호출되는 정확한 조건과 호출 주체를 본문·알고리즘·저자 구현 근거로 확인해주세요.
2. 신규 컨테이너 admission이 논문의 직접적인 reclaim 트리거라는 해석이 맞는지 검증해주세요.
3. 호스트 사용량 임계값 기반 데몬이 논문에 실제로 존재하는지, 아니면 현재 Docker 실험을 위한 별도 정책인지 구분해주세요.
4. 현재 `container_monitor.py`, `puff_manager.py`, `03-multi-container-reclaim.md`가 논문과 일치하는 부분과 다른 부분을 파일 및 코드 위치 기준으로 표로 정리해주세요.
5. 현재 `reclaim_host()`의 “최근 puff 우선” 정책과 논문의 “낮은 우선순위 OCM 컨테이너 우선” 설명이 왜 다른지 저자 공개 구현까지 확인해주세요.
6. 논문 재현을 우선한다면 다음 구현을 아래 중 무엇으로 잡아야 하는지 판단해주세요.
   - 신규 컨테이너 실행 전에 메모리를 확인하는 admission wrapper
   - 주기적으로 호스트 임계값을 확인하는 reclaim 데몬
   - 두 방식을 분리해 각각 논문 재현과 확장 정책으로 구현
7. 구현 변경 전, 수정 대상 파일과 실험 절차를 먼저 제안하고 아직 코드는 수정하지 마세요.

답변할 때는 반드시 다음을 구분해주세요.

- 논문에 명시된 사실
- 논문 저자의 공개 구현에서 확인한 사실
- 현재 저장소에 구현된 사실
- Docker/cgroup v2 환경을 위한 해석 또는 제안
- 확실하지 않아 추가 검증이 필요한 내용

