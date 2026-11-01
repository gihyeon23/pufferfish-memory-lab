#!/bin/bash
# 호스트에 HiBench 6.0 빌드 → /opt/HiBench-6.0 (논문 워크로드 출처 [22])
# 버전은 논문·원 코드에 없음 → 원 저자 로그(2017-02) 시점 최신인 6.0 선택 (x86-server/steps/07 §2)
# sparkbench만 빌드 (WC·KM·PR·NW). -Dspark=2.0이면 Scala 2.11.8. Maven 필요 (apt maven 3.3.9)
# 여러 번 실행해도 됨. usage: bash install-hibench.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
V=6.0
DL=${DL:-$HOME/legacy/dl}
H=/opt/HiBench-$V
mkdir -p "$DL"
cd "$DL"
[ -f HiBench-$V.tar.gz ] || {
  wget -q --show-progress -O HiBench-$V.tar.gz.part \
    https://github.com/Intel-bigdata/HiBench/archive/HiBench-$V.tar.gz
  mv HiBench-$V.tar.gz.part HiBench-$V.tar.gz
}
sha256sum HiBench-$V.tar.gz
cd - >/dev/null
if [ ! -d $H ]; then
  sudo mkdir -p $H
  sudo chown "$USER:$USER" $H
  tar xzf "$DL/HiBench-$V.tar.gz" -C $H --strip-components=1
fi
cd $H
ls sparkbench/assembly/target/*-dist.jar >/dev/null 2>&1 || \
  mvn -q -Psparkbench -Dspark=2.0 clean package -DskipTests
ls -la autogen/target/*.jar sparkbench/assembly/target/*.jar
# 우리 설정 (hadoop.conf · spark.conf · pufferfish.conf) — 템플릿 대신 사용
cp "$HERE/hibench-conf/"*.conf conf/
ls conf/*.conf
