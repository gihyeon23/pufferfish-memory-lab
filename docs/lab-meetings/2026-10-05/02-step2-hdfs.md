# Step 2 — JDK 17 + Hadoop 3.5.0 설치, HDFS 기동

> 로드맵: [2026-10-05.md](2026-10-05.md) §3 Step 2 / 이전 단계: [01-step1-vm-setup.md](01-step1-vm-setup.md)

## 목적

- 3대(`pf-control`, `pf-worker1`, `pf-worker2`)에 **서버용 JDK 17**과 **Hadoop 3.5.0(aarch64)** 설치
- HDFS 기동: NameNode·SecondaryNameNode = `pf-control`, DataNode = worker 2대
- Step 3(YARN)의 바탕이 되는 단계. YARN은 아직 띄우지 않는다

## 설계

| 항목 | 값 | 이유 |
|---|---|---|
| JDK | `openjdk-17-jdk-headless` (17.0.20.1) | Hadoop 3.5.0 서버 측 Java 17 필수. GUI 불필요해서 headless |
| Hadoop | `hadoop-3.5.0-aarch64.tar.gz` → `/opt/hadoop-3.5.0`, `/opt/hadoop` 심볼릭 링크 | cgroup v2 지원이 3.5.0부터 (로드맵 §2) |
| 환경 변수 | `/etc/profile.d/hadoop.sh` (`JAVA_HOME`, `HADOOP_HOME`, `HADOOP_CONF_DIR`, `PATH`) | 로그인 셸 공통 |
| `hadoop-env.sh` | `JAVA_HOME` 명시 | `start-dfs.sh`가 SSH로 띄우는 데몬은 profile.d를 안 읽음 |
| `fs.defaultFS` | `hdfs://pf-control:9000` | |
| `dfs.replication` | 2 | DataNode가 2대 |
| 데이터 경로 | `/home/gihyeon/hadoop-data/{namenode,datanode,tmp}` | 기본값(`/tmp`)은 재부팅 시 지워짐 |

- 설정 원본은 저장소 [experiments/configs/hadoop/](../../../experiments/configs/hadoop/)에 둔다
  (`core-site.xml`, `hdfs-site.xml`, `workers`). 노드에는 `/opt/hadoop/etc/hadoop/`로 복사
- 설치는 맥에서 SSH로 3대에 병렬 실행했다. 이를 위해 3대에 `/etc/sudoers.d/90-gihyeon`
  (`NOPASSWD`)을 넣었다 — 외부와 막힌 실습용 VM이라 허용. 되돌리려면 이 파일만 지운다

## 실행 방법

```bash
# 1) JDK 17 (3대)
sudo apt-get update && sudo apt-get install -y openjdk-17-jdk-headless

# 2) Hadoop — control에서 1회 내려받아 worker로 복사
curl -fLO https://downloads.apache.org/hadoop/common/hadoop-3.5.0/hadoop-3.5.0-aarch64.tar.gz
sha512sum hadoop-3.5.0-aarch64.tar.gz      # 아래 "확인 포인트"의 값과 비교
scp hadoop-3.5.0-aarch64.tar.gz pf-worker1:/tmp/   # worker2도 동일

# 3) 설치 (3대)
sudo tar -xzf hadoop-3.5.0-aarch64.tar.gz -C /opt
sudo ln -sfn /opt/hadoop-3.5.0 /opt/hadoop
sudo chown -R gihyeon:gihyeon /opt/hadoop-3.5.0
#   + /etc/profile.d/hadoop.sh 작성, hadoop-env.sh에 JAVA_HOME 추가

# 4) 설정 배포 (맥, 저장소 루트에서)
for h in pf-control pf-worker1 pf-worker2; do
  scp experiments/configs/hadoop/{core-site.xml,hdfs-site.xml,workers} $h:/opt/hadoop/etc/hadoop/
done

# 5) 포맷 + 기동 (pf-control)
hdfs namenode -format -nonInteractive -clusterId pf-cluster
start-dfs.sh
hdfs dfsadmin -report
```

정지는 `stop-dfs.sh` (pf-control). VM을 끄기 전에 실행한다.

## 확인 포인트

- 타르볼 SHA512 = `feaa20fe…0703430f` (공식 `.sha512`와 일치)
  - 공식 `.sha512` 파일 안의 파일명은 `hadoop-3.5.0.tar.gz`로 적혀 있지만 해시값은 aarch64 타르볼과 같다
- `libhadoop.so`가 `ARM aarch64` ELF인지 (`file /opt/hadoop/lib/native/libhadoop.so.1.0.0`)
- `jps`: control = NameNode + SecondaryNameNode, worker = DataNode
- `hdfs dfsadmin -report` → `Live datanodes (2)`
- 실제 파일 쓰기·읽기 + 복제본 2개 (`hdfs fsck ... -locations`)

## 검증 결과 (2026-10-05)

| 항목 | 결과 |
|---|---|
| `java -version` (3대) | `openjdk version "17.0.20.1" 2026-08-18` |
| `hadoop version` (3대) | `Hadoop 3.5.0` |
| 네이티브 라이브러리 | `ELF 64-bit LSB shared object, ARM aarch64` |
| `jps` | control: NameNode, SecondaryNameNode / worker1·2: DataNode |
| `dfsadmin -report` | **Live datanodes (2)** — `10.10.0.12:9866 (pf-worker1)`, `10.10.0.13:9866 (pf-worker2)`, 총 50.85 GB |
| 쓰기·읽기 | `hdfs dfs -put` → `-cat` 내용 일치 |
| 복제 | `Live_repl=2`, 블록이 10.10.0.12·10.10.0.13 양쪽에 존재 |

### 메모리 (HDFS 기동 직후)

| 노드 | used | available | Java 프로세스 RSS |
|---|---:|---:|---|
| pf-control (1450 MB) | 637 MB | 812 MB | NameNode 211 MB, SecondaryNameNode 148 MB |
| pf-worker1 (3396 MB) | 566 MB | 2830 MB | DataNode |
| pf-worker2 (3396 MB) | 564 MB | 2832 MB | DataNode |

- control은 HDFS만으로 available이 **812 MB**로 줄었다. Step 3에서 ResourceManager(+ 나중에
  Spark history 등)가 올라가면 빠듯할 수 있다 → Step 3에서 RM 기동 후 다시 측정하고,
  부족하면 control RAM을 2048 MB로 올리거나 SecondaryNameNode를 끄는 것을 검토한다
- worker 2대의 메모리 상태는 거의 동일 (비교 조건 유지)
