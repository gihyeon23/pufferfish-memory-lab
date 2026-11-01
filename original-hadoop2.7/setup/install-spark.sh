#!/bin/bash
# 호스트에 Spark 2.0.1 (논문 버전, p.265) 설치 → /opt/spark-2.0.1-bin-hadoop2.7
# executor·AM은 YARN이 task 이미지 안에서 띄우므로 Spark는 호스트(spark-submit 쪽)에만 있으면 됨
# 여러 번 실행해도 됨. usage: bash install-spark.sh
set -e
DL=${DL:-$HOME/legacy/dl}
S=/opt/spark-2.0.1-bin-hadoop2.7
mkdir -p "$DL"
cd "$DL"
[ -f spark-2.0.1-bin-hadoop2.7.tgz ] || {
  wget -q --show-progress -O spark-2.0.1-bin-hadoop2.7.tgz.part \
    https://archive.apache.org/dist/spark/spark-2.0.1/spark-2.0.1-bin-hadoop2.7.tgz
  mv spark-2.0.1-bin-hadoop2.7.tgz.part spark-2.0.1-bin-hadoop2.7.tgz
}
# Apache 공식 체크섬 (2.0.1은 .md5만 남아 있음)
echo "43aa7c28b9670e65cb4f395000838860  spark-2.0.1-bin-hadoop2.7.tgz" | md5sum -c --quiet
cd - >/dev/null
if [ ! -d $S ]; then
  sudo tar xzf "$DL/spark-2.0.1-bin-hadoop2.7.tgz" -C /opt
  sudo chown -R "$USER:$USER" $S
fi
$S/bin/spark-submit --version 2>&1 | grep -m1 -o "version [0-9.]*"
