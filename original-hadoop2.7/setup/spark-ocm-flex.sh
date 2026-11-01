#!/bin/bash
# 06b: Flex executor에 메모리를 채워 OCM → puff 유도 (ocm-cache.scala)
#   client 모드(spark-shell): driver는 호스트(JDK 8), AM·executor는 task 이미지(JDK 7)
#   spark.yarn.am.nodeLabelExpression은 AM 요청에 붙으므로 client 모드에서도 Flex가 됨 (추측 — NM 로그로 확인)
# usage: bash spark-ocm-flex.sh [MB_PER_EXEC] [HOLD_SEC]   (기본 3000 60)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ARCH=$(dpkg --print-architecture)
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-$ARCH
export HADOOP_CONF_DIR=/opt/hadoop-2.7.3/etc/hadoop
export MB_PER_EXEC=${1:-3000} HOLD_SEC=${2:-60}
S=/opt/spark-2.0.1-bin-hadoop2.7
$S/bin/spark-shell --master yarn --deploy-mode client \
  --conf spark.yarn.am.nodeLabelExpression=flex \
  --num-executors 2 --executor-memory 1g --executor-cores 1 \
  -i "$HERE/ocm-cache.scala"
