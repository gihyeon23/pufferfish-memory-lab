# workload-java

Pufferfish 실험에 사용하는 점진적 메모리 증가 Java 워크로드.

## 목적

`MemoryGrowthWorkload`는 실행되면 일정 시간 간격마다 고정 크기의 메모리 청크를
할당하고, 할당한 메모리를 계속 참조하여 GC가 회수하지 못하게 유지한다.
누적 할당량이 최대치에 도달하면 더 이상 할당하지 않고 메모리를 유지한 채
대기한다.

이 워크로드는 Docker 컨테이너의 메모리 사용량 증가, cgroup CPU 제한,
puff()/reclaim() 동작 등을 실험하기 위한 부하 발생기로 사용된다. CPU
제한이나 cgroup 제어는 이 워크로드 자체가 아니라 `controller/`의 스크립트가
컨테이너 바깥에서 수행한다.

Java 21과 표준 라이브러리만 사용하며 외부 의존성은 없다.

## 컴파일

```bash
cd workload-java
javac -d out src/main/java/lab/pufferfish/MemoryGrowthWorkload.java
```

## 기본 설정으로 실행

기본값은 32MiB씩, 5초 간격으로, 최대 512MiB까지 누적 할당한다.

```bash
java -cp out lab.pufferfish.MemoryGrowthWorkload
```

## 환경변수

| 변수명 | 설명 | 기본값 |
| --- | --- | --- |
| `CHUNK_SIZE_MB` | 한 번에 증가시킬 메모리 크기(MiB) | 32 |
| `INTERVAL_SECONDS` | 할당 간격(초) | 5 |
| `MAX_ALLOCATION_MB` | 최대 누적 할당량(MiB) | 512 |

환경변수를 변경해 실행하는 예시:

```bash
CHUNK_SIZE_MB=32 INTERVAL_SECONDS=1 MAX_ALLOCATION_MB=96 \
  java -cp out lab.pufferfish.MemoryGrowthWorkload
```

## JVM 최대 힙 크기 지정

`MAX_ALLOCATION_MB`가 JVM 힙 크기보다 크면 `OutOfMemoryError`가 발생할 수
있으므로, 실험 목적에 맞게 `-Xmx`로 힙 크기를 지정한다.

```bash
CHUNK_SIZE_MB=32 INTERVAL_SECONDS=5 MAX_ALLOCATION_MB=512 \
  java -Xmx1g -cp out lab.pufferfish.MemoryGrowthWorkload
```

## 실행 중 메모리 사용량 확인

프로그램은 매 할당 시점마다 다음 정보를 표준 출력에 기록한다.

- 현재 시각
- 할당 횟수
- 이번에 추가한 메모리 크기
- 누적 유지 중인 메모리 크기
- JVM used / committed / max 메모리 (heap 기준)

프로세스 외부에서 관찰하려면 다음과 같은 방법도 사용할 수 있다.

```bash
# 프로세스의 RSS(실제 사용 물리 메모리) 확인
ps -o pid,rss,vsz,cmd -p <PID>

# 컨테이너로 실행 중이라면
docker stats <container_name>
```

## Docker로 실행

```bash
docker build -t pufferfish/workload-java:latest .

docker run -d --name pf-test \
  --memory=256m --memory-swap=768m \
  -e CHUNK_SIZE_MB=32 -e INTERVAL_SECONDS=2 -e MAX_ALLOCATION_MB=512 \
  -e JAVA_OPTS="-Xmx700m" \
  pufferfish/workload-java:latest
```

`JAVA_OPTS` 환경변수로 임의의 JVM 플래그를 주입할 수 있다(엔트리포인트가
`sh -c`로 `$JAVA_OPTS`를 전개한다). 컨테이너 메모리 한도(`--memory`) 내에서
JVM이 기본으로 잡는 최대 힙은 그 한도보다 작게 잡히므로, 힙이 cgroup 메모리
한도를 실제로 초과해 swap을 유발하게 하려면 `-Xmx`를 명시적으로 한도보다
크게 지정해야 한다. cgroup 상태 모니터링과 CPU 제한은
[`controller/`](../controller)를 참고한다.
