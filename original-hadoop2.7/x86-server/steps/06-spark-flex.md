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
