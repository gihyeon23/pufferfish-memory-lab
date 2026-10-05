# Step 1 — VM 3대 기동 (control 1 + worker 2)

> 로드맵: [2026-10-05.md](2026-10-05.md) §3 Step 1 / 기준선: [00-step0-baseline.md](00-step0-baseline.md)

## 목표 구성

| VM 이름 | vCPU | RAM | 고정 IP | 맥→SSH 포트 | 역할 |
|---|---:|---:|---|---:|---|
| `pf-control` | 2 | 1536 MB | 10.10.0.11 | 2211 | NameNode + ResourceManager |
| `pf-worker1` | 3 | 3584 MB | 10.10.0.12 | 2212 | DataNode + NodeManager + controller |
| `pf-worker2` | 3 | 3584 MB | 10.10.0.13 | 2213 | 동일 |
| `pufferfish-lab` | 2 | 4096 MB | (NAT 유지) | 기존 | **보존, 평소엔 꺼둠** — 1~10차 재현용 |

- NAT Network 이름: `pfnet`, 대역 `10.10.0.0/24`, 게이트웨이 `10.10.0.1`

## ⚠️ 시작 전 주의

1. **지금 작업 중인 VS Code Remote-SSH 세션은 `pufferfish-lab` VM 안에서 돈다.**
   이 VM을 끄면 편집기 연결이 끊긴다. 아래 작업은 **맥 터미널**에서 한다.
2. 끄기 전에 **미커밋 변경사항을 커밋·푸시**할 것. 새 VM들은 GitHub에서 clone해야 한다.
   ```bash
   # VM 안에서
   cd ~/pufferfish-memory-lab && git status
   ```
3. 맥에서 Docker Desktop·브라우저 등을 내려 swap을 회복시킨 뒤 시작한다
   (Step 0에서 swap 7052MB/8192MB 사용 중이었음).

## 1. 기존 VM 종료 (맥)

```bash
VBoxManage controlvm pufferfish-lab acpipowerbutton
VBoxManage list runningvms        # 비어 있으면 완료
```

## 2. NAT Network 생성 (맥)

```bash
VBoxManage natnetwork add --netname pfnet --network "10.10.0.0/24" --enable --dhcp off
VBoxManage natnetwork modify --netname pfnet \
  --port-forward-4 "ssh-control:tcp:[127.0.0.1]:2211:[10.10.0.11]:22"
VBoxManage natnetwork modify --netname pfnet \
  --port-forward-4 "ssh-worker1:tcp:[127.0.0.1]:2212:[10.10.0.12]:22"
VBoxManage natnetwork modify --netname pfnet \
  --port-forward-4 "ssh-worker2:tcp:[127.0.0.1]:2213:[10.10.0.13]:22"
VBoxManage natnetwork list
```

> VirtualBox 7.2의 옵션 이름이 다르면 `VBoxManage natnetwork --help`로 확인한다.

## 3. 연결된 복제 3대 생성 (맥)

```bash
for n in control worker1 worker2; do
  VBoxManage clonevm pufferfish-lab \
    --snapshot 00-clean-ubuntu \
    --options link \
    --name "pf-$n" --register
done
VBoxManage list vms
```

- `--options link` = **연결된 복제**. 원본 스냅샷과 차이분만 저장
- ⚠️ **원본 `pufferfish-lab`과 `00-clean-ubuntu` 스냅샷을 지우면 복제본 3대가 전부 깨진다**

## 4. 각 VM 자원·네트워크 설정 (맥)

```bash
VBoxManage modifyvm pf-control --memory 1536 --cpus 2 \
  --nic1 natnetwork --nat-network1 pfnet
VBoxManage modifyvm pf-worker1 --memory 3584 --cpus 3 \
  --nic1 natnetwork --nat-network1 pfnet
VBoxManage modifyvm pf-worker2 --memory 3584 --cpus 3 \
  --nic1 natnetwork --nat-network1 pfnet
```

## 5. 부팅 (맥)

```bash
for n in control worker1 worker2; do VBoxManage startvm "pf-$n" --type headless; done
VBoxManage list runningvms
```

## 6. 각 노드 안에서 개별 설정

> 연결된 복제는 **hostname·machine-id·SSH 호스트키가 전부 동일**하다.
> 그대로 두면 DHCP 충돌, SSH 호스트키 경고, Hadoop 노드 식별 오류가 난다. 반드시 노드마다 바꾼다.

각 노드 콘솔(VirtualBox GUI)에서 `<NAME>`/`<IP>`를 해당 값으로 바꿔 실행:

```bash
# (1) hostname
sudo hostnamectl set-hostname <NAME>          # pf-control / pf-worker1 / pf-worker2

# (2) machine-id 재생성
sudo rm -f /etc/machine-id /var/lib/dbus/machine-id
sudo systemd-machine-id-setup
sudo ln -sf /etc/machine-id /var/lib/dbus/machine-id

# (3) SSH 호스트키 재생성
sudo rm -f /etc/ssh/ssh_host_*
sudo dpkg-reconfigure -f noninteractive openssh-server

# (4) 고정 IP (netplan) — 인터페이스명은 `ip -br link`로 확인
sudo tee /etc/netplan/99-pfnet.yaml >/dev/null <<YAML
network:
  version: 2
  ethernets:
    enp0s8:
      dhcp4: no
      addresses: [<IP>/24]
      routes:
        - to: default
          via: 10.10.0.1
      nameservers:
        addresses: [10.10.0.1, 8.8.8.8]
YAML
sudo chmod 600 /etc/netplan/99-pfnet.yaml
sudo netplan apply

# (5) 3대 상호 이름 등록
sudo tee -a /etc/hosts >/dev/null <<HOSTS
10.10.0.11 pf-control
10.10.0.12 pf-worker1
10.10.0.13 pf-worker2
HOSTS

# (6) 127.0.1.1의 옛 이름 제거 (Step 0 P1과 같은 문제 방지)
sudo sed -i '/^127\.0\.1\.1/d' /etc/hosts

sudo reboot
```

> (6)이 중요하다. 복제본에는 `127.0.1.1 pufferfish-lab`이 남아 있는데,
> Hadoop이 자기 hostname을 `127.0.1.1`로 해석하면 **다른 노드에 루프백 주소를 광고**해
> 워커 등록이 실패한다. 반드시 지우고 (5)의 실제 IP로 해석되게 한다.

## 7. SSH 키 배포 (pf-control에서)

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519   # 이미 있으면 생략
for h in pf-control pf-worker1 pf-worker2; do ssh-copy-id "$h"; done
for h in pf-control pf-worker1 pf-worker2; do ssh "$h" hostname; done
```

## 8. 맥에서의 접속 설정 (`~/.ssh/config`)

```
Host pf-control
  HostName 127.0.0.1
  Port 2211
  User gihyeon
Host pf-worker1
  HostName 127.0.0.1
  Port 2212
  User gihyeon
Host pf-worker2
  HostName 127.0.0.1
  Port 2213
  User gihyeon
```

## 완료 기준

- [ ] `VBoxManage list runningvms`에 3대
- [ ] 각 노드에서 `hostname`이 서로 다름
- [ ] `pf-control`에서 `ssh pf-worker1 hostname`, `ssh pf-worker2 hostname` 무암호 성공
- [ ] 각 노드에서 `getent hosts pf-worker1` → `10.10.0.12` (루프백 아님)
- [ ] 각 노드에서 외부 인터넷 접속 가능 (`curl -sI https://archive.ubuntu.com | head -1`)
- [ ] 맥에서 `ssh pf-control` 접속 성공
- [ ] 3대 기동 상태에서 맥 `sysctl vm.swapusage` 기록 (측정 오염 여부 판별용)
