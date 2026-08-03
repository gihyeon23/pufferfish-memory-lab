# workload-java

Pufferfish 실험에 사용하는 점진적 메모리 증가 Java 워크로드.

## 목적

`MemoryGrowthWorkload`는 실행되면 일정 시간 간격마다 고정 크기의 메모리 청크를
할당하고, 할당한 메모리를 계속 참조하여 GC가 회수하지 못하게 유지한다.
누적 할당량이 최대치에 도달하면 더 이상 할당하지 않고 메모리를 유지한 채
대기한다.

이 워크로드는 Docker 컨테이너의 메모리 사용량 증가, cgroup CPU 제한,
puff()/reclaim() 동작 등을 실험하기 위한 부하 발생기로 사용된다. 이 저장소의
현재 버전은 메모리 증가 동작만 구현하며, CPU 제한이나 cgroup 제어, Docker
연동 기능은 포함하지 않는다.

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
