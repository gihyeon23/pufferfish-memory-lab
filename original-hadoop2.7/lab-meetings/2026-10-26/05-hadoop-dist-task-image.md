# Legacy 4 — 실행용 Hadoop 2.7.3 구성 + task Docker 이미지

> 랩미팅: 2026-10-26 / 이전: [04-ubuntu1604-env.md](04-ubuntu1604-env.md)
>
> 표기: **[사실]** 실측·원 코드 확인 / **[추측]** 내 해석

## 목적

**한 줄 요약: 원 코드를 수정하지 않고 실행용 Hadoop 묶음(`/opt/hadoop-2.7.3`)과 task 이미지(`local/hadoop-docker:2.7.3`)를 만든다.**

- 소스 전체 빌드는 dist 단계에서 실패함 [사실: `build-pass2/A/B.log`] → 공식 2.7.3 바이너리에 원 저자 YARN jar만 교체
- 파일: [original-hadoop2.7/legacy-2.7.3/](../../legacy-2.7.3/) (Dockerfile, conf, build-image.sh, cmpsig.py)

## 1. 결정 사항 (2026-10-24)

| 항목 | 결정 | 이유 |
|---|---|---|
| Hadoop 묶음 | 공식 2.7.3 + 원 저자 YARN jar 13개 교체 | 원 코드 무수정 |
| 설치 경로 | `/opt/hadoop-2.7.3` (호스트 = 이미지) | DCE가 NM 쪽 경로를 그대로 쓸 수 있음 [추측] → 같게 맞춤 |
| 이미지 안 Hadoop | 호스트와 같은 교체본 | 원 저자는 `sequenceiq/hadoop-docker:2.4.0`(Hadoop 2.4.0) 사용 [사실: 원 README] → **차이** |
| JDK | OpenJDK 8u292, `/usr/lib/jvm/java-8-openjdk-arm64` (호스트 = 이미지) | xenial에 JDK 7 없음 |
| 이미지 안 설정 | 이미지에 넣음, 바꾸면 재빌드 | DCE는 local/log/work dir만 마운트 [사실: `DockerContainerExecutor.java:210-229`] |
| 네이티브 라이브러리 | 공식 x86 `.so` 그대로 (ARM에선 Java 구현으로 대체) | ARM용 빌드 생략 |
| 컨테이너 안 계정 | root (sequenceiq와 같음) | 파일 정리 실패 여부는 기동 시 확인 |
| Spark 2.0.1 | MR pi 확인 후 추가 | 원인 분리 |

## 2. 공식 바이너리 받기

```bash
wget https://archive.apache.org/dist/hadoop/common/hadoop-2.7.3/hadoop-2.7.3.tar.gz{,.mds}
sha256sum hadoop-2.7.3.tar.gz   # d489df38…b09259c2 — .mds와 일치 [사실]
```

## 3. "공식 바이너리 + 원 저자 YARN jar = 원 저자 소스 전체 빌드" 검증

- 바이트 비교(.class sha256)는 Common/HDFS/MR도 60~100% 다름 → 의미 없음
  - 원인 [사실]: 공식 jar `Build-Jdk: 1.7.0_111`, 우리 빌드 `1.8.0_292` (class 버전은 둘 다 51)
- **javap 시그니처 비교**(클래스·필드·메서드 목록)로 전환: [cmpsig.py](../../legacy-2.7.3/cmpsig.py), 결과 [05-cmpsig.log](05-cmpsig.log)

| 구분 | 결과 [사실] |
|---|---|
| Common / HDFS / MapReduce (12 jar, 약 7,300 class) | 4 class만 다름 — 전부 컴파일러 자동 생성 `access$NNN` (JDK 7은 `access$N14`/`$N12`, JDK 8은 `access$N02`) → **소스 동일** |
| YARN 중 무수정 9 jar | 전부 동일 |
| `hadoop-yarn-api` | `YarnConfiguration` 1개 — `balloon.*` 설정 상수 추가 |
| `hadoop-yarn-server-common` | 26 class 변경 + 2 추가 (heartbeat proto 등) |
| `hadoop-yarn-server-nodemanager` | 15 변경 + 8 추가 (`NodeMemoryManager`, `ContainerMemoryState` 등) |
| `hadoop-yarn-server-resourcemanager` | 12 변경 (`RMNode`, `SchedulerNode`, `RMContainer` 등) |

- ⇒ 원 저자 수정은 YARN 4개 jar에만 있고, 나머지는 공식과 같음. 13개 전부 교체(같은 소스에서 빌드한 세트로 통일)
- 교체 위치: `share/hadoop/yarn/` 13개뿐 (다른 폴더에 YARN jar 없음 [사실]). 원본은 `~/legacy/official-yarn-jars/`에 백업

## 4. 원 저자 설정 키 [사실: 원 `YarnConfiguration` diff, README]

| 키 (`yarn.nodemanager.` +) | 기본값 | 의미 |
|---|---|---|
| `balloon.ratio` | 0.4 | 최우선 컨테이너 puff 비율 (논문 ϕ) |
| `balloon.stop` | 0.8 (README 예시는 0.9) | 노드 메모리 이 비율 넘으면 puff 중단 |
| `balloon.reclaim` | 0.9 | 이 비율 넘으면 reclaim |
| `balloon.jvm-mb` | 65536 | Flex 컨테이너 JVM 힙(`MAX_HEAP`) |
| `balloon.memory-mb` | -1 | 정적 컨테이너 크기(테스트용) |
| (변경) `container-monitor.interval-ms` 기본값 | 3000 → 2000 | |

- 이번 conf는 balloon.* 전부 기본값 유지

## 5. task 이미지 빌드

```bash
# 맥에서
scp -r -P 2214 original-hadoop2.7/legacy-2.7.3 gihyeon@127.0.0.1:legacy/
# VM에서
bash ~/legacy/legacy-2.7.3/build-image.sh   # 호스트 conf 반영 → tar → docker build
```

- 구성: `local/ubuntu:16.04` + `openjdk-8-jdk-headless` + 교체본 tar + conf + `JAVA_HOME`/`HADOOP_*` ENV
- conf (단일 노드, VM 3GB): NM 2048MB, 최소 할당 256MB, map/reduce/AM 512MB(`-Xmx384m`), DCE + 이미지 `local/hadoop-docker:2.7.3`

## 확인 포인트 / 검증 결과 [사실]

- [x] `docker build` 성공 — `local/hadoop-docker:2.7.3`, 705.8MB
- [x] 컨테이너 안 `java -version` = 1.8.0_292, `hadoop version` = 2.7.3 (호스트와 같음)
- [x] 컨테이너 vs 호스트 YARN jar 13개 sha256 전부 일치
- [x] `--net=host`에서 hostname = `pf16-worker1`
- [ ] YARN 기동 + DCE로 pi 실행 (다음 단계)

## 남은 단계

1. HDFS/YARN 단일 노드 기동 → pi 예제 (DCE 경유 확인)
2. root 소유 파일 때문에 local-dirs 정리가 실패하는지 확인
3. OCM/suspend/puff 로그 확인
4. Spark 2.0.1 추가 → VM 복제로 3대 구성
