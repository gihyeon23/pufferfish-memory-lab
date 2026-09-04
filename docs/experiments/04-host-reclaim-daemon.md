# 4차: 호스트 레벨 자동 reclaim 데몬

## 목적

3차 실습에서 확인했듯, `puff()`가 호스트 예산 부족으로 거부된 뒤에도 아무도
`reclaim`을 호출해주지 않으면 압박받는 컨테이너가 그대로 OOM-kill당한다
(`pf-test-2` 사례, [03-multi-container-reclaim.md](03-multi-container-reclaim.md)
참고). `reclaim`/`reclaim_host` 자체는 이미 구현·검증돼 있으니, 남은 건
"언제 자동으로 부를지" 트리거뿐이다. 이 트리거를 `controller/
host_reclaim_daemon.py`로 구현했다.

## 설계

- **cgroup을 직접 건드리지 않는다.** `puff_manager.get_host_assigned_mb()`,
  `get_host_memory_total_mb()`, `reclaim_host()`를 그대로 재사용하는
  폴링 루프일 뿐이다.
- **컨테이너 하나가 아니라 호스트 전체를 본다.** `container_monitor.py`는
  컨테이너마다 하나씩 띄워서 500ms 주기로 그 컨테이너의 급격한 순간 위기
  (OCM)를 감시하는 반면, 이 데몬은 호스트당 하나만 띄워서 여러 컨테이너에
  걸친 누적 추세(호스트 예산 소진)를 좀 더 느슨한 주기(기본 5초)로 감시한다.
- **`RECLAIM_TRIGGER_RATIO=0.9`** — `puff()`가 스스로 멈추는 기준
  (`HOST_STOP_RATIO=0.8`)보다 일부러 더 빡빡하게 잡았다. 두 기준이 같으면
  puff가 막 거부되기 시작하는 순간에 reclaim도 동시에 걸려서 서로 왔다갔다
  (thrashing)할 수 있기 때문이다.
- **`RECLAIM_TARGET_FREE_MB=300`** — 한 번 reclaim할 때 확보하려는 최소 여유.
  값이 작으면 자주 조금씩, 크면 드물게 크게 회수한다.

## 실행 방법

```bash
cd controller
python3 host_reclaim_daemon.py --interval 5
```

3차 실습([03-multi-container-reclaim.md](03-multi-container-reclaim.md))처럼
컨테이너 여러 개 + `container_monitor.py`를 각각 띄운 상태에서, 이 데몬을
추가로 하나 더 백그라운드로 띄우면 된다.

```bash
python3 host_reclaim_daemon.py --interval 5 > host-reclaim.log 2>&1 &
```

## 확인 포인트 (다음 실습에서 검증)

- [ ] 3개 컨테이너를 다시 경쟁 상황까지 밀어붙였을 때, `puff()`가 거부되기
      전에(또는 거부되자마자) 데몬이 먼저 `reclaim_host()`를 호출하는지
- [ ] 그 결과로 3차에서 죽었던 `pf-test-2` 같은 케이스가 이번엔 안 죽고
      살아남는지
- [ ] `RECLAIM_TRIGGER_RATIO`/`RECLAIM_TARGET_FREE_MB`가 너무 빡빡하거나
      느슨해서 의미 없는 결과가 나오지 않는지 (필요하면 값 튜닝)

## 상태

구현·컴파일 확인(`python3 -m py_compile`)만 끝났고, 실제 다중 컨테이너
경쟁 상황에서의 동작 검증은 아직 하지 않았다.

## ⚠️ 논문과의 관계 (중요, 2026-09-04 수정)

**이 데몬은 Pufferfish 논문의 reclaim 메커니즘을 재현한 것이 아니다.**
논문(§4.3.1, p.263~264, 자세한 근거는
[docs/pufferfish-architecture.md](../pufferfish-architecture.md#reclaim-p263264--가장-중요한-트리거-조건))에서
`reclaim()`은 **신규 컨테이너를 노드에 배치하려는 요청이 있는데 가용 메모리가
부족할 때**(lazy reclaim) 호출된다. 호스트 사용률이 어떤 임계값을 넘었다고
주기적으로 폴링해서 reclaim을 도는 메커니즘은 논문에 없다.

이 데몬(`RECLAIM_TRIGGER_RATIO=0.9` 초과 시 폴링으로 트리거)은 이 프로젝트가
3차 실습에서 실제로 관찰한 "puff 거부 후 아무도 reclaim을 안 불러줘서
OOM-kill" 문제를 막기 위해 **독자적으로 설계한 OOM 예방용 확장 정책**이다.
동작 자체가 잘못된 건 아니지만, 논문 재현 실습으로 착각하면 안 된다.

논문에 맞게 재현하려면 별도로 "컨테이너 admission 시점에 가용 메모리를
확인하고, 부족하면 reclaim_host()를 호출한 뒤 컨테이너를 실행하는" wrapper가
필요하다 — 이 방향의 구체적 설계는
[docs/papers/pufferfish-reclaim-review-context.md](../papers/pufferfish-reclaim-review-context.md)에
제안돼 있음(아직 미구현).
