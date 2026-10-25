#!/bin/bash
# Ubuntu 16.04 VM에서 실행: 원 구현(YARN 2.7.3 + Pufferfish) 실행 환경을 한 번에 구성
#   1) 빌드·실행 도구 (호스트 NM/RM용 OpenJDK 8 등)
#   2) Docker 1.12.1 (논문 버전, 2016-10-14 Launchpad 빌드) + hold
#   3) swap accounting (커널 옵션 swapaccount=1) — 원 코드 OCM 판정에 필요
#   4) 공식 Hadoop 2.7.3 → /opt/hadoop-2.7.3, YARN jar 13개를 원 저자 빌드본으로 교체
# 여러 번 실행해도 됨 (이미 된 단계는 건너뜀). arm64·amd64 자동 판별.
# usage: bash install-host.sh            (같은 폴더의 yarn-jars/ 사용)
#        YARN_JARS_DIR=/path bash install-host.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ARCH=$(dpkg --print-architecture)              # amd64 | arm64
YARN_JARS_DIR=${YARN_JARS_DIR:-$HERE/yarn-jars}
DL=${DL:-$HOME/legacy/dl}
H=/opt/hadoop-2.7.3
LP=https://launchpad.net/ubuntu/+archive/primary/+files
REBOOT=0

echo "== 0) 환경: $(lsb_release -ds), 커널 $(uname -r), $ARCH, CPU $(nproc)개"
grep -q 'VERSION_ID="16.04"' /etc/os-release || { echo "Ubuntu 16.04가 아님 — 중단"; exit 1; }
[ "$(uname -r | cut -d. -f1-2)" = "4.4" ] || echo "⚠️ 커널이 4.4가 아님 (논문 당시 16.04 기본 커널은 4.4)"
mkdir -p "$DL"

echo "== 1) 도구"
sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q openjdk-8-jdk-headless wget curl unzip python3 >/dev/null

echo "== 2) Docker 1.12.1"
if dpkg -s docker.io 2>/dev/null | grep -q '^Version: 1.12.1-0ubuntu13~16.04.1'; then
  echo "이미 설치됨"
else
  cd "$DL"
  for p in "containerd_0.2.3-0ubuntu1~16.04_$ARCH.deb" "runc_1.0.0~rc1-0ubuntu1~16.04_$ARCH.deb" \
           "docker.io_1.12.1-0ubuntu13~16.04.1_$ARCH.deb"; do
    [ -f "$p" ] || wget -q "$LP/$p"
  done
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q ./containerd_*_$ARCH.deb ./runc_*_$ARCH.deb ./docker.io_*_$ARCH.deb >/dev/null
  cd - >/dev/null
fi
sudo apt-mark hold docker.io containerd runc >/dev/null
id -nG "$USER" | grep -qw docker || { sudo usermod -aG docker "$USER"; echo "docker 그룹 추가 (재로그인 후 적용)"; }
sudo docker info 2>/dev/null | grep -E "Server Version|Storage Driver|Cgroup Driver"

echo "== 3) swap accounting"
if grep -q swapaccount=1 /proc/cmdline; then
  echo "이미 적용됨"
elif grep -q '^GRUB_CMDLINE_LINUX=.*swapaccount=1' /etc/default/grub; then
  echo "설정됨, 재부팅 필요"; REBOOT=1
else
  sudo sed -i 's/^GRUB_CMDLINE_LINUX="\(.*\)"/GRUB_CMDLINE_LINUX="\1 swapaccount=1"/' /etc/default/grub
  sudo update-grub >/dev/null 2>&1
  echo "GRUB에 swapaccount=1 추가, 재부팅 필요"; REBOOT=1
fi

echo "== 4) Hadoop 2.7.3 + 원 저자 YARN jar"
cd "$DL"
[ -f hadoop-2.7.3.tar.gz ] || wget -q https://archive.apache.org/dist/hadoop/common/hadoop-2.7.3/hadoop-2.7.3.tar.gz
echo "d489df3808244b906eb38f4d081ba49e50c4603db03efd5e594a1e98b09259c2  hadoop-2.7.3.tar.gz" | sha256sum -c --quiet
cd - >/dev/null
if [ ! -d $H ]; then
  sudo tar xzf "$DL/hadoop-2.7.3.tar.gz" -C /opt
  sudo chown -R "$USER:$USER" $H
  mkdir -p "$HOME/legacy/official-yarn-jars"
  cp $H/share/hadoop/yarn/hadoop-yarn-*-2.7.3.jar "$HOME/legacy/official-yarn-jars/"   # baseline용 원본 백업
fi
(cd "$YARN_JARS_DIR" && sha256sum -c --quiet "$HERE/yarn-jars.sha256")
cp "$YARN_JARS_DIR"/hadoop-yarn-*-2.7.3.jar $H/share/hadoop/yarn/
(cd $H/share/hadoop/yarn && sha256sum -c --quiet "$HERE/yarn-jars.sha256") && echo "YARN jar 13개 = 원 저자 빌드본"
unzip -l $H/share/hadoop/yarn/hadoop-yarn-server-nodemanager-2.7.3.jar | grep -q NodeMemoryManager && echo "NodeMemoryManager 포함 확인"

echo "== 완료"
[ $REBOOT = 1 ] && echo "⚠️ swapaccount 적용을 위해 재부팅: sudo reboot"
echo "다음: bash $HERE/prepare-base-image.sh → bash $HERE/build-image.sh jdk7 → bash $HERE/hadoop.sh start"
