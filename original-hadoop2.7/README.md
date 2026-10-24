# original-hadoop2.7 — 원 저자 코드 + 논문 환경 재현 (진행 중)

원 저자 공개 코드(YARN 2.7.3 기반)를 수정 없이, 논문 소프트웨어 환경(Ubuntu 16.04 · Docker 1.12.1 ·
cgroup v1)에서 실행한다. VM `u1604-test`(호스트명 `pf16-worker1`, SSH `127.0.0.1:2214`).

| 폴더 | 내용 |
|---|---|
| [lab-meetings/2026-10-26/](lab-meetings/2026-10-26/) | 01 원 코드 빌드 · 02 환경 차이표 · 03 16.04 부팅 · 04 16.04 환경 · 05 Hadoop 묶음 + task 이미지 |
| [legacy-2.7.3/](legacy-2.7.3/) | task 이미지 Dockerfile, conf, `build-image.sh`, jar 비교 `cmpsig.py` |

## 진행 상황

- [x] Ubuntu 16.04.7 + Docker 1.12.1 + cgroup v1(`swapaccount=1`)
- [x] 원 코드 컴파일 (테스트 제외) → YARN jar 13개
- [x] 공식 2.7.3 + YARN jar 교체 → `/opt/hadoop-2.7.3`, 소스 동일성 검증
- [x] task 이미지 `local/hadoop-docker:2.7.3`
- [ ] 단일 노드 YARN 기동 + DCE로 pi
- [ ] OCM/suspend/puff 로그 확인
- [ ] Spark 2.0.1 추가 → 3대 구성
