# 02. VM 접속 설정 · install-host.sh 실행 (2026-11-01)

> 접속 정보(IP·포트·키 파일)는 저장소에 남기지 않는다. 맥 `~/.ssh/config`의 `labvm` 별칭으로만 표기.

## 1. 목적

- 할당받은 x86 VM에 접속하고, [../../setup/install-host.sh](../../setup/install-host.sh)로 호스트 환경(Docker 1.12.1, swapaccount, Hadoop 2.7.3 + 원 저자 YARN jar) 구성

## 2. 접속 설정 (맥)

- 개인키를 `~/.ssh/`로 옮기고 권한 `400` (기본 `644`면 ssh가 키를 무시하고 비밀번호를 물음)
- `~/.ssh/config`에 `Host labvm` 추가 → `ssh labvm`으로 접속
- `scp`는 저장소 절대경로로 실행 (키 폴더에서 상대경로 `original-hadoop2.7/setup`을 쓰면 `No such file`)

```bash
ssh labvm "mkdir -p ~/legacy"
scp -r ~/pufferfish-memory-lab/original-hadoop2.7/setup labvm:legacy/
```

## 3. 수령 직후 확인 (VM)

| 항목 | 결과 | 판정 |
|---|---|---|
| OS | Ubuntu 16.04.7 LTS | OK |
| 커널 `uname -r` | 4.4.0-186-generic | OK (16.04 기본 4.4 계열) |
| `nproc` | 8 | OK (맥 VM과 달리 전부 보임) |
| `uname -m` | x86_64 | OK |
| glibc | 2.23 | 16.04 기본 |
| `/sys/fs/cgroup` | tmpfs | cgroup v1 |
| sudo | NOPASSWD | 스크립트 무인 실행 가능 |
| yarn-jars 복사 | 13개 | OK |

## 4. install-host.sh 결과

```
Server Version: 1.12.1 / Storage Driver: aufs / Cgroup Driver: cgroupfs
GRUB에 swapaccount=1 추가, 재부팅 필요
YARN jar 13개 = 원 저자 빌드본
NodeMemoryManager 포함 확인
```

- Docker 1.12.1·aufs·cgroupfs — 논문 환경과 같은 조합
- docker 그룹 추가됨 → 재로그인 후 `sudo` 없이 `docker` 사용 가능

## 5. 다음 (실행 방법 · 확인 포인트)

```bash
sudo reboot
# 재접속 후
grep -o swapaccount=1 /proc/cmdline     # swapaccount 적용
id -nG | grep -w docker                 # docker 그룹 적용
free -h; df -h /                        # 메모리·디스크가 steps/01 사양과 맞는지
bash ~/legacy/setup/prepare-base-image.sh
bash ~/legacy/setup/build-image.sh jdk7
bash ~/legacy/setup/hadoop.sh start
```

- 확인 필요: 이 VM이 master/worker 중 어느 노드인지 (8 vCPU라 worker로 **추측**), 나머지 2대 수령 여부

## 6. 재부팅 후 확인

| 항목 | 결과 | 판정 |
|---|---|---|
| `/proc/cmdline` | `swapaccount=1` | OK |
| docker 그룹 | 포함 | OK |
| 메모리 | 31G | OK — worker 사양(32GB) → 이 VM은 **worker** |
| 디스크 `/` | 196G (사용 2.4G) | OK |
| swap | 979M (설치 기본값) | steps/01 §3 계획(32GB swapfile)과 다름 → [04](04-swap-32gb.md)에서 32GB로 변경 |

## 7. prepare-base-image.sh 중단 — 원인 · 수정

- 증상: 아무 출력 없이 멈춘 것처럼 보여 `^C`로 중단
- 원인(**추측**): `wget -q`라 진행률이 안 보였음. 다운로드 중이었는지 네트워크에서 막혔는지 로그로는 구분 안 됨
- 문제: 중간에 끊기면 덜 받은 파일이 남는데, 스크립트는 `[ -f 파일 ]`로 "이미 받음"이라고 판단하고 `tar`에서 실패함
- 수정: [../../setup/prepare-base-image.sh](../../setup/prepare-base-image.sh)에 `fetch()` 추가 — 진행률을 보여주고, `.part`로 받은 뒤 다 받으면 이름을 바꿈

## 8. 검증 결과

- 접속·사전 확인·install-host.sh·재부팅 확인 완료
- prepare-base-image.sh: 스크립트만 수정함. **VM에서 다시 실행해서 확인할 예정**
