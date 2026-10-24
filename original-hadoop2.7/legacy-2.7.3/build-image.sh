#!/bin/bash
# VM(pf16-worker1)에서 실행: 호스트 설정 반영 → 교체본 tar 생성 → task 이미지 빌드
# 전제: /opt/hadoop-2.7.3 = 공식 2.7.3 + 원 저자 YARN jar 13개 교체 완료
set -e
H=/opt/hadoop-2.7.3
HERE=$(cd "$(dirname "$0")" && pwd)
JAVA_HOME=/usr/lib/jvm/java-8-openjdk-arm64

# 1) 호스트 설정 (이미지와 같은 파일)
cp "$HERE"/conf/*.xml $H/etc/hadoop/
for f in hadoop-env.sh yarn-env.sh mapred-env.sh; do
  grep -q "^export JAVA_HOME=$JAVA_HOME" $H/etc/hadoop/$f || echo "export JAVA_HOME=$JAVA_HOME" >> $H/etc/hadoop/$f
done

# 2) 교체본 tar (설정은 Dockerfile에서 따로 COPY)
CTX=$(mktemp -d)
tar czf "$CTX/hadoop-2.7.3-pufferfish.tar.gz" -C /opt hadoop-2.7.3
cp -r "$HERE/Dockerfile" "$HERE/conf" "$CTX/"

# 3) 이미지 빌드
docker build -t local/hadoop-docker:2.7.3 "$CTX"
rm -rf "$CTX"
docker images local/hadoop-docker
