# 6차: EJF 우선순위 기반 reclaim 대상 선정

## 목적

`puff_manager.reclaim_host()`가 지금까지 쓰던 "가장 최근에 puff된 컨테이너부터"
(state 파일 mtime 기준) 휴리스틱을 논문 기본 정책인 **EJF(Earliest Job
First)**로 교체한다. 논문(§4.3.3, p.264)은 다음과 같이 서술한다.

> "Earliest Job First (EJF) policy prioritizes containers based on the
> arrival time of the job that the containers belong to. This is the
> default policy in Pufferfish. Its rationale is that the oldest job may
> release memory first."

즉 **가장 먼저 도착(생성)한 컨테이너가 최고 우선순위**(보호 대상)이고,
**가장 나중에 도착한 컨테이너부터 reclaim** 대상이 되어야 한다. mtime(puff
시각) 기준은 "언제 puff됐는가"이지 "언제 도착했는가"가 아니므로 논문의
우선순위 정책과 다르다.

## 설계

- 컨테이너의 "도착 시각" = `docker inspect --format '{{.Created}}'`
  (RFC3339 문자열, `cgroup_utils.docker_inspect()` 재사용)
- `puff_manager._sort_reclaim_candidates_ejf()`: reclaim 후보 state 파일들을
  컨테이너 생성 시각 기준 **내림차순**(가장 최근에 생성된 것 먼저) 정렬
  - RFC3339 문자열은 사전순 정렬이 시간순 정렬과 일치하므로 별도 파싱 없이
    문자열 비교로 정렬 가능
  - 컨테이너가 이미 종료/삭제돼 생성 시각을 못 가져오면(`docker inspect`
    실패) 그 state 파일을 정리(삭제)하고 후보에서 제외 — 기존에는 이 경우
    `reclaim()` 호출 시 크래시할 수 있었던 부수적 버그도 같이 막았다.
- `reclaim_host()`는 정렬만 이 함수로 교체, 나머지 루프(목표 여유 확보될
  때까지 순서대로 reclaim)는 그대로.
- `admission.py`/`host_reclaim_daemon.py`는 `reclaim_host()`를 그대로
  호출하므로 별도 수정 없이 새 정책을 자동으로 물려받는다.

## 실행 방법 (검증에 쓴 시나리오)

```bash
cd controller
docker run -d --name pf-ejf-1 --memory=64m --memory-swap=192m alpine sleep 600
sleep 2
docker run -d --name pf-ejf-2 --memory=64m --memory-swap=192m alpine sleep 600
sleep 2
docker run -d --name pf-ejf-3 --memory=64m --memory-swap=192m alpine sleep 600

# 창생 순서(1→2→3)와 반대로 puff시켜서, mtime 기준과 EJF 기준이
# 서로 다른 컨테이너를 고르도록 만든다
python3 puff_manager.py puff pf-ejf-3
sleep 1
python3 puff_manager.py puff pf-ejf-2
sleep 1
python3 puff_manager.py puff pf-ejf-1

python3 -c "
from puff_manager import reclaim_host, get_host_assigned_mb, get_host_memory_total_mb
free = get_host_memory_total_mb() - get_host_assigned_mb()
reclaim_host(target_free_mb=free + 20)
"
```

## 확인 포인트

- [x] mtime 기준(구 로직)이라면 `pf-ejf-1`(가장 최근에 puff됨)이 선택돼야
      하는데, 실제로는 EJF 기준으로 `pf-ejf-3`(가장 최근에 **생성**된
      컨테이너, 최저 우선순위)이 선택되는지
- [x] 종료된 컨테이너의 stale state 파일이 크래시 없이 정리되는지 (직접
      재현은 안 했지만 로직상 `docker inspect` 실패 시 `unlink` 후 `continue`
      하도록 구현)
- [ ] 실제 admission.py/host_reclaim_daemon.py 경로를 통한 통합 검증 (5차/4차
      라이브 검증과 함께 진행 예정)

## 검증 결과

3개 컨테이너(`pf-ejf-1/2/3`, 생성 순서 1→2→3)를 창생 순서와 반대로(3→2→1)
puff시켜 state 파일 mtime 순서를 창생 순서와 어긋나게 만든 뒤
`reclaim_host()`를 호출했다.

```
[puff_manager] pf-ejf-3: reclaim 적용 89MiB -> 69MiB (회수 20MiB)
```

mtime 기준(구 로직)이었다면 가장 최근에 puff된 `pf-ejf-1`이 선택됐어야
하지만, 실제로는 가장 최근에 **생성**된 `pf-ejf-3`이 정확히 reclaim
대상으로 선정됐다 — EJF 정책이 의도대로 동작함을 확인했다.

테스트에 쓴 컨테이너와 state 파일은 검증 직후 정리했다
(`docker rm -f pf-ejf-1 pf-ejf-2 pf-ejf-3`, `rm -f controller/state/pf-ejf-*.json`).
