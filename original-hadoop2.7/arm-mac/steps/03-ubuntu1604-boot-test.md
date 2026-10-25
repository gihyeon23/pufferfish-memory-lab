# Legacy 2 — Ubuntu 16.04 ARM64 부팅 시험 (Apple Silicon VirtualBox)

> 랩미팅: 2026-10-26 / 관련: [02-env-diff.md](02-env-diff.md) §2 OS 행
>
> 표기: **[사실]** 실측 / **[추측]** 내 해석

## 목적

**한 줄 요약: 논문 OS(Ubuntu 16.04)가 지금 맥(M4) + VirtualBox 7.2에서 부팅되는지 확인한다.**

- 교수님 목표 "최대한 원 논문과 맞추기" → 못 맞추면 "시도 → 실패 원인" 근거를 남기기 위해
- 기존 VM(pf-*)과 무관한 테스트 VM `u1604-test`로 진행

## 실행 방법

```bash
# ISO (체크섬 확인: f2ac4f94...0b78, 공식 SHA256SUMS와 일치)
curl -O https://cdimage.ubuntu.com/releases/16.04/release/ubuntu-16.04.7-server-arm64.iso

# 테스트 VM: ARM64, EFI, 2 vCPU / 2GB, VirtIO-SCSI 20GB, USB 키보드, 시리얼=TCP 23604
VBoxManage createvm --name u1604-test --platform-architecture arm --ostype Ubuntu_arm64 --register
VBoxManage modifyvm u1604-test --memory 2048 --cpus 2 --firmware efi --graphicscontroller qemuramfb \
  --nic1 nat --keyboard usb --mouse usbtablet --usbxhci on --uart1 0x3F8 4 --uart-mode1 tcpserver 23604
VBoxManage storagectl u1604-test --name VirtIO --add virtio --controller VirtIO-SCSI
# (디스크·ISO attach 생략)

# GRUB 명령줄(c)에서 시리얼 콘솔을 켜고 부팅 — 시리얼 TCP로 키 입력
linux /install/vmlinuz console=ttyAMA0,115200 earlycon ignore_loglevel ---
initrd /install/initrd.gz
boot
```

## 결과 — ✅ 부팅 성공 (설치 프로그램 첫 화면까지)

| 단계 | 결과 | 근거 |
|---|---|---|
| UEFI → GRUB 메뉴 | ✅ | [03-u1604-grub.png](03-u1604-grub.png) |
| 기본 메뉴로 커널 부팅 | ⚠️ 화면 멈춤처럼 보임 | [03-u1604-no-console.png](03-u1604-no-console.png) — `EFI stub: Exiting boot services` 뒤 출력 없음 |
| 시리얼 콘솔 지정 후 커널 부팅 | ✅ **4.4.0-186-generic** 부팅 | [03-u1604-serial-boot.log](03-u1604-serial-boot.log) |
| 디스크 인식 | ✅ VirtIO SCSI HBA, 20GB 디스크·CD-ROM | 같은 로그 |
| 설치 프로그램 | ✅ "Select a language" 화면 도달 | 같은 로그 |
| cgroup | ✅ v1 서브시스템(cpuset, cpu, memory, freezer …) 초기화 | 같은 로그 — 16.04는 기본이 v1 |

- 커널 4.4는 Apple Silicon VirtualBox에서 **부팅된다** [사실]
- "화면 멈춤"은 커널이 죽은 게 아니라 **화면 출력 장치를 못 찾은 것** [추측: 커널 4.4에 VirtualBox ARM 그래픽(ramfb) 드라이버가 없음] → 시리얼 콘솔로 우회됨

## 겪은 문제와 해결

1. PS/2 키보드로는 키 입력 전송 실패(`Failed to send a scancode`) → USB 키보드로 변경
2. USB 키보드 입력이 GRUB에 전달 안 됨 → 시리얼 포트를 TCP 서버로 열어 키 입력
3. 시험 도중 맥 잠자기로 VM 일시정지(`reason 'HostSuspend'`) → `caffeinate`로 잠자기 방지

## 남은 확인 (전체 설치 시)

- [ ] 네트워크: NIC가 Intel 82540EM(e1000)인데 부팅 로그에 NIC 인식 줄이 없음 → virtio-net으로 바꿔 재시험 필요 [추측]
- [ ] 설치 후 부팅: 설치된 시스템도 `console=ttyAMA0`를 GRUB 기본값으로 넣어야 접속 가능 [추측]
- [ ] 16.04 저장소: 표준 지원 종료 → 패키지 설치 가능 여부(old-releases / ESM) 확인
- 예상 소요: 설치 30분~1시간 + 위 확인

## 결론

- **OS 16.04는 "맞출 수 있음"으로 상향** (02-env-diff.md의 ⚠️ → 조건부 ✅)
- 단 화면 출력이 안 돼 **시리얼 콘솔 전용**으로 운영해야 함 (SSH 접속 후에는 문제 없음 [추측])
- 테스트 VM `u1604-test`는 꺼둔 상태로 보존 (삭제 안 함)
