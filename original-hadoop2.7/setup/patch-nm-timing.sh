#!/bin/bash
# Fig 6(a) 타이밍을 논문에 맞춤 (x86 steps/11): puff 주기 2초 + shrink 대기 2분
#   1) 호스트 yarn-site.xml에 container-monitor.interval-ms=2000 추가 (conf/yarn-site.xml과 같은 내용)
#   2) 패치한 NodeMemoryManager.java만 컴파일해 NM jar 안의 클래스 교체 (patches/swap-keep-time.diff)
#   원본 jar는 ~/legacy/nm-jar-orig/에 1회 백업. 되돌리기: bash patch-nm-timing.sh revert
# usage: bash patch-nm-timing.sh <패치된 .java> [<패치된 .java> ...] | revert
#   여러 파일 가능 (steps/17 C부터 ContainerImpl.java 추가). 패키지 경로는 각 파일의 package 줄에서 읽음
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
mkdir -p "$W/out"
SRCS=(); CLS=()
for f in "$@"; do
  pkg=$(sed -n 's/^package \(.*\);/\1/p' "$f" | head -1 | tr . /)
  mkdir -p "$W/src/$pkg"; cp "$f" "$W/src/$pkg/"
  SRCS+=("$W/src/$pkg/$(basename "$f")"); CLS+=("$pkg/$(basename "$f" .java)")
done
# 원 jar가 Java 7 클래스(major 51)라 같은 버전으로 컴파일. 클래스패스 맨 앞에 원본 NM jar
javac -g -nowarn -encoding UTF-8 -source 1.7 -target 1.7 -cp "$BAK/$(basename $JAR):$($H/bin/yarn classpath)" \
  -d "$W/out" "${SRCS[@]}" 2>&1 | grep -v "bootstrap class path" || true
for c in "${CLS[@]}"; do ls "$W/out/$c.class" > /dev/null; done   # 컴파일 실패면 여기서 중단 (jar 안 건드림)
cp -p "$BAK/$(basename $JAR)" "$JAR"
(cd "$W/out" && jar uf "$JAR" $(cd "$W/out" && for c in "${CLS[@]}"; do ls $c.class $c\$*.class 2>/dev/null; done))
for c in "${CLS[@]}"; do unzip -l "$JAR" | grep " $c.class"; done
rm -rf "$W"
echo "NM 재시작 필요: cd $H && sbin/yarn-daemon.sh stop nodemanager && sbin/yarn-daemon.sh start nodemanager"
