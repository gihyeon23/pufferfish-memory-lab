# 17. 논문 기준으로 전환 — 진행 순서 (2026-11-12)

## 결정 (교수님 논의)

- 기준: **논문 Fig 6(a) 그래프와 같게**. 조건은 논문 명시 내용이 1순위
- 논문에 맞춰 원 코드를 고친 결과 = **본 결과**. 원 코드 그대로(09~16)는 비교용
- executor **1코어** 확정. 입력은 논문 Table 1 비율(PR 2배 안 씀)

## 방법

원 코드에서 논문과 다른 곳을 **하나씩** 논문대로 고침 → 실행 → 논문 그래프와 비교. 앞 단계 수정은 유지(누적).

- 시작점: 14 (원 코드, 1코어, 제출 0초, puff 2초, 4회)
- 비교 지표 (`setup/fig6a-metrics.py`): PR이 가장 크고 오래 / stop 전 shrink 수 / kill 수 (논문 1) / 전체 시간 (논문 약 1790초)

## 순서

경로 접두어 `hadoop-yarn-server-nodemanager/.../nodemanager/`. 상세 [architecture §2](../../../common/pufferfish-architecture.md)

| 단계 | 고칠 곳 | 논문 | 원 코드 | 기대 변화 | 이유 (순서) |
|---|---|---|---|---|---|
| A | shrink 대기 | e.g. 2분 [p.264] | 약 18초 (`NodeMemoryManager.java:102, 166-177`) | stop 전 shrink 감소 | 그래프 차이 가장 큼, 패치 있음 (11·16) |
| B | kill 기준 (suspension tolerance) | job 예상 기간의 절반 [p.264] | 고정 라운드 `SWAP_KEEP_TIME*2` (`:298`) | kill 수 감소 | 남은 가장 큰 차이 (16: kill 10 vs 논문 1) |
| C | shrink 여유분 | +2GB [p.264] | ×1.1 (`ContainerImpl.java:663, 1204, 1217`) | shrink 뒤 크기 | 그래프 점선 높이 |
| D | reclaim 대상 | 최저 우선순위부터 [p.264] | 균등 분할 | 어느 job이 줄어드는지 | 새 job 시작 때만 영향 |
| E | puff 상한·정지 | M 기준, 메모리 소진 시 [p.264 Alg.1] | M×0.8, 할당 0.8에서 정지 | puff 최대 크기 | 영향 작을 것 **추측** |

## 단계마다 정할 것 (사용자)

- 반복 횟수
- A: 라운드 수 (2초 주기 → 약 60), B와 분리할지
- B: "job 예상 기간"을 무엇으로 줄지 (논문 설명 없음 → [우리])
- C: 2GB 그대로 / 규모 1/4로 512MB

## 단계 A 실행 (worker1)

- 패치 소스 `~/legacy/setup/NodeMemoryManager.java` (= `setup/patches/swap-keep-time.diff`: 59, kill 10 고정)
- `bash ~/legacy/setup/patch-nm-timing.sh ~/legacy/setup/NodeMemoryManager.java` → NM 재시작
- NM 재시작 후 **10분 대기**: 옛 NM(이전 포트)이 RM 목록에서 빠질 때까지 (`hadoop.sh status` 노드 1줄 확인)
- `nohup bash -c 'for i in 1 2 3 4; do bash ~/legacy/setup/fig6a.sh 0 > ~/hibench-logs/stepA-$i.out 2>&1; sleep 60; done; touch ~/hibench-logs/stepA.done' >/dev/null 2>&1 &`
- 누적이라 끝나도 jar 되돌리지 않음

## 진행 기록

| 단계 | 결정 | 실행 | 결과 문서 |
|---|---|---|---|
| A | 4회 (11-12) | | |
