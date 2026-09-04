# 5차: admission 기반 reclaim (논문 재현)

## 목적

04번 데몬(`host_reclaim_daemon.py`)은 호스트 사용률 임계값을 상시 폴링하는
방식으로, Pufferfish 논문의 실제 reclaim 트리거와 다르다는 것을 지난 대화에서
확인했다([docs/pufferfish-architecture.md](../pufferfish-architecture.md) 참고).
논문은 reclaim()을 **"새 컨테이너를 노드에 배치하려는데 가용 메모리가 부족할
때"**만 호출하는 lazy reclaim이다(§4.3.1, p.263-264). 이 실습은 그 admission
경로를 실제로 재현한다.

## 설계

- `controller/admission.py` 신설 — `docker run`을 감싸는 래퍼.
  1. 요청 메모리(`--request-mb`)와 현재 호스트 가용 메모리
     (`host_total - get_host_assigned_mb()`)를 비교
  2. 부족하면 `puff_manager.reclaim_host()` 호출 (이미 검증된 함수 재사용,
     cgroup 직접 조작 없음 — 04번과 동일한 원칙)
  3. 확보된 여유로 `docker run` 실행
- **04번과의 차이**: 04번은 admission 이벤트 없이 5초마다 상시 감시하며 90%
  넘으면 트리거. 이 스크립트는 오직 "새 컨테이너 요청" 시점에만 reclaim을
  시도한다(그 외에는 절대 호출 안 됨 — 지난 대화에서 확인한 "논문은 %에
  도달해도 admission 요청이 없으면 reclaim 안 한다"는 지점을 그대로 구현).
- **의도적으로 생략한 것**: 논문 4.3.2의 스케줄러 플러그인이 하는 "admission
  지연(delay)" — reclaim 후에도 여유가 부족하면 요청을 큐에 쌓고 기다리는
  로직. 단일 호스트, 컨테이너 몇 개뿐인 이 실습 규모에서는 과한 설계라
  생략하고, 대신 경고 로그만 남기고 그대로 실행한다.
- **우선순위 정책 한계**: 논문은 최저 우선순위 OCM 컨테이너부터 회수하지만
  (EJF/SJF), 이 프로젝트는 우선순위 개념이 없어 `reclaim_host()`의 기존 정책
  ("가장 최근에 puff된 컨테이너부터")을 그대로 물려받는다. 03/04 실습과 동일한
  한계이며 별도 개선 과제로 남긴다.

## 실행 방법

```bash
cd controller
rm -f state/*.json

# 기존 컨테이너를 puff시켜 호스트 예산을 채운 상태를 만든 뒤 (예: 03 실습처럼
# pf-test-1/2/3을 여러 번 puff), 신규 컨테이너 admission을 시도
python3 admission.py pf-test-4 pufferfish/workload-java:latest \
  --request-mb 512 \
  --env CHUNK_SIZE_MB=32 --env INTERVAL_SECONDS=2 --env MAX_ALLOCATION_MB=512 \
  --env JAVA_OPTS="-Xmx600m"
```

여유가 이미 충분하면 `reclaim` 없이 바로 `docker run`만 실행되는 로그를
확인할 수 있고, 부족하면 `reclaim_host` 호출 로그가 먼저 찍힌 뒤 실행된다.

## 확인 포인트

- [ ] 호스트 여유가 충분할 때: reclaim 호출 없이 바로 컨테이너가 뜨는지
- [ ] 호스트 여유가 부족할 때(기존 컨테이너들을 먼저 puff시켜 예산을 채운 뒤):
      `admission.py`가 `reclaim_host()`를 호출해 여유를 만들고 나서 컨테이너를
      띄우는지
- [ ] reclaim 후에도 여유가 부족하면 경고 로그를 남기고 그래도 실행되는지
      (admission 지연을 구현하지 않았으므로 의도된 동작)
- [ ] 04번 데몬과 동시에 띄워도 서로 충돌 없이 동작하는지 (둘 다
      `reclaim_host()`를 호출할 뿐 상태를 공유하므로 원칙적으로는 안전할 것으로
      예상 — 실습에서 확인 필요)

## 상태

구현·`py_compile` 확인만 끝났고, 실제 다중 컨테이너 경쟁 상황에서 admission
트리거가 의도대로 동작하는지는 아직 검증 전이다.
