# original-hadoop2.7 — 원 저자 코드 + 논문 환경 재현 (진행 중)

원 저자 공개 코드(YARN 2.7.3 기반)를 수정 없이, 논문 소프트웨어 환경(Ubuntu 16.04 · Docker 1.12.1 ·
cgroup v1)에서 실행한다.

| 폴더 | 내용 | 상태 |
|---|---|---|
| [setup/](setup/) | 두 환경 공통: 설치·이미지 빌드 스크립트, conf, Dockerfile, jar 비교 `cmpsig.py` | 사용 중 |
| [arm-mac/](arm-mac/) | 맥(M4) VirtualBox VM `u1604-test` — 절차 확인·연습용 | 정식 실험 안 함 |
| [x86-server/](x86-server/) | 연구실 x86 VM — **정식 실험** | VM 할당 대기 |

## 환경을 나눈 이유

- 맥은 ARM이라 원 이미지(x86 전용)·CentOS 6.5·Oracle JDK 7을 못 쓰고, 16.04 커널이 CPU를 1개만 인식함
  ([06](arm-mac/steps/06-single-node-yarn-pi.md))
- 2026-10-25 교수님이 x86 VM(Ubuntu 16.04.7) 할당 결정 → 정식 결과는 x86에서, 맥 기록은 연습·근거로 보존

## 진행 상황

### arm-mac (연습) — [steps/](arm-mac/steps/)

01 원 코드 빌드 · 02 환경 차이표 · 03 16.04 부팅 · 04 16.04 환경 · 05 Hadoop 묶음 + task 이미지 · 06 단일 노드 기동 + pi

- [x] Ubuntu 16.04.7 + Docker 1.12.1 + cgroup v1(`swapaccount=1`)
- [x] 원 코드 컴파일 (테스트 제외) → YARN jar 13개
- [x] 공식 2.7.3 + YARN jar 교체 → `/opt/hadoop-2.7.3`, 소스 동일성 검증
- [x] task 이미지 `local/hadoop-docker:2.7.3-jdk7` (CentOS 7 + OpenJDK 7, Server VM) / 비교용 `2.7.3-jdk8`
- [x] 단일 노드 YARN 기동 + DCE로 pi — JDK 7 6/6 (평균 21.2초). 단 MR 컨테이너는 전부 REGULAR (Flex는 AM node label `flex` 필요, MR 2.7.3은 지정 불가)
- [x] VM CPU 1개 문제 확인 (VirtualBox ACPI 6.3 형식을 커널 4.4가 못 읽음) → x86 VM으로 해소 예정

### x86-server (정식) — [x86-server/](x86-server/)

- [x] 설치 스크립트 준비 (`setup/`)
- [ ] VM 수령 → 커널 4.4·CPU 수·x86_64 확인
- [ ] 설치 스크립트로 환경 구성 → pi
- [ ] task 이미지 방향 결정 (원 `sequenceiq/hadoop-docker` 반입 vs CentOS 6.5 + JDK 7 직접 구성)
- [ ] Spark 2.0.1 + `spark.yarn.am.nodeLabelExpression flex` → OCM/suspend/puff 로그 확인
- [ ] baseline(공식 YARN jar) vs Pufferfish 비교 → 3대 구성
