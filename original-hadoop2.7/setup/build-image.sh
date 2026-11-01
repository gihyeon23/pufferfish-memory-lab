#!/bin/bash
# VM(단일 노드)에서 실행: 호스트 설정 반영 → 교체본 tar 생성 → task 이미지 빌드
# 전제: install-host.sh(/opt/hadoop-2.7.3 + YARN jar 교체), prepare-base-image.sh(베이스 이미지) 완료
# usage: build-image.sh [sequenceiq|jdk7|jdk8]   (기본: amd64는 sequenceiq — x86-server/steps/03, arm64는 jdk7 — 05 §7)
#   sequenceiq: 원 이미지 sequenceiq/hadoop-docker:2.4.0(CentOS 6.5 + Oracle JDK 7u51) → local/hadoop-docker:2.7.3-sequenceiq
#               (먼저 fetch-sequenceiq-image.py → docker load, x86 전용)
#   jdk7: local/centos:7 + OpenJDK 7 → local/hadoop-docker:2.7.3-jdk7
#   jdk8: local/ubuntu:16.04 + OpenJDK 8 → local/hadoop-docker:2.7.3-jdk8 (비교용)
set -e
ARCH=$(dpkg --print-architecture)              # amd64 | arm64
[ $ARCH = amd64 ] && VARIANT=${1:-sequenceiq} || VARIANT=${1:-jdk7}
H=/opt/hadoop-2.7.3
HERE=$(cd "$(dirname "$0")" && pwd)
# 호스트 NM/RM은 JDK 8로 실행 (task JDK는 이미지 ENV — yarn-site env-whitelist에서 JAVA_HOME 제외)
JAVA_HOME=/usr/lib/jvm/java-8-openjdk-$ARCH

# 1) 설정 생성: conf/의 @HOST@·@HOME@·@YARN_MB@·@JVM_MB@을 채움 → 호스트·이미지가 같은 파일을 씀
#    YARN_MB·JVM_MB 기본 = x86 워커(steps/01 §3). 맥 VM: YARN_MB=2048 JVM_MB=65536 bash build-image.sh jdk7
YARN_MB=${YARN_MB:-28672}
JVM_MB=${JVM_MB:-16384}
CTX=$(mktemp -d)
mkdir "$CTX/conf"
for f in "$HERE"/conf/*.xml; do
  sed -e "s#@HOST@#$(hostname)#g" -e "s#@HOME@#$HOME#g" \
      -e "s#@YARN_MB@#$YARN_MB#g" -e "s#@JVM_MB@#$JVM_MB#g" "$f" > "$CTX/conf/$(basename "$f")"
done
# NM이 띄울 task 이미지 = 이번에 빌드하는 이미지
sed -i "s#local/hadoop-docker:2.7.3-[a-z0-9]*#local/hadoop-docker:2.7.3-$VARIANT#" "$CTX/conf/yarn-site.xml"
cp "$CTX"/conf/*.xml $H/etc/hadoop/
for f in hadoop-env.sh yarn-env.sh mapred-env.sh; do
  grep -q "^export JAVA_HOME=$JAVA_HOME" $H/etc/hadoop/$f || echo "export JAVA_HOME=$JAVA_HOME" >> $H/etc/hadoop/$f
done

# 2) 교체본 tar (로그 제외, 설정은 Dockerfile에서 따로 COPY)
tar czf "$CTX/hadoop-2.7.3-pufferfish.tar.gz" --exclude=hadoop-2.7.3/logs -C /opt hadoop-2.7.3
cp "$HERE/Dockerfile.$VARIANT" "$CTX/Dockerfile"
# CentOS 7 지원 종료 → vault (aarch64는 altarch 경로)
case $ARCH in
  amd64) VAULT=http://vault.centos.org/7.9.2009 ; C7=x86_64 ;;
  arm64) VAULT=http://vault.centos.org/altarch/7.9.2009 ; C7=aarch64 ;;
esac
printf '[base]\nname=CentOS-7.9.2009 base (vault)\nbaseurl=%s/os/%s/\ngpgcheck=0\n\n[updates]\nname=CentOS-7.9.2009 updates (vault)\nbaseurl=%s/updates/%s/\ngpgcheck=0\n' \
  $VAULT $C7 $VAULT $C7 > "$CTX/vault.repo"

# 3) 이미지 빌드
docker build --build-arg JAVA8_HOME=/usr/lib/jvm/java-8-openjdk-$ARCH -t local/hadoop-docker:2.7.3-$VARIANT "$CTX"
rm -rf "$CTX"
docker images local/hadoop-docker
