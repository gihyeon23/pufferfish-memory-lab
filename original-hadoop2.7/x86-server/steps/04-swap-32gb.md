# 04. swap 32GB swapfile (2026-11-01)

## 1. 목적

- [01](01-cluster-spec-and-scaling.md) §3 초기안: 워커 swap = **32GB swapfile** (RAM과 같은 크기 [우리])
- OCM 판정(`memory + swap > limit`)과 puff는 컨테이너가 swap을 쓸 수 있어야 동작함. 설치 기본 swap 980M로는 부족

## 2. 변경 전

| 항목 | 값 |
|---|---|
| swap | `/dev/mapper/ubuntu--vg-swap_1` (LVM, `dm-1`) 980M, 사용 0B |
| `/etc/fstab` | 위 LVM swap 1줄 |

## 3. 실행 방법 (VM)

```bash
sudo fallocate -l 32G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 기존 LVM swap 끄기 → swap 합계를 계획과 같은 32GB로
sudo swapoff /dev/mapper/ubuntu--vg-swap_1
sudo sed -i '/swap_1/s/^/#/' /etc/fstab
```

- 기존 LVM swap은 지우지 않고 끄기만 함 (fstab 주석을 풀면 다시 쓸 수 있음)

## 4. 확인 포인트 · 결과

| 확인 | 결과 |
|---|---|
| `swapon --show` | `/swapfile file 32G 0B` 한 줄 — LVM swap 꺼짐 |
| `free -h` | Swap 31G (`free -h`가 32GiB를 31G로 표시. `mkswap` 기준 32 GiB) |
| `vm.swappiness` | 60 (16.04 기본값) — 논문에 값 없음 → 그대로 둠 |
| 재부팅 후 유지 | **미확인** — 다음 재부팅 때 `swapon --show`로 확인 |

## 5. 논문과 다른 점

- 원 실험 호스트의 swap 크기는 논문에 없음. 32GB는 우리가 정한 값
- swap 장치: 원 논문 물리 HDD RAID-5 ↔ VM 디스크 위 파일 → swap 속도가 달라 reclaim·thrashing 수치에 영향 가능 (01 §7)
