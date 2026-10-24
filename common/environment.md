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

## 논문 환경과의 차이

- 원 논문(YARN 2.7.3, 26노드 x86) 대비 차이표: [lab-meetings/2026-10-26/02-env-diff.md](../original-hadoop2.7/lab-meetings/2026-10-26/02-env-diff.md)
