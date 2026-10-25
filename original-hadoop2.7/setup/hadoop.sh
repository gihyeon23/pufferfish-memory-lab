#!/bin/bash
# 단일 노드 HDFS/YARN 데몬 시작·중지 (SSH-to-localhost 없이 데몬을 직접 띄움)
# usage: bash hadoop.sh start|stop|status
set -e
ARCH=$(dpkg --print-architecture)
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-$ARCH
H=/opt/hadoop-2.7.3
cd $H
case $1 in
  start)
    # 최초 1회만 포맷 (hadoop.tmp.dir = core-site.xml)
    [ -d "$HOME/hadoop-data/dfs/name/current" ] || bin/hdfs namenode -format -nonInteractive >/dev/null 2>&1
    sbin/hadoop-daemon.sh start namenode;  sbin/hadoop-daemon.sh start datanode
    sbin/yarn-daemon.sh start resourcemanager; sbin/yarn-daemon.sh start nodemanager
    bin/hdfs dfsadmin -safemode wait >/dev/null
    bin/hdfs dfs -mkdir -p /user/$USER
    sleep 10; "$0" status ;;
  stop)
    sbin/yarn-daemon.sh stop nodemanager; sbin/yarn-daemon.sh stop resourcemanager
    sbin/hadoop-daemon.sh stop datanode;  sbin/hadoop-daemon.sh stop namenode ;;
  status)
    jps | grep -v Jps
    bin/hdfs dfsadmin -report 2>/dev/null | grep "Live datanodes" || true
    bin/yarn node -list 2>/dev/null | tail -n +2 || true ;;
  *) echo "usage: $0 start|stop|status"; exit 1 ;;
esac
