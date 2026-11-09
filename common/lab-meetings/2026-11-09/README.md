# 2026-11-09 랩미팅 — Fig 6(a) 조건별 비교

- PPT: [fig6a-conditions.pptx](fig6a-conditions.pptx) (16장, 발표자 노트 포함)
- 다른 AI에게 맡길 때: 이 README + 아래 문서를 읽고 같은 흐름으로. **서식: 맑은 고딕, 색 최대 3개**

## 흐름

1. 논문 Fig 6(a) 원본 (p.265) → 2. 조건별 그래프 (09 → 10 → 11·12 → 13·14 → 14×4 반복) → 3. 요약표 → 4. 논문과 같은 것 / 서술≠원 코드 / 우리가 정한 값 → 5. 여쭐 것 → 6. 다음

## 출처 (숫자는 여기 값만)

- 실험: `original-hadoop2.7/x86-server/steps/` 09~13 (그래프 `NN-*/fig6a.png`), 지표 `setup/fig6a-metrics.py`
- 우리가 정한 값: `original-hadoop2.7/x86-server/assumptions-review.md`
- 표기: [논문 p.NN] / [원 코드] / [실측] / **추측** / [우리]. "논문이 틀렸다" 표현 금지

## 여쭐 것

1. 목표: 그래프 모양 일치 vs 메커니즘 재현 + 차이 원인 분리
2. executor 코어 1 vs 4 — 4코어 3회 완료 ([steps/15](../../../original-hadoop2.7/x86-server/steps/15-fig6a-4core.md)): PR 커짐·빨라짐, kill·PR 먼저 종료는 그대로
3. shrink 대기 2분: 원 코드만 vs 코드 수정 결과(11) 보조 제시
4. 입력 비율: Table 1(09) vs PR 확대(10)
5. VM 디스크 SSD 여부, worker1 복구
