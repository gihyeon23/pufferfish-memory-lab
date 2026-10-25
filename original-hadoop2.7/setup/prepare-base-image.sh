#!/bin/bash
# task 이미지의 베이스를 Docker Hub 없이 준비 (Docker 1.12.1은 현재 Docker Hub pull 불가)
#   local/centos:7    — CentOS Cloud SIG rootfs (JDK 7 이미지용)
#   local/ubuntu:16.04 — Ubuntu base (JDK 8 비교 이미지용)
# CentOS rootfs는 SELinux xattr 때문에 aufs에서 파일 쓰기가 실패 → xattr 없이 다시 묶어 import
# usage: bash prepare-base-image.sh
set -e
ARCH=$(dpkg --print-architecture)              # amd64 | arm64
case $ARCH in
  amd64) C7=x86_64 ;;
  arm64) C7=aarch64 ;;
  *) echo "지원 안 하는 arch: $ARCH"; exit 1 ;;
esac
DL=${DL:-$HOME/legacy/dl}
mkdir -p "$DL/centos7"

if docker images -q local/centos:7 | grep -q .; then
  echo "local/centos:7 이미 있음"
else
  cd "$DL/centos7"
  [ -f centos-7-$C7-docker.tar.xz ] || wget -q \
    https://raw.githubusercontent.com/CentOS/sig-cloud-instance-images/CentOS-7-$C7/docker/centos-7-$C7-docker.tar.xz
  sudo rm -rf rootfs && mkdir rootfs
  sudo tar --no-xattrs --no-selinux --no-acls -xJf centos-7-$C7-docker.tar.xz -C rootfs
  sudo tar --no-xattrs --no-selinux --no-acls -C rootfs -c . | docker import - local/centos:7 >/dev/null
  sudo rm -rf rootfs
  cd - >/dev/null
fi
docker run --rm local/centos:7 bash -c 'touch /tmp/x && cat /etc/centos-release'

if docker images -q local/ubuntu:16.04 | grep -q .; then
  echo "local/ubuntu:16.04 이미 있음"
else
  cd "$DL"
  [ -f ubuntu-base-16.04.6-base-$ARCH.tar.gz ] || wget -q \
    https://cdimage.ubuntu.com/ubuntu-base/releases/16.04/release/ubuntu-base-16.04.6-base-$ARCH.tar.gz
  docker import ubuntu-base-16.04.6-base-$ARCH.tar.gz local/ubuntu:16.04 >/dev/null
  cd - >/dev/null
fi
docker images | grep -E "^local/(centos|ubuntu)"
