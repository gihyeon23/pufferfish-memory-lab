# 7차: 멀티 노드 클러스터 (마스터 1 + 워커 2) 설계

## 목적

지금까지(1~6차)는 논문 4.3.1의 **노드 레벨** 메커니즘(OCM 감지, puff,
reclaim)만 단일 호스트에서 재현했다. 논문은 여기에 더해 4.3.2에서
**클러스터 레벨**(ResourceManager가 여러 NodeManager에 걸쳐 컨테이너를
배치·조율)을 다룬다. 이번 단계는 물리적으로 분리된 VM 3대(마스터 1 +
워커 2)로 이 클러스터 레벨을 실제로 재현하기 위한 설계다.

## 환경 제약

- 호스트: MacBook, Apple 계열 CPU 10코어, RAM 16GB
- 지금까지의 단일 VM 환경(`docs/environment.md`)을 워커 1대 스펙의
  기준으로 삼는다.

## 리소스 배분

| 노드 | vCPU | RAM | 역할 |
|---|---:|---:|---|
| 마스터 | 1 | 1~2GB | 워커 상태 조회 + reclaim 판단만, 워크로드 컨테이너 없음 |
| 워커 1 | 2~3 | 5GB | 워크로드 컨테이너 실행 (`container_monitor.py`+`suspend_manager.py`+`puff_manager.py`) |
| 워커 2 | 2~3 | 5GB | 워커 1과 동일 |

macOS 자체 여유분(코어/RAM 일부)은 남겨두고 딱 맞춰 쓰지 않는다.

## 네트워크

- **Bridged Adapter**로 VM 3대를 공유기 LAN에 직접 붙인다 (Host-only보다
  설정이 간단하고, 상호 통신에 별도 NAT 포트포워딩이 필요 없다)
- 각 VM에 고정 IP를 할당하거나, 서로의 `/etc/hosts`에 `master`/`worker1`/
  `worker2`로 등록해 이름으로 접근한다

## 통신 방식: SSH 기반 원격 실행

- **선택 이유**: 이 프로젝트 개발 환경이 이미 VS Code Remote-SSH
  (`docs/environment.md`)라 워커들에 SSH가 이미 세팅돼 있다. 새 의존성
  (Flask 등 HTTP 서버) 없이, 지금 `puff_manager.py`가
  `subprocess.run(["docker", ...])`로 로컬 docker를 조작하던 패턴을
  `subprocess.run(["ssh", "worker1", "docker", ...])`로 그대로 확장하면 된다.
- HTTP API(Flask 등)로 바꾸는 건 필요해지면 v2로 미룬다 — 지금 단계에서는
  오버엔지니어링을 피한다.

## 코드 구조 (기존 코드 재사용 관점)

- **워커**: `container_monitor.py` + `suspend_manager.py` + `puff_manager.py`
  (puff/개별 reclaim) — **수정 없이 그대로** 워커 로컬에서 지금처럼 실행.
  논문에서도 이 부분은 원래 "NodeManager당 하나씩 도는" 로직이라 그대로
  맞는다.
- **마스터**: 신규 `cluster_reclaim_daemon.py`(가칭)
  - SSH로 각 워커의 `get_host_assigned_mb()`(신규 조회용 서브커맨드 필요,
    아래 참고)를 원격 호출해 클러스터 전체 할당량을 합산
  - 부족하면 **어느 워커의 어느 컨테이너**를 reclaim할지 결정 (EJF는 이미
    `puff_manager.reclaim_host()`에 있으니, 마스터는 "어느 워커부터
    볼지"만 추가로 정하면 됨 — 예: 워커별로 가장 오래된 컨테이너의 생성
    시각을 비교해 전체 클러스터 EJF로 확장)
  - SSH로 해당 워커에 `puff_manager.py reclaim`/`reclaim-host` 원격 실행
- `puff_manager.py`에 "assigned-mb만 출력"하는 조회 전용 서브커맨드를 하나
  추가하면 마스터가 SSH stdout을 파싱하기 쉬워진다 (아직 미구현).

## 확인 포인트 (구현 후)

- [ ] 워커 1/2에서 각각 독립적으로 OCM 감지·puff가 지금처럼 동작하는지
- [ ] 마스터가 SSH로 두 워커의 할당량을 정확히 합산하는지
- [ ] 클러스터 전체가 예산 부족일 때, 마스터가 올바른 워커의 올바른
      컨테이너를 골라 reclaim하는지 (EJF가 워커 경계를 넘어서도 성립하는지)
- [ ] SSH 연결 실패/워커 다운 등 네트워크 장애 상황에서 마스터가 죽지
      않고 견디는지

## 상태

**설계만 완료.** VM 3대 실제 세팅과 마스터/워커 코드 구현은 아직
시작하지 않았다.
