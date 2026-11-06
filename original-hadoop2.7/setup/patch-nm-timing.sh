#!/bin/bash
# Fig 6(a) 타이밍을 논문에 맞춤 (x86 steps/11): puff 주기 2초 + shrink 대기 2분
#   1) 호스트 yarn-site.xml에 container-monitor.interval-ms=2000 추가 (conf/yarn-site.xml과 같은 내용)
#   2) 패치한 NodeMemoryManager.java만 컴파일해 NM jar 안의 클래스 교체 (patches/swap-keep-time.diff)
#   원본 jar는 ~/legacy/nm-jar-orig/에 1회 백업. 되돌리기: bash patch-nm-timing.sh revert
# usage: bash patch-nm-timing.sh <패치된 NodeMemoryManager.java> | revert
set -e
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-$(dpkg --print-architecture)
H=/opt/hadoop-2.7.3
JAR=$H/share/hadoop/yarn/hadoop-yarn-server-nodemanager-2.7.3.jar
BAK=$HOME/legacy/nm-jar-orig
PKG=org/apache/hadoop/yarn/server/nodemanager/containermanager

mkdir -p "$BAK"; [ -f "$BAK/$(basename $JAR)" ] || cp -p "$JAR" "$BAK/"
if [ "$1" = revert ]; then
  cp -p "$BAK/$(basename $JAR)" "$JAR"; echo "NM jar 원본 복구 (yarn-site interval은 그대로)"; exit 0
fi

SITE=$H/etc/hadoop/yarn-site.xml
grep -q container-monitor.interval-ms "$SITE" || sed -i 's#</configuration>#  <property>\n    <name>yarn.nodemanager.container-monitor.interval-ms</name>\n    <value>2000</value>\n  </property>\n</configuration>#' "$SITE"
grep -A1 container-monitor.interval-ms "$SITE" | grep value

W=$(mktemp -d)
mkdir -p "$W/src/$PKG" "$W/out"
cp "$1" "$W/src/$PKG/"
# 원 jar가 Java 7 클래스(major 51)라 같은 버전으로 컴파일. 클래스패스 맨 앞에 원본 NM jar
javac -g -nowarn -encoding UTF-8 -source 1.7 -target 1.7 -cp "$BAK/$(basename $JAR):$($H/bin/yarn classpath)" \
  -d "$W/out" "$W/src/$PKG/NodeMemoryManager.java" 2>&1 | grep -v "bootstrap class path" || true
cp -p "$BAK/$(basename $JAR)" "$JAR"
(cd "$W/out" && jar uf "$JAR" $PKG/NodeMemoryManager*.class)
unzip -l "$JAR" | grep "NodeMemoryManager.class"
rm -rf "$W"
echo "NM 재시작 필요: cd $H && sbin/yarn-daemon.sh stop nodemanager && sbin/yarn-daemon.sh start nodemanager"
