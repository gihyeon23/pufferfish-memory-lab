# 06. Spark 2.0.1 + Flex 컨테이너 동작 확인 (2026-11-01)

> 표기: [사실] 원 코드·README 확인 / **추측**

## 1. 목적

- 10/26 계획 2단계: Flex 컨테이너가 실제로 만들어지고, Pufferfish 경로(OCM → suspend → puff → reclaim)를 탈 수 있는지 확인
- 06a(이번): SparkPi로 **Flex 판정 · `-Xmx` 치환 · docker 메모리 설정**까지 확인
- 06b(다음): 메모리를 많이 쓰는 작업으로 OCM·puff 유도

## 2. 설계 — Flex 판정 경로 [사실: 원 코드]

| 단계 | 위치 | 동작 |
|---|---|---|
| 1 | `RMAppManager.java:330-357` | AM 요청 라벨이 `flex` 하나면 라벨을 `null`로 지우고 `isFlex=true` → **node label 기능을 켤 필요 없음** |
| 2 | `ContainerManagerImpl.java:841-847` | Flex app의 AM이 아닌 컨테이너 → 로그 `<id> set to be flexible`, 나머지 `set to be normal` |
| 3 | `DockerContainerExecutor.java:353-366` | Flexible 컨테이너 명령의 `-Xmx...` 인자를 `-Xmx<balloon.jvm-mb>m`으로 교체 (05에서 16384) |
| 4 | `DockerContainerExecutor.java:214-220` | `docker run --memory=<요청 메모리>m --memory-swap -1` |

- Spark는 `spark.yarn.am.nodeLabelExpression=flex`로 AM 라벨 지정 [원 README]
- MapReduce 2.7.3은 AM 라벨을 지정할 수 없어 Flex가 안 됨 (arm-mac 06)

## 3. 준비

- [../../setup/install-spark.sh](../../setup/install-spark.sh)
  - `spark-2.0.1-bin-hadoop2.7`을 `/opt`에 설치 (Apache archive, 공식 `.md5`로 검증 — 2.0.1은 md5만 남아 있음)
- [../../setup/spark-pi-flex.sh](../../setup/spark-pi-flex.sh)
  - SparkPi를 cluster 모드 + `flex` 라벨로 실행 (기본: executor 2개 × 1g)
  - cluster 모드라 driver(AM)도 task 이미지(JDK 7) 안에서 실행됨
- 호스트 `spark-submit`은 JDK 8. Spark 2.0.1은 JDK 7도 지원하므로 컨테이너 쪽은 7u51 (**추측**: 둘 사이 직렬화 호환 문제 없음)

## 4. 실행 방법 (VM)

```bash
bash ~/legacy/setup/install-spark.sh
bash ~/legacy/setup/spark-pi-flex.sh            # 실행 중 다른 터미널에서 아래 확인
```

## 5. 확인 포인트

```bash
# ① Flex 판정 (executor = flexible, AM = normal)
grep -E "set to be (flexible|normal)" /opt/hadoop-2.7.3/logs/yarn-*-nodemanager-*.log | tail
# ② -Xmx 치환 + docker 메모리 (실행 중에)
docker ps --format '{{.Names}}' | while read c; do echo "$c $(docker inspect -f '{{.HostConfig.Memory}} {{.HostConfig.MemorySwap}}' $c)"; done
ps -ef | grep -o -- "-Xmx[0-9]*[mg]" | sort | uniq -c
# ③ 결과 (driver stdout, cluster 모드라 컨테이너 로그에 있음)
grep -rh "Pi is roughly" /opt/hadoop-2.7.3/logs/userlogs/ ~/hadoop-data/ 2>/dev/null | tail -1
```

- 기대: executor 컨테이너만 flexible, 그 컨테이너의 `-Xmx16384m`, docker Memory는 요청값(1g + overhead), MemorySwap `-1`
- `Pi is roughly` 위치는 확인 필요 (DCE의 컨테이너 로그 경로)

## 6. 검증 결과

### 1차 실행 (2026-11-01, `spark-pi-flex.sh` 기본값)

| 확인 | 결과 |
|---|---|
| Spark 설치 | `install-spark.sh` → md5 통과, `version 2.0.1` |
| 잡 | `application_1793511642822_0001` SparkPi cluster 모드 — **final status: SUCCEEDED** (제출~종료 약 20초) |
| AM 요청 | 1408MB (1024 + overhead 384) |
| ① Flex 판정 | AM `..._01_000001` **set to be normal**, executor `..._000002`·`..._000003` **set to be flexible** ✅ |
| 비교: MR pi (03) | 컨테이너 4개 전부 normal — MR은 AM 라벨 지정 불가 (arm-mac 06과 같음) |

- `flex` 라벨 요청이 node label 기능 없이 통과함 → §2의 원 코드 분석과 일치
- ②·③은 잡이 끝난 뒤에 확인해서 컨테이너가 없었음 → 2차에서 확인

### 2차 실행 (`spark-pi-flex.sh 2 1g 30000`, `application_1793511642822_0002`, 실행 중 확인)

| 확인 | 결과 |
|---|---|
| ② `-Xmx` (`ps -ef`) | `-Xmx16384m` ×4 = executor 2개 ✅ / `-Xmx1024m` ×2 = AM(normal, 원래 값) / `-Xmx1000m` ×4 = Hadoop 데몬 |
| ② docker 메모리 | 컨테이너 3개 모두 `Memory 1610612736`(1536MB), `MemorySwap -1` ✅ |

- 한 컨테이너가 `ps`에 2번 잡힘 (**추측**: `bash -c "java ..."` 셸 + java 프로세스)
- 1536MB인 이유 (**추측**): 요청 1408MB(1024 + overhead 384)를 YARN이 `minimum-allocation-mb`(256)의 배수로 올림 → 6 × 256 = 1536
- **핵심**: Flex executor는 컨테이너 메모리 1.5GB에 힙 상한 16GB → 힙이 커지면 limit을 넘어 swap으로 감(`--memory-swap -1`) → OCM → puff로 받아내는 원 설계 그대로 (10/26 랩미팅 3-5)
  - SparkPi는 힙을 거의 안 써서 이번엔 OCM 없음 → 06b에서 유도
| ③ 결과 | **final status: SUCCEEDED**, 제출~종료 약 3분 13초 (14:57:13 → 15:00:26), `Pi is roughly 3.141589616557201` |

- 06a 결론: Flex 판정 → `-Xmx` 치환 → `docker run --memory --memory-swap -1`까지 원 코드 설계대로 동작. JDK 7u51 컨테이너에서 Spark 2.0.1 cluster 모드 정상
- 다음 06b: executor 힙을 실제로 키우는 작업으로 OCM → suspend → puff → reclaim 로그 확인

## 7. 06b — OCM → puff 유도

### 설계

- Flex executor는 컨테이너 limit 1.5GB, 힙 상한 16GB (06a) → 힙을 실제로 3GB 채우면 limit을 넘어 swap으로 감
- [../../setup/ocm-cache.scala](../../setup/ocm-cache.scala): executor마다 1MB 배열 `MB_PER_EXEC`개(기본 3000)를 `MEMORY_ONLY`로 cache → `HOLD_SEC`(60초) 유지 → 다시 읽기
  - Spark 저장 메모리 = (힙 − 300MB) × 0.6 ≈ 9.6GB (**추측**: 힙 16GB 기준) → 3GB는 evict 없이 캐시됨
- [../../setup/spark-ocm-flex.sh](../../setup/spark-ocm-flex.sh): `spark-shell -i`(client 모드) + `flex` 라벨
- [../../setup/watch-containers.sh](../../setup/watch-containers.sh): 2초마다 컨테이너별 cgroup limit·mem·swap·CPU quota·cpuset 출력

### 원 코드 로그 [사실: `ContainerImpl.java`]

| 단계 | 로그 | 위치 |
|---|---|---|
| OCM | `out of memory contianer detected: <id> ...` (원문 오타 그대로) | :1143 |
| puff | `balloon-nswap: <id> from X to: Y`, `update container memory: ...` | :946-949 |
| 상태 | `$$$  <id> <state>` | :780 |
| CPU 제한 | `Container quota <id> ...`, `Container set <id> ...` | :1072, :1087 |
| puff 중단 | `stop ballooning at assign usage: ...` | `NodeMemoryManager.java:303` |

### 실행 방법 (VM, 터미널 2개)

```bash
# 터미널 2 (먼저)
bash ~/legacy/setup/watch-containers.sh
# 터미널 1
bash ~/legacy/setup/spark-ocm-flex.sh            # 3000MB × executor 2, 60초 유지
# 끝난 뒤
grep -E "set to be|out of memory contianer|balloon|update container memory|Container (quota|set)|stop ballooning" \
  /opt/hadoop-2.7.3/logs/yarn-*-nodemanager-*.log | tail -60
```

### 확인 포인트 · 기대 (**추측**)

- executor 2개 `set to be flexible` (client 모드에서도 Flex가 되는지)
- executor mem이 limit 근처에서 멈추고 swap이 늘어남 → OCM 로그
- limit이 ×1.4씩 늘어남 (1536 → 약 2150 → 3010 → 4214MB, ϕ=0.4) → swap 감소
- 노드 메모리가 충분하므로 suspend·reclaim은 안 일어나는 게 정상 → 메모리 압박 실험은 다음 단계
- `[06b] cached 6000 MB`, `second pass` 출력

### 결과 (2026-11-01, `application_1793511642822_0004`) — OCM → suspend → puff → shrink 관찰

- 1차 시도(`_0003`) 실패: `spark-shell -i`가 줄 단위로 해석해서 `.map(...)`로 시작하는 줄이 `illegal start of definition` → 체인을 한 줄로 수정
- 원본 기록: [06b-watch.log](06b-watch.log) (cgroup 2초 간격), [06b-nm.log](06b-nm.log) (NM 로그 발췌)
- Spark 출력: `[06b] cached 6000 MB in 30s`, `[06b] second pass 6000.0 MB in 0s`

| 단계 | 관찰 [사실: 로그] | 원 코드 / 논문 |
|---|---|---|
| Flex | client 모드에서도 executor `_02`·`_03` `set to be flexible`, AM normal | §2와 일치 |
| OCM | 15:09:05 mem 1535 / limit 1536, swap 119~134M → 15:09:09.888 `out of memory contianer detected: _02 1535 134 1536` | `mem + swap > limit` (`ContainerImpl.java:1143`) |
| suspend | 15:09:09 `_02` quota 1000 → 15:09:12 cpus 0 | 논문 "CPU 1%, 코어 1개" [p.260] |
| puff `_02` | 1536 → 2150 → 3010 → **4214 → 5899**MB (15:09:12 ~ 15:09:30) | ×1.4 정확히 일치 (ϕ=0.4) [p.263] |
| puff `_03` | 1536 → 2150 → 3010 → **4214**MB (15:09:17 ~ 15:09:28) | 〃 |
| 재개 | puff 직후 quota -1로 풀림, cpus는 몇 초 뒤 0-7로 복원 | — |
| shrink | 15:09:44 `_02` 5899 → 5216, `_03` 4214 → 3667 | 아래 참고 |
| 종료 | 15:10:32 `_03` 종료, `_02` 5216 → 3769, 15:10:34 컨테이너 모두 정리 | — |

- **shrink = (mem + swap) × 1.1** [사실: 계산 일치]
  - `_02`: (4157 + 585) × 1.1 = 5216 ✅, `_03`: (3236 + 98) × 1.1 = 3667 ✅
  - 원 코드 `SLACK_FACTOR=1.1`, limit > (mem + swap) × 1.1이면 그 값으로 줄임 (`ContainerImpl.java:663, 1204-1217`)
  - **논문과 차이 (확인함)**

    | 논문에 명시된 사실 | 원 코드 | 차이 | 수정 필요 |
    |---|---|---|---|
    | "puffed from 50GB to 70GB while its actual demand is 60GB … shrinks the container size to 62GB (2GB overhead by default)" [p.264] | `targetSize = (mem + swap) × 1.1`, 조건 `limit > (mem + swap) × 1.1` (`ContainerImpl.java:1204, 1217`), `SLACK_FACTOR=1.1` 하드코딩 (:663) | 고정 2GB ↔ 10% 비율. 논문 예시(수요 60GB)면 62GB ↔ 66GB | 없음 — 원 코드 재현이 목적이라 그대로 씀. 결과 해석 때 명시 |

    - shrink 조건: 한 번이라도 puff된 컨테이너(`balloonedBefore`)이고 puff 진행 중(`isBallooningWindow`)이 아닐 때 (`ContainerImpl.java:1195-1199`)
    - 우리 워커 규모(수요 수 GB)에서는 10%가 2GB보다 작음 → 논문보다 여유가 적게 남음 (**추측**: 이후 다시 OCM이 날 가능성이 논문보다 큼)
    - 관찰된 shrink는 마지막 puff(15:09:30) 약 14초 뒤 — 논문의 "2분 동안 OCM이 아니면 집합 C에서 제외" [p.264]와는 별개 동작으로 보임 (**추측**)
- puff 간격은 약 4~5초 (논문 heartbeat 2초 [p.263]보다 김) — **추측**: OCM 판정 후 다음 heartbeat에 puff가 실행돼서 두 주기가 걸림
- backoff(2순위 컨테이너는 ϕ/Nc) [p.263]는 안 보임: 두 컨테이너 모두 ×1.4 → 원 코드는 **앱 단위** backoff라 정상 (§8에서 확인)
- 남은 swap: puff 뒤에도 `_02` 585M가 그대로 남음 → swap된 페이지는 다시 접근해야 메모리로 돌아옴
  - `second pass 0s`: 두 번째 읽기가 배열 길이만 봐서 실제 페이지를 안 건드림 → §8에서 스크립트 개선
- `stop ballooning`·reclaim·kill 없음: 노드 메모리(28GB)에 여유가 있어서 정상 — 메모리 압박 실험은 다음 단계

## 8. 06c — 두 번째 읽기 개선 + backoff 원 코드 확인 (2026-11-01)

### 목적

- 06b의 `second pass 0s` 해결: 두 번째 읽기가 실제 페이지를 건드려 swap-in이 일어나게
- 06b에서 backoff(ϕ/Nc)가 안 보인 이유를 원 코드로 확인
- 실행은 Claude가 맥에서 `ssh labvm`으로 VM에서 직접 수행 (06b와 같은 조건)

### 설계 — 스크립트 변경 ([../../setup/ocm-cache.scala](../../setup/ocm-cache.scala))

- 두 번째 읽기: `_.length` 합 → 배열마다 **4KB 간격으로 1바이트씩 더함** (모든 페이지 접근, 1MB당 256번)
- 출력: `second pass <MB 수> MB (byte sum <합>) in <초>s` — 바이트 합은 항상 0 (JIT가 루프를 없애지 않게 결과를 출력에 씀)

### 원인 — backoff는 앱 단위 [사실: 원 코드 · 논문]

| 논문에 명시된 사실 | 원 코드 | 차이 | 수정 필요 |
|---|---|---|---|
| Algorithm 1: `Nc = C.size()`(C = 우선순위로 정렬된 **OCM 컨테이너** 집합), 컨테이너 하나 puff할 때마다 `ϕ /= Nc` [p.264] | 앱을 시작 시각 순으로 정렬, **같은 앱의 컨테이너는 같은 비율**, 앱 하나 처리 후 `balloonRatio /= swappingSize`(= swap 중인 컨테이너가 있는 **앱 수**) (`NodeMemoryManager.java:308-345`) | 나누는 단위가 컨테이너 ↔ 앱. 이번처럼 한 앱의 executor 2개면 논문은 ×1.4, ×1.2 / 원 코드는 둘 다 ×1.4 | 없음 — 원 코드 재현이 목적. 결과 해석 때 명시 |
| EJF: 컨테이너 우선순위 = 그 컨테이너가 속한 **job의 도착 시각** [p.264] | `getApplicationLaunchTime()` 오름차순 (`NodeMemoryManager.java:202-207`) | 없음 — 같은 job 컨테이너는 우선순위가 같음 | — |
| puff 양 `min(c.memory × ϕ, (M − A)/2)` [p.264, Algorithm 1 18행] | `min(old × ratio, available/2)`, `available = nodeTotal × balloon.stop − 할당 합` (`NodeMemoryManager.java:326-327`) | M 대신 `M × 0.8` 사용 | 없음 |

- **추측**: 공개 코드는 앱 단위 backoff라 "앱 2개 이상이 동시에 OCM"일 때만 비율이 줄어듦 → 다음 메모리 압박 실험에서 앱 2개로 확인 가능

### 실행 방법 (맥 → VM)

```bash
scp original-hadoop2.7/setup/ocm-cache.scala labvm:legacy/setup/
ssh labvm 'cd ~; nohup bash legacy/setup/watch-containers.sh > 06c-watch.log 2>&1 & W=$!;
  bash legacy/setup/spark-ocm-flex.sh > 06c-spark.log 2>&1; sleep 4; kill $W'
```

### 결과 (`application_1793511642822_0005`)

- 원본: [06c-watch.log](06c-watch.log), [06c-nm.log](06c-nm.log)
- Spark 출력: `[06b] cached 6000 MB in 30s`, `[06b] second pass 6000 MB (byte sum 0) in 1s`

| 시각 | 관찰 [사실: 로그] |
|---|---|
| 15:41:55 ~ 15:42:18 | OCM → suspend → puff: `_02` 1536 → 2150 → 3010 → 4214 → 5899, `_03` 1536 → 2150 → 3010 → 4214 (06b와 같은 순서·크기) |
| 15:42:08 | 같은 라운드에서 `_02` 3010 → 4214, `_03` 2150 → 3010 — **둘 다 ×1.4** (앱 단위 backoff와 일치) |
| 15:42:29 / 15:42:35 | `is removed`(swap 집합에서 빠짐) 직후 shrink: `_03` 4214 → 3639, `_02` 5899 → 4826 |
| 15:43:18 | 두 번째 읽기: swap `_02` 175 → 171M, `_03` 142 → 134M (거의 그대로) |
| 15:43:20 ~ 24 | AM·`_03` 종료 후 `_02`만 OCM 재발: mem 4825 / limit 4826, swap 422M → suspend(quota 1000, cpus 0) → puff 4826 → 6756 (×1.4) |

- **shrink = (mem + swap) × 1.1 재확인**: `_03` (3167 + 142) × 1.1 = 3639 ✅, `_02` (4213 + 175) × 1.1 = 4826 ✅
- **shrink 시점**: `is removed` 바로 뒤 [사실: 로그] — 원 코드는 `SWAP_KEEP_TIME = 5` 라운드 동안 OCM이 없으면 ballooning window를 끄고(`NodeMemoryManager.java:102, 170-177`), 그 뒤에 shrink 가능(`ContainerImpl.java:1198`). 논문은 "2분" [p.264], 코드 주석도 `keep for 2 minute`인데 값은 5 라운드
- **두 번째 읽기**: 모든 페이지를 건드렸지만(1초) swap은 거의 안 줄었음
  - **추측**: swap된 페이지는 cache 배열이 아니라 cache를 만들 때 생긴 쓰레기 객체나 JVM의 다른 영역이라, 배열을 다시 읽어도 안 돌아옴
- **OCM 재발 (15:43:21)**: shrink 후 여유가 10%뿐이라 다시 OCM이 날 수 있다는 §7의 추측과 맞는 현상
  - 단, 두 번째 읽기가 끝나고 앱이 종료되던 중이라 **원인은 단정 못 함** (**추측**: executor 종료 과정의 메모리 사용)
- **reclaim**: executor launch마다 `MemoryReclaim` 호출됨(`memory reclaim called … request: 1536`) — 하지만 회수 없음
  - 원 코드는 `할당 합 + 요청 < nodeTotal(28672)`이면 바로 리턴 (`NodeMemoryManager.java:398-400`)
  - 로그의 `current assigned: 0`은 `updateMetrics()` 전에 찍은 값 (`NodeMemoryManager.java:393-396`)
  - `limit: 25804.8` = 28672 × 0.9 (`balloon.reclaim`)는 출력만 하고 판정에는 안 씀
- `stop ballooning`·kill 없음 (노드 여유 충분)

### 다음 — 메모리 압박 실험 설계 메모 (**추측**, 원 코드 기준)

- puff는 할당 합이 `28672 × 0.8 = 22937MB`에 닿으면 멈추고(`stop ballooning`), `× 0.9 = 25804MB` 이상이면 kill
- reclaim은 새 컨테이너 launch 때 `할당 합 + 요청 ≥ 28672`일 때만 실제로 회수
  - RM은 puff를 모르므로(요청량 기준으로만 스케줄) puff로 할당 합이 커진 뒤 새 앱을 넣으면 이 조건을 만들 수 있음
- 계획: 앱 1이 puff로 할당 합을 0.8 근처까지 올림 → 앱 2(Flex)를 제출해 reclaim + 앱 단위 backoff 확인
