# Pufferfish Memory Lab

Pufferfish 논문(SoCC'19, "Pufferfish: Container-driven Elastic Memory
Management for Data-intensive Applications")의 OCM 감지/puff/reclaim 동작을
재현하는 프로젝트입니다. 프로젝트 개요는 [README.md](README.md) 참고.

## 패키지 구성

| 폴더 | 내용 | 상태 |
|---|---|---|
| `reimpl-single-node/` | Python controller 재구현, Docker + cgroup v2 단일 호스트 (실험 1~10차) | 완료 |
| `reimpl-hadoop3/` | Hadoop 3.5.0 YARN 클러스터 + controller 외부 데몬 (Step 0~3) | 중단 |
| `original-hadoop2.7/` | 원 저자 코드(YARN 2.7.3) + 논문 환경(Ubuntu 16.04, Docker 1.12.1, cgroup v1) | 진행 중 |
| `common/` | 논문(`papers/`), 논문 분석 요약, 환경(`environment.md`) | — |

## 논문 참고 워크플로

논문 원본은 `common/papers/pufferfish-paper.pdf`에 있습니다(없으면 아직 안
넣은 것 — 사용자에게 요청).

**우선순위: `common/pufferfish-architecture.md` > 논문 원본**

1. `common/pufferfish-architecture.md`가 **있으면** 그 문서를 먼저 참고한다.
   이미 논문을 분석해서 핵심 내용(OCM 감지, puff/reclaim 트리거, Node Memory
   Manager 구조 등)과 페이지 근거를 정리해둔 요약본이라, 매번 논문 전체를
   다시 읽는 것보다 토큰을 훨씬 아낄 수 있다.
2. `common/pufferfish-architecture.md`가 **없거나**, 구체적인 근거(정확한 인용문·
   페이지 번호)를 다시 확인해야 하는 경우에만 논문 원본을 직접 읽는다.
   - PDF를 바로 못 읽는 환경이면 먼저 텍스트로 변환한다:
     ```bash
     pdftotext "common/papers/pufferfish-paper.pdf" "common/papers/pufferfish-paper.txt"
     ```
   - 분석이 끝나면 핵심 내용을 `common/pufferfish-architecture.md`에 정리해서
     남긴다(다음 세션이 논문을 다시 통째로 안 읽어도 되게).
3. 논문 vs 현재 구현을 비교할 때는 다음을 지킨다:
   - **논문에 명시된 사실**과 **내 해석/추측**을 명확히 구분하고, 추측은
     반드시 "추측"이라고 표시한다.
   - 논문 근거는 페이지 번호와 함께 표시한다.
   - 현재 구현 근거는 파일 경로와 줄 번호(`reimpl-single-node/controller/xxx.py:NN`, 원 저자 코드는 `XxxClass.java:NN`)로 표시한다.
   - 비교 결과는 "논문에 명시된 사실 / 현재 구현 / 차이 / 수정 필요 여부"
     표로 정리한다.

## 이 저장소의 관례

- 새 작업은 해당 패키지 폴더 안에서 한다. 여러 패키지가 같이 쓰는 것만
  `common/`에 둔다.
- `reimpl-single-node/controller/` 안의 스크립트는 반드시 `cd reimpl-single-node/controller`
  후 실행한다 (다른 위치에서 실행하면 `ModuleNotFoundError`/파일 경로 오류가 남).
- 뭔가 구현하거나 버그를 고치면, 코드만 바꾸지 말고 문서를 같이 남긴다 —
  목적 → 설계/원인 → 실행 방법 → 확인 포인트 → 검증 결과(또는 "구현만 완료,
  검증 예정") 순서.
  - `reimpl-single-node/`: `reimpl-single-node/experiments/`에 단계 번호(`NN-짧은-이름.md`),
    `reimpl-single-node/experiments/README.md` 인덱스와 루트 `README.md` 표도 갱신
  - `reimpl-hadoop3/`: `steps/`에 단계 번호(`0N-*.md`)
  - `original-hadoop2.7/`: 환경별 폴더(`arm-mac/` 연습, `x86-server/` 정식)의 `steps/`에 단계 번호. 두 환경 공통 스크립트·설정은 `setup/`
- **실험 기록(메인 길)과 랩미팅 발표 자료는 분리한다.**
  - 실험 기록: 위 패키지 폴더에 단계 번호로 계속 쌓는다.
  - 발표 자료: `common/lab-meetings/<랩미팅 날짜>/`에 그 주 요약·발표 메모·예상 질문을 둔다.
    실험 문서는 복사하지 않고 링크로 가리킨다.
