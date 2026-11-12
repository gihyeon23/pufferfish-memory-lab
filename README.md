# Pufferfish Memory Lab

Pufferfish 논문의 메모리 관리 동작(OCM 감지 → suspend → puff → shrink/reclaim)을
**원 저자 코드와 논문 환경으로 재현**하는 프로젝트입니다.

> **Pufferfish: Container-driven Elastic Memory Management for Data-intensive Applications** (ACM SoCC 2019)

## 목표

- 연구실 x86 VM에서 원 저자 코드(YARN 2.7.3)로 논문 실험을 재현
- 기준: **논문 그래프(Fig 6)와 같게**. 조건은 논문에 적힌 내용이 1순위 (2026-11-12 결정)
- 원 코드가 논문 설명과 다른 곳은 논문대로 고치고, 고친 곳을 한 줄씩 기록
  — 진행 순서: [steps/17](original-hadoop2.7/x86-server/steps/17-paper-aligned-plan.md)

## 현재 상태

- worker1 단일 노드에서 **Fig 6(a) (puff)** 재현 중
- 원 코드 그대로 결과(steps 09~16)를 비교 기준으로 확보
- 논문 기준 수정 단계 A (shrink 대기 2분) 실행 중
- 다음: kill 기준 → shrink 여유분 → reclaim 대상 → puff 상한 → Fig 6(b)(c) → 3대 클러스터

## 실험 환경

| | 논문 [p.265] | 우리 (규모 1/4) |
|---|---|---|
| 노드 | 26대, 128GB, 16코어 | x86 VM 3대: master 8GB, worker ×2 각 32GB·8 vCPU |
| OS · 컨테이너 | Ubuntu 16.04, Docker 1.12.1, cgroup v1 | 같음 |
| YARN | Pufferfish (YARN 2.7.3 기반) | 원 저자 공개 코드 |
| 워크로드 | HiBench (PageRank, KMeans 등) | HiBench 6.0 + Spark 2.0.1, 데이터 1/4 |

- 축소 근거: [steps/01](original-hadoop2.7/x86-server/steps/01-cluster-spec-and-scaling.md),
  논문에 없어 우리가 정한 값: [assumptions-review.md](original-hadoop2.7/x86-server/assumptions-review.md)

## 프로젝트 구조

| 폴더 | 내용 | 상태 |
|---|---|---|
| [original-hadoop2.7/](original-hadoop2.7/) | **메인** — 원 저자 코드 + 논문 환경. `x86-server/`(정식), `arm-mac/`(연습) | 진행 중 |
| [common/](common/) | 논문·분석 요약([pufferfish-architecture.md](common/pufferfish-architecture.md)), 랩미팅 자료, [작업 분담](common/work-split.md) | — |
| [reimpl-single-node/](reimpl-single-node/) | 맥 VM에서 Python으로 직접 재구현 (실험 1~10차) | 완료 |
| [reimpl-hadoop3/](reimpl-hadoop3/) | Hadoop 3.5.0 + 외부 데몬 방식 | 중단 (원 코드 재현으로 전환) |

## 진행 흐름

1. **2026-09** 맥 VM에서 논문 메커니즘을 Python으로 직접 구현 → `reimpl-single-node/`
2. **2026-10** 최신 Hadoop 3 연결 시도 → 원 코드 재현이 더 정확해 중단
3. **2026-10** 원 저자 코드를 맥(ARM)에서 빌드·연습 → x86 VM 수령 후 정식 실험
4. **2026-11** Fig 6(a) 조건별 실험 → 논문 기준으로 코드 맞추기 시작
