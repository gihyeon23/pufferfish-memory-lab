# reimpl-hadoop3 — 최신 Hadoop YARN 클러스터 (⏸ 중단)

> **중단 (2026-10-11)**: 10/7 피드백("외부 데몬 대신 원 코드 활용")에 따라 원 저자 코드 재현으로 전환 →
> [original-hadoop2.7/](../original-hadoop2.7/)

VM 3대(control 1 + worker 2)에 JDK 17 + Hadoop 3.5.0 YARN을 올리고, reimpl-single-node의 controller를
외부 데몬(A안)으로 연결하려던 2단계 로드맵.

| 폴더 | 내용 |
|---|---|
| [docs/07-multi-node-cluster.md](docs/07-multi-node-cluster.md) | 다중 노드 초기 설계 (SSH 기반, 원래 실험 7차) |
| [steps/](steps/) | Step 0~3 기록 (로드맵·발표 메모는 로컬 `common/lab-meetings/2026-10-05/`) |
| [configs/hadoop/](configs/hadoop/) | Step 2~3 Hadoop 3.5.0 설정 원본 |

- 완료: Step 0 기준선, Step 1 VM 3대, Step 2 HDFS, Step 3 YARN + pi 5/5
- 미진행: Step 4~9 (Spark, HiBench, controller 연결, 비교)
- VM `pf-*` 3대는 그대로 보존
