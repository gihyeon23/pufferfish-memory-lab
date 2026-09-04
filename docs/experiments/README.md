# 실험 목록

각 실험의 목적, 실행 명령어, 검증 결과를 담은 문서다. 새 실험을 시작하면
`0N-짧은-이름.md` 형식으로 파일을 추가하고 이 목록에 링크를 더한다.

| 순서 | 문서 | 내용 | 상태 |
|---|---|---|---|
| 1차 | [01-ocm-suspend.md](01-ocm-suspend.md) | OCM(On-Container Memory pressure) 감지 시 CPU 1% 제한 | 완료 |
| 2차 | [02-puff-reclaim-single.md](02-puff-reclaim-single.md) | 단일 컨테이너에서 `puff()`/`reclaim()` 동작·자동 트리거 검증 | 완료 |
| 3차 | [03-multi-container-reclaim.md](03-multi-container-reclaim.md) | 다중 컨테이너 환경에서 `reclaim_host()` 우선순위 검증 | 부분 완료 (OCM 감지 버그 발견·수정, `reclaim-host` 자동 트리거는 미구현) |
| 4차 | [04-host-reclaim-daemon.md](04-host-reclaim-daemon.md) | 호스트 예산 부족 시 자동으로 `reclaim_host()`를 호출하는 감시 데몬 (⚠️ 논문 재현 아님, 이 프로젝트의 독자 확장 정책 — [pufferfish-architecture.md](../pufferfish-architecture.md) 참고) | 구현 완료 (실습 검증 필요) |
| 5차 | [05-admission-reclaim.md](05-admission-reclaim.md) | 신규 컨테이너 admission 시점에만 `reclaim_host()`를 호출하는 `admission.py` — 논문 §4.3.1의 실제 reclaim 트리거(lazy reclaim) 재현 | 구현 완료 (실습 검증 필요) |
| 6차 | [06-priority-reclaim.md](06-priority-reclaim.md) | `reclaim_host()`의 대상 선정을 "최근 puff순"에서 논문 기본 정책 EJF(가장 나중에 생성된 컨테이너부터)로 교체 | 완료 |

공통 실행 환경(호스트/VM 스펙)은 [`docs/environment.md`](../environment.md)에
정리돼 있다.
