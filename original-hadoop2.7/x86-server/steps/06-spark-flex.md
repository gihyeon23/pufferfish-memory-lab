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
  - **논문과 차이**: 01 §4에는 shrink 여유분을 "2GB [p.264]"로 적었는데, 원 코드는 고정 2GB가 아니라 **10% 비율** → 비교표에 추가할 것
- puff 간격은 약 4~5초 (논문 heartbeat 2초 [p.263]보다 김) — **추측**: OCM 판정 후 다음 heartbeat에 puff가 실행돼서 두 주기가 걸림
- backoff(2순위 컨테이너는 ϕ/Nc) [p.263]는 안 보임: 두 컨테이너 모두 ×1.4 — 원 코드 확인 필요
- 남은 swap: puff 뒤에도 `_02` 585M가 그대로 남음 → swap된 페이지는 다시 접근해야 메모리로 돌아옴
  - `second pass 0s`: 두 번째 읽기가 배열 길이만 봐서 실제 페이지를 안 건드림 → 스크립트 개선 필요 (바이트 합으로)
- `stop ballooning`·reclaim·kill 없음: 노드 메모리(28GB)에 여유가 있어서 정상 — 메모리 압박 실험은 다음 단계
