# Experiment Environment

## Host

- MacBook Apple M4
- VirtualBox 7.2
- Ubuntu Server 24.04 ARM64

## Virtual Machine

- CPU: 2 cores
- RAM: 4GB
- Swap: approximately 4GB
- Disk: 30GB

## Container Environment

- Docker Engine
- cgroup v2
- Initial container memory: 256MB
- Maximum Java heap: 1GB
- Memory + swap limit: 1.5GB
- Puff ratio: 40%
- Monitoring interval: 2 seconds
- Restricted CPU: 1%

## original-hadoop2.7 VM (`u1604-test`)

- Ubuntu 16.04.7, 커널 4.4.0-186, VirtualBox 설정 2 vCPU / 3GB / 20GB, SSH `127.0.0.1:2214`
- ⚠️ 게스트는 **CPU 1개만 인식** (`Brought up 1 CPUs`), HWE 4.15 커널은 부팅 멈춤 — [06-single-node-yarn-pi.md](../original-hadoop2.7/arm-mac/steps/06-single-node-yarn-pi.md)
- ⚠️ 이 VirtualBox(ARM)에선 **라이브 스냅샷의 메모리 상태 복원 불가** (`virtio-scsi` 로드 실패) → 스냅샷은 VM을 끈 상태에서 찍기

## 논문 환경과의 차이

- 원 논문(YARN 2.7.3, 26노드 x86) 대비 차이표: [original-hadoop2.7/arm-mac/steps/02-env-diff.md](../original-hadoop2.7/arm-mac/steps/02-env-diff.md)
