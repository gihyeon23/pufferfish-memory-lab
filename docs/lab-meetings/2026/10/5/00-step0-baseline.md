# Step 0 — 호스트 기준선 측정 + 자원 예산 확정

> 로드맵: [2026-10-05.md](2026-10-05.md) §3 Step 0

## 1. 게스트(현 VM `pufferfish-lab`) 실측 — 2026-10-05 완료

| 항목 | 실측값 | 비고 |
|---|---|---|
| OS | **Ubuntu 24.04.4 LTS (noble)**, aarch64, kernel 6.8.0-139 | VirtualBox 정보창의 "Ubuntu 24.10 Oracular"는 **VM 생성 시 고른 타입 라벨일 뿐**, 실제 설치본과 무관 |
| vCPU | 2 | |
| RAM | 3899 MiB (사용 1733 / 가용 2166 / buff·cache 1962) | VirtualBox 할당 4096MB |
| swap | `/swap.img` 3.8GiB, `swappiness=60` | |
| 디스크 | 루트 26G 중 **16G 사용 / 8.7G 여유** (VDI 상한 30GB, LVM) | ⚠️ **병목** |
| 디스크 내역 | `/usr` 3.3G, `/home` 4.4G, `/var` 약 5.2G(= docker 4.3G 포함) | |
| Docker | 29.7.1, `DockerRootDir=/var/lib/docker` | 이미지 1.10GB(보존 필요) + 빌드캐시 3.22GB(회수 가능 2.27GB) |
| cgroup | `cgroup2fs` (unified) | ✅ Hadoop 3.5 cgroup v2 전제 충족 |
| JDK | **21만 설치됨** (`java-21-openjdk-arm64`) | ⚠️ Hadoop 3.5.0 서버는 **17 필수** |
| 네트워크 | **NAT**, `enp0s8 10.0.2.15/24`, GW `10.0.2.2` | ⚠️ 7차 설계의 Bridged가 **아님** |
| SSH | `ssh` active, `~/.ssh/id_ed25519` 키 존재 | ✅ 키 재사용 가능 |
| 시간 동기화 | NTP active, synchronized=yes (UTC) | ✅ Hadoop 전제 충족 |

## 2. 지금 고쳐야 하는 문제

### P1. `/etc/hosts` 오타 — hostname이 IPv4로 해석되지 않음 (✅ 2026-10-05 수정 완료)

```
hostname        → pufferfish-lab
/etc/hosts      → 127.0.1.1 pufferfish-lap   ← 오타 (b가 p)
getent hosts pufferfish-lab
  → fd17:625c:... (IPv6 ULA)
  → fe80::...     (IPv6 link-local)
  → IPv4 항목 없음
```

- Hadoop/YARN은 데몬이 hostname을 해석해 바인딩·광고(advertise)하므로,
  IPv4가 안 잡히면 **NameNode·ResourceManager 기동 또는 워커 등록 단계에서 실패**한다
- 링크로컬(`fe80::`)로 광고되면 노드 간 통신이 아예 안 된다
- 지금은 단일 VM + Docker라 드러나지 않았을 뿐, Step 2~3에서 반드시 터진다

**수정**: `sudo sed -i 's/pufferfish-lap/pufferfish-lab/' /etc/hosts`
→ `getent hosts pufferfish-lab` 이 `127.0.1.1 pufferfish-lab` 반환하는 것으로 확인.
단, `00-clean-ubuntu` **스냅샷에서 복제하면 이 수정은 따라가지 않는다**(수정 이후 상태가 아님).
어차피 Step 1에서 노드마다 hostname·hosts를 개별 설정해야 하므로, 노드별 작업 항목으로 둔다.

### P2. 네트워크가 NAT — VM 3대가 서로 통신할 수 없음

- VirtualBox **NAT**는 각 VM이 독립된 `10.0.2.0/24`를 받아 **VM 간 통신이 불가능**
- 7차 설계([07-multi-node-cluster.md](../../../../experiments/07-multi-node-cluster.md))는 **Bridged Adapter** 전제
- Step 1 전에 어댑터를 **Bridged** 또는 **NAT Network**로 변경해야 함

### P3. 디스크 여유 8.7G

- 예상 소요: Hadoop 3.5.0 약 1.5G + Spark 약 1.5G + HiBench 빌드 시 Maven 로컬 저장소 3~5G + HDFS 데이터
- 대응 후보
  - `docker builder prune` → **2.27GB** 즉시 회수 (빌드 캐시만, 안전)
    ⚠️ `docker image prune -a`는 **쓰지 말 것** — 실행 중 컨테이너가 없어
    `pufferfish/workload-java:latest`까지 삭제돼 9·10차 재현이 불가능해진다
  - VDI 30GB → 확장(VM 종료 후 `VBoxManage modifymedium --resize`) + LVM/파일시스템 확장
  - HiBench 빌드는 **control 1대에서만** 수행하고 결과물만 worker로 배포

## 3. 호스트(macOS) 실측 — 2026-10-05 완료

| 항목 | 실측값 | 판정 |
|---|---|---|
| 물리 RAM | 16.0 GB | |
| 코어 | 10 | |
| 메모리 여유 | **39% free** | |
| **swap** | **total 8192 MB / used 7052 MB (86%)** | 🔴 **이미 거의 포화** |
| 디스크 | 460 GB 중 **107 GB 여유** | |
| 기존 VM 점유 | `~/VirtualBox VMs/` = **61 GB** (VM 1대 + 스냅샷) | VDI 상한 30GB인데 61GB → 스냅샷이 차지 |

### 🔴 R3 재평가 — 리스크가 "주의"가 아니라 "설계 변경 사유"

- 측정 시점은 **VM 1대(4GB)만 돌던 상태**인데 macOS가 이미 **swap 7GB를 쓰고 있다**
- 여기에 VM을 2대 더(+6GB) 올리면 호스트가 심하게 thrashing → **측정값 자체가 오염된다**
  (Step 6~9에서 "메모리 압박 때문에 느려진 것"인지 "맥이 스왑해서 느려진 것"인지 구분 불가)
- 측정 당시 Docker Desktop·브라우저 등이 떠 있었을 가능성이 큼 → 정리 후 재측정하되,
  macOS swap은 앱 종료 후에도 바로 줄지 않으므로 **절대값이 아니라 VM 기동 전/후 증가량과
  `memory_pressure` 추세**를 지표로 쓴다

### 디스크

- 여유 107GB, 기존 61GB
- **연결된 복제(linked clone)** 를 쓰면 복제본은 차이분만 저장 → 2대 추가해도 수 GB 수준
  - 전체 복제(full clone)면 2대 × 약 20GB = 40GB 소요 → 67GB 남음(가능하지만 낭비)
  - 단, 연결된 복제는 **원본 스냅샷을 지우면 전부 깨진다**

## 4. 자원 예산 — 제안

> 맥 swap 7GB 포화 상태를 반영해 9/30안(11GB)·10/5 1차안(10GB)보다 더 보수적으로 잡는다.

| 노드 | vCPU | RAM | 근거 |
|---|---:|---:|---|
| control | 2 | **1536 MB** | NameNode + ResourceManager만. 워크로드 컨테이너 없음. **기동용 예산** — Hadoop 기동 후 부족하면 Step 2에서 상향 |
| worker1 | 3 | **3584 MB** | NodeManager + DataNode + executor |
| worker2 | 3 | **3584 MB** | 동일 |
| **합계** | **8 / 10** | **8.5 GB / 16 GB** | macOS에 7.5GB 확보 |

- worker RAM을 깎으면 Step 6의 "메모리 압박 지점"을 못 찾을 수 있으므로 **worker를 우선 보호**하고
  control부터 줄인다
- 실행 중에는 맥에서 Docker Desktop·브라우저·Zoom 등을 내린다 (측정 전 체크리스트 항목으로 고정)
- **측정 중 `sysctl vm.swapusage`를 같이 기록**해서, 호스트 스왑이 결과를 오염시켰는지 사후 판별 가능하게 한다

## 5. 확정 사항 (2026-10-05 결정)

| 항목 | 결정 | 근거 |
|---|---|---|
| 기존 `pufferfish-lab` VM | **보존** (꺼둔 채 유지) | 1~10차 증거·환경 재현용. 교수님이 1단계 결과를 다시 물을 때 대응 |
| 새 클러스터 VM | `00-clean-ubuntu` 스냅샷에서 **연결된 복제 3대** | 디스크 절약(차이분만 저장), 깨끗한 출발점 |
| 노드 수 | **3대 유지** (control 1 + worker 2) | worker 2대가 있어야 Step 7 baseline과 논문 §4.3.2 클러스터 레벨이 성립 |
| 메모리 | control 1536MB / worker 3584MB ×2 = **8.5GB** | 맥 swap 포화 반영, worker 우선 보호 |
| vCPU | control 2 / worker 3 ×2 = **8 / 10** | |
| 네트워크 | **NAT Network** (아래 P2 참고) | 7차 설계의 Bridged에서 변경 — 노트북이라 접속 네트워크가 바뀌면 Bridged IP가 흔들림 |

### P2 결정 — Bridged가 아니라 NAT Network

| 방식 | VM↔VM | 맥→VM | 장소 바뀌어도 동작 | 판정 |
|---|---|---|---|---|
| NAT (현재) | ❌ | 포트포워딩 | ✅ | 3대 클러스터 불가 |
| Bridged (7차 설계) | ✅ | ✅ | ❌ 공유기 바뀌면 IP 변동 | 노트북엔 부적합 |
| **NAT Network** | ✅ | 포트포워딩 | ✅ | ✅ **채택** |
| 호스트 전용 어댑터 추가 | ✅ | ✅ | ✅ | ARM VirtualBox 지원 여부 미확인 — 보류 |

- NAT Network 안에서 **고정 IP**를 직접 부여해 Hadoop이 보는 주소를 결정적으로 만든다
  - control `10.10.0.11` / worker1 `10.10.0.12` / worker2 `10.10.0.13`, GW `10.10.0.1`
- 맥에서의 SSH(VS Code Remote-SSH)는 포트포워딩으로 해결: 2211/2212/2213 → 각 노드 22

## 6. 완료 기준

- [x] 게스트 VM 기준선 실측
- [x] macOS 호스트 실측 (RAM 16GB / 10코어 / swap 7GB 사용 중 / 디스크 107GB 여유)
- [x] VM 3대 자원 배분 확정 (control 2vCPU·1536MB, worker 3vCPU·3584MB ×2)
- [ ] 맥 정리(Docker Desktop 등 종료) 후 swap 재측정
  - ⚠️ macOS swap은 앱을 종료해도 **즉시 줄지 않는다**(지연 회수 + 메모리 압축).
    절대값이 아니라 **VM 기동 전/후 증가량과 `memory_pressure` 추세**로 판단한다
- [x] 기존 `pufferfish-lab` VM 처리 방침 확정 → **보존**
- [x] P1 `/etc/hosts` 수정 (2026-10-05 완료 — `getent hosts pufferfish-lab` → `127.0.1.1` 확인)
- [x] P2 네트워크 모드 확정 → **NAT Network + 고정 IP**
