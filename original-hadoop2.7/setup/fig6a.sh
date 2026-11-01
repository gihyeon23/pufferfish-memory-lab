#!/bin/bash
# Fig 6(a) puff() 재현 (논문 §5.2 [p.265]): PageRank 1개(container-1) → KMeans 2개(container-2·3)를 차례로 제출
#   job마다 Flex executor 1개 · 1코어 · 1g (hibench-conf/spark.conf), 데이터 = Table 1 Small의 1/4 (pufferfish.conf)
#   제출 간격: 논문 6(a)엔 없음 → 같은 절 Fig 7의 120초 [p.266] 사용 [우리]
#   HiBench run.sh를 동시에 돌리면 출력·리포트 폴더가 겹쳐서, HiBench가 만든 spark-submit 명령을 그대로 직접 실행
#   (HiBench가 넘기는 환경변수 SPARKBENCH_PROPERTIES_FILES·HADOOP_CONF_DIR도 같게)
# 사전: pagerank·kmeans prepare 완료, 각 workload를 run.sh로 한 번 돌려 report/<w>/spark/conf가 있어야 함
# usage: bash fig6a.sh [간격초]   (기본 120) → ~/hibench-logs/fig6a-<시각>/
set -e
IV=${1:-120}
HERE=$(cd "$(dirname "$0")" && pwd)
H=/opt/HiBench-6.0
S=/opt/spark-2.0.1-bin-hadoop2.7
ARCH=$(dpkg --print-architecture)
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-$ARCH
export HADOOP_CONF_DIR=/opt/hadoop-2.7.3/etc/hadoop
NMLOG=$(ls /opt/hadoop-2.7.3/logs/yarn-*-nodemanager-*.log)
OUT=$HOME/hibench-logs/fig6a-$(date +%m%d-%H%M)
JAR=$H/sparkbench/assembly/target/sparkbench-assembly-6.0-dist.jar
HDFS=hdfs://ubuntu:9000/HiBench
mkdir -p $OUT

submit() {  # submit <이름> <workload> <클래스> <인자...>
  local name=$1 w=$2 cls=$3; shift 3
  ( export SPARKBENCH_PROPERTIES_FILES=$H/report/$w/spark/conf/sparkbench/sparkbench.conf
    s=$(date +%s); rc=0; echo "$(date +%T) submit $name" >> $OUT/events.log
    $S/bin/spark-submit --properties-file $H/report/$w/spark/conf/sparkbench/spark.conf \
      --name $name --class $cls --master yarn-client \
      --num-executors 1 --executor-cores 1 --executor-memory 1g $JAR "$@" > $OUT/$name.log 2>&1 || rc=$?
    echo "$(date +%T) end $name exit=$rc sec=$(( $(date +%s) - s ))" >> $OUT/events.log ) &
}

/opt/hadoop-2.7.3/bin/hdfs dfs -rm -r -f -skipTrash $HDFS/Pagerank/Output-fig6a > /dev/null
nm0=$(wc -l < $NMLOG)
bash $HERE/watch-containers.sh > $OUT/watch.log 2>&1 &
W=$!
echo "interval=${IV}s start=$(date +%F' '%T)" > $OUT/events.log

submit fig6a-pr  pagerank org.apache.spark.examples.SparkPageRank $HDFS/Pagerank/Input/edges $HDFS/Pagerank/Output-fig6a 3
sleep $IV
submit fig6a-km1 kmeans com.intel.hibench.sparkbench.ml.DenseKMeans -k 10 --numIterations 5 $HDFS/Kmeans/Input/samples
sleep $IV
submit fig6a-km2 kmeans com.intel.hibench.sparkbench.ml.DenseKMeans -k 10 --numIterations 5 $HDFS/Kmeans/Input/samples
while [ $(grep -c "^.* end " $OUT/events.log) -lt 3 ]; do sleep 5; done
sleep 4; kill $W

tail -n +$((nm0 + 1)) $NMLOG | sed -E 's/org\.apache\.hadoop\.yarn\.server\.nodemanager\.containermanager\.//' > $OUT/nm.log
# 앱 ID ↔ job 이름 (HiBench 앱은 코드에서 이름을 정해 --name이 무시됨 → 각 job 로그의 앱 ID로 대응)
for n in fig6a-pr fig6a-km1 fig6a-km2; do
  echo "$(grep -a -o -m1 'application_[0-9]*_[0-9]*' $OUT/$n.log) $n"
done > $OUT/apps.txt
cat $OUT/events.log
echo "-> $OUT"
