#!/bin/bash
# Spark on YARN을 Flex로 실행 (원 README: spark.yarn.am.nodeLabelExpression flex)
#   RM이 AM 라벨 "flex"를 지우고 isFlex=true로 표시 → NM이 AM 외 컨테이너(executor)를 Flexible로
#   (RMAppManager.java:330-357, ContainerManagerImpl.java:841-847) — node label 기능은 켤 필요 없음
# cluster 모드: driver(AM)도 task 이미지(JDK 7) 안에서 실행
# usage: bash spark-pi-flex.sh [executors] [executor-memory] [slices]   (기본 2 1g 100)
set -e
ARCH=$(dpkg --print-architecture)
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-$ARCH          # spark-submit(호스트)용
export HADOOP_CONF_DIR=/opt/hadoop-2.7.3/etc/hadoop
S=/opt/spark-2.0.1-bin-hadoop2.7
$S/bin/spark-submit --master yarn --deploy-mode cluster \
  --conf spark.yarn.am.nodeLabelExpression=flex \
  --num-executors ${1:-2} --executor-memory ${2:-1g} --executor-cores 1 \
  --class org.apache.spark.examples.SparkPi \
  $S/examples/jars/spark-examples_2.11-2.0.1.jar ${3:-100}
