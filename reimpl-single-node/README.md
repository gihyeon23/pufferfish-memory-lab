# reimpl-single-node — Python controller 재구현 (완료)

논문의 노드 레벨 메커니즘(OCM 감지, CPU 1% suspend, puff/reclaim, admission 시점 lazy reclaim, EJF)을
Python controller로 직접 구현해 단일 호스트(Docker + cgroup v2)에서 검증했다.

| 폴더 | 내용 |
|---|---|
| [controller/](controller/) | cgroup 모니터·suspend·puff/reclaim·admission — 반드시 `cd reimpl-single-node/controller` 후 실행 |
| [workload-java/](workload-java/) | 메모리를 점진적으로 늘리는 Java 워크로드 + 이미지 |
| [experiments/](experiments/) | 1~10차 실행 방법·검증 결과 (인덱스: [experiments/README.md](experiments/README.md)) |
| [evidence/](evidence/) | 원본 로그 등 검증 근거 |
| [experiments/swap-off-latency/](experiments/swap-off-latency/) | 9/21 랩미팅 swap 차단 실험 (발표 자료는 로컬 `common/lab-meetings/2026-09-21/`) |

- 7차(다중 노드 설계)는 [reimpl-hadoop3/docs/](../reimpl-hadoop3/docs/)로 옮김
