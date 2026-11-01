# 01. 클러스터 사양 확정 · 실험 설정 초기안 (2026-10-26)

> **확정**: 서버 요청 사양(§2)만. **초기안**: 실험 설정(§3~§5) — 예비 실험(§6)으로 조정한다.
> 표기: [논문 p.NN] 논문 명시 / [코드] 원 저자 코드 기본값 / [README] 원 저자 README / [우리] 우리가 정한 값 / **추측**

## 1. 목적

- 교수님 지시: 하드웨어는 원논문에 최대한 맞출 것
- 원논문 사양(노드당 128GB, 26노드)은 확보할 수 없음 → 워커 1대의 **메모리를 1/4로 축소**하고, 축소 근거를 남김
- 실험 구성은 9/21에 정한 control 1 + worker 2

## 2. 서버 요청 사양 — 확정

| 노드 | vCPU | RAM | 디스크 | 역할 |
|---|---|---|---|---|
| master ×1 | 4 | 8GB | 100GB | NameNode, ResourceManager |
| worker ×2 | 8 (각) | 32GB (각) | 200GB (각) | NodeManager, DataNode, task 컨테이너 |

- 메일로 요청한 8 vCPU / 32GB / 200GB는 **워커 1대당** 사양 (3대 합계가 아님)
- 원논문 노드 [논문 p.265]: Xeon E5-2640 ×2 (16코어 / 32스레드), 128GB, 1TB HDD ×5 RAID-5, 10Gbps, 26노드

## 3. 워커 메모리 설정 — 초기안

축소 기준: 노드 RAM 128GB → 32GB (1/4)

| 항목 | 원 값 (출처) | 초기값 | 근거 / 주의 |
|---|---|---|---|
| YARN 메모리 `yarn.nodemanager.resource.memory-mb` | 120GB [논문 p.265] | **28GB** (28672) | 정확한 1/4는 30GB. 워커에는 OS·DataNode·NodeManager·Docker 데몬과 컨테이너의 힙 외 메모리가 남고, 고정 오버헤드는 RAM과 함께 1/4로 줄지 않음 → 4GB 여유로 시작 [우리]. **논문 비율과 2GB 차이** |
| MAX_HEAP `balloon.jvm-mb` | 64GB [논문 p.265] / 65536 [코드] | **16GB** (16384) | 1/4 |
| MIN_CONT | 4GB [논문 p.265] | **1GB** | 1/4. 원 코드에서 이 값에 해당하는 설정은 아직 확인 못 함 (Spark executor 요청 메모리로 **추측**) |
| swap | 컨테이너 swap 제한 해제 [코드] (`--memory-swap -1` 등, [pufferfish-architecture.md](../../../common/pufferfish-architecture.md) §3.1) / 호스트 swap 용량은 논문에 없음 | **32GB swapfile** | RAM과 같은 크기로 시작 [우리]. 원 코드의 "무제한"은 컨테이너 단위 제한 해제라는 뜻이고, 원 실험 호스트의 swap이 무한했다는 뜻이 아님 |

## 4. 비율 파라미터 — 출처 구분

| 파라미터 | 논문 | 원 코드 기본값 | 원 README | 초기값 |
|---|---|---|---|---|
| puff ratio ϕ `balloon.ratio` | 40% [p.265] | 0.4 | — | 0.4 |
| puff 중단 `balloon.stop` | 수치 없음 ("노드 메모리 소진 시") | 0.8 | **0.9** (예시) | 0.8 (코드 기본) |
| reclaim `balloon.reclaim` | 수치 없음 | 0.9 | — | 0.9 |
| shrink 여유분 | 2GB [p.264] | 확인 필요 | — | 설정 가능하면 0.5GB(1/4), 고정값이면 2GB |

- 근거: [05-hadoop-dist-task-image.md](../../arm-mac/steps/05-hadoop-dist-task-image.md) `balloon.*` 표

## 5. 데이터 · HDFS — 초기안

### 데이터 (Table 1 Small의 1/4, [논문 p.265])

| 워크로드 | 논문 Small | 시작값 |
|---|---|---|
| Spark-WC | 100GB | 25GB |
| Spark-KM | 1×10⁸ 샘플 | 2.5×10⁷ |
| Spark-PR | 5×10⁶ 페이지 | 1.25×10⁶ |
| Spark-NW | 1×10⁷ 엣지 | 2.5×10⁶ |
| TPC-H | 10GB | 2.5GB |

- 1/4은 **예비 실험으로 조정할 시작값**. 입력을 1/4로 줄여도 메모리 수요가 정확히 1/4이 되는 것은 아님
- 샘플·페이지·엣지 개수만으로는 저장 용량을 알 수 없음 → 생성 후 `hdfs dfs -du -h`로 실측

### 디스크 200GB 예산 (워커당, 실측 전 예산값)

| 용도 | 예산 |
|---|---|
| OS·패키지 | 20GB |
| Docker 이미지·Hadoop·Spark | 20GB |
| swap | 32GB |
| HDFS 입력 | 생성 후 확인 |
| 셔플·임시·출력 | 생성 후 확인 |
| 로그·결과 | 5GB |

### HDFS 복제 설정

| 실험 | `dfs.replication` | DataNode | NodeManager |
|---|---|---|---|
| 단일 워커 (§5.2 재현) | 2 | worker1·2 모두 | **worker1만** |
| 두 워커 (baseline vs Pufferfish) | 2 | worker1·2 | worker1·2 |

- 단일 워커 실험은 계산만 worker1로 제한하고, 저장은 두 워커가 그대로 맡음
  - DataNode를 한 대만 켜면 replication=2에서 복제본이 부족해짐
  - 두 실험이 같은 HDFS 데이터를 그대로 공유할 수 있음
  - replication=2라 worker1에도 모든 블록이 있음 → 읽기는 로컬에서 됨 (**추측**: HDFS가 로컬 복제본을 우선 읽는 기본 동작 기준)
- 방법: worker2의 NodeManager만 중지 (`yarn-daemon.sh stop nodemanager`)

## 6. 예비 실험 → 동작 검증 (실행 방법 · 확인 포인트)

1. **입력 규모 선택 (예비)**
   - worker1에서 Spark-PR을 작은 힙(1GB)으로 실행해 OOM/실패 확인, MAX_HEAP 16GB로 실행해 성공 확인
   - 이 결과는 입력 규모를 고르는 근거일 뿐, **전체 축소가 타당하다는 증거는 아님**
   - 실패하지 않거나 16GB에서도 실패하면 입력 크기를 조정
2. **Pufferfish 동작 검증 (별도)**: Flex 컨테이너(`spark.yarn.am.nodeLabelExpression flex`)에서 NM 로그로 확인
   - OCM 감지: `memory+swap > limit` 판정 로그
   - suspend: `docker update --cpu-quota 1000 --cpuset-cpus 0` 적용
   - puff: 컨테이너 limit 증가, `balloon.stop` 근처에서 중단
   - reclaim: 신규 컨테이너 launch 시 `MemoryReclaim` 호출 및 회수
3. **YARN 28GB 점검**: 실험 중 워커의 `free -m`과 데몬 RSS를 기록해서, 4GB 여유가 실제로 필요한지 판단
   - 여유가 남으면 30GB(정확한 1/4)로 올릴지 검토
4. 1~3을 통과한 뒤 §5.2 단일 워커 실험(PR 1 + KM 2)과 두 워커 실험(HiBench)으로 진행

## 7. 논문과 다른 점 (결과에 명시)

- 26노드 → 워커 2대 (다중 노드 실험은 축소판)
- 노드 RAM·데이터 1/4, YARN은 28GB (1/4 기준 30GB보다 2GB 적음)
- 32스레드 → 8 vCPU
- 물리 HDD RAID-5 → VM 디스크 (종류 미확인) — swap 속도 차이로 reclaim·thrashing 수치가 달라질 수 있음

## 8. 검증 결과

- 사양 확정, 설정은 초기안 — **VM 수령 후 §6 예비 실험 예정**
