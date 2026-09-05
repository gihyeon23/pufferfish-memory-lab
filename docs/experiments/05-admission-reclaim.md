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
     (`puff_manager.get_host_free_mb()`, budget 기준 — 아래 "발견된 버그"
     참고)를 비교
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

## 발견된 버그: budget 계산 불일치 (라이브 테스트에서 발견, 수정 완료)

실제 3개 컨테이너를 puff시켜 호스트 할당량을 정확히 `budget(=host_total×
HOST_STOP_RATIO=0.8)`까지 채운 뒤 `admission.py`를 실행했더니, 이미
`assigned=3119MiB=budget`(사실상 puff가 더는 못 늘리는 한계)인데도
"여유 충분(free=780MiB)"이라고 판단해 reclaim을 한 번도 안 부르는 문제를
발견했다.

원인: `admission.py`(및 `puff_manager.reclaim_host()`)가 여유를 계산할 때
`host_total - assigned`(raw 100% 기준)를 썼다 — `puff()`가 스스로 멈추는
기준인 `HOST_STOP_RATIO=0.8` budget과 다른 천장이었다. 그 결과 puff는
80%에서 거부되기 시작하는데 reclaim/admission은 100%까지는 "괜찮다"고
판단하는 모순이 생겼다.

수정: `puff_manager.get_host_budget_mb()`/`get_host_free_mb()`를 신설해
`reclaim_host()`와 `admission.py`의 `free_mb()`가 모두 budget 기준으로
통일하도록 고쳤다. monkeypatch로 `assigned==budget`(3119MiB) 상황을
재현해, 수정 전 `free_mb()=780MiB`(오판) → 수정 후 `free_mb()=0MiB`
(정확)로 바뀌는 것을 확인했다.

수정 후 실제 CLI로도 재현: 컨테이너 3개(`--memory=900m`)를 띄우고 2개를
puff시켜 `assigned=budget=3119MiB`(free=0)를 만든 뒤
`admission.py pf-fix-new alpine --request-mb 200` 실행 —

```
[admission] 여유 부족 (free=0MiB < request=200MiB) -> reclaim_host 호출
[puff_manager] pf-fix-b: reclaim 적용 959MiB -> 900MiB (회수 59MiB)
[puff_manager] pf-fix-b: 원래 한도로 완전히 복구되어 puff 상태 해제
[puff_manager] pf-fix-a: reclaim 적용 1260MiB -> 1119MiB (회수 141MiB)
[admission] reclaim 200MiB 회수, reclaim 후 여유 200MiB
[admission] 실행: docker run -d --name pf-fix-new --memory 200m ...
[admission] 컨테이너 시작됨: 7ec78f36...
```

`pf-fix-b`(더 나중에 생성됨)가 EJF 순서대로 먼저 reclaim되고, 부족분은
`pf-fix-a`에서 마저 회수해 정확히 200MiB를 확보한 뒤 신규 컨테이너가
정상 실행됐다. 테스트 컨테이너는 종료 후 정리했다.

## 확인 포인트

- [x] 호스트 여유가 충분할 때: reclaim 호출 없이 바로 컨테이너가 뜨는지
      (2개 컨테이너만 puff한 상태 — `free=599MiB >= request=200MiB` —
      에서 reclaim 없이 바로 실행되는 것을 확인)
- [x] 호스트 여유가 부족할 때(기존 컨테이너들을 먼저 puff시켜 예산을 채운 뒤):
      `admission.py`가 `reclaim_host()`를 호출해 여유를 만들고 나서 컨테이너를
      띄우는지 — 위 "발견된 버그" 절의 재현 로그로 확인
- [ ] reclaim 후에도 여유가 부족하면 경고 로그를 남기고 그래도 실행되는지
      (admission 지연을 구현하지 않았으므로 의도된 동작) — 아직 직접 재현 안 함
- [ ] 04번 데몬과 동시에 띄워도 서로 충돌 없이 동작하는지 (둘 다
      `reclaim_host()`를 호출할 뿐 상태를 공유하므로 원칙적으로는 안전할 것으로
      예상 — 실습에서 확인 필요)

## 상태

라이브 테스트(3개 컨테이너 puff → budget 도달 → admission 시도)로 budget
계산 불일치 버그를 발견·수정하고, 수정된 코드로 "여유 충분"/"여유 부족 →
reclaim 트리거" 두 경로 모두 실제 CLI로 재검증 완료. 남은 건 admission
지연 동작과 04번 데몬과의 동시 실행 확인.
