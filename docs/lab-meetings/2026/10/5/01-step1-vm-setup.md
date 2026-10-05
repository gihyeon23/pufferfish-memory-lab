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

## 3. 복제 전 사전 확인 (맥 + VM)

```bash
# (맥) 스냅샷이 실제로 있는지 — 없으면 clonevm이 그냥 실패한다
VBoxManage snapshot pufferfish-lab list
```

```bash
# (pufferfish-lab VM 안에서, 끄기 전에) 스냅샷 시점에 SSH 서버가 있는지 확인
dpkg -l openssh-server | tail -1
```

- `00-clean-ubuntu`가 없으면 → 현재 상태로 스냅샷을 먼저 뜨거나, 전체 복제로 전환
- `openssh-server`가 없으면 → §7 SSH 키 배포가 통째로 막힌다. 복제 후 각 노드 콘솔에서
  `sudo apt install -y openssh-server` 선행 필요

## 4. 연결된 복제 3대 생성 (맥)

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

## 5. 각 VM 자원·네트워크 설정 (맥)

```bash
VBoxManage modifyvm pf-control --memory 1536 --cpus 2 \
  --nic1 natnetwork --nat-network1 pfnet
VBoxManage modifyvm pf-worker1 --memory 3584 --cpus 3 \
  --nic1 natnetwork --nat-network1 pfnet
VBoxManage modifyvm pf-worker2 --memory 3584 --cpus 3 \
  --nic1 natnetwork --nat-network1 pfnet
```

## 6. 부팅 — **한 대씩** (맥)

> ⚠️ `--type headless`를 쓰면 안 된다. 아직 고정 IP가 없고 NAT Network의 DHCP도 꺼둔
> 상태라 **SSH로 들어갈 방법이 없고**, headless면 콘솔 창도 안 떠서 설정 자체가 불가능하다.
> 반드시 GUI 콘솔로 띄우고, 한 대씩 §7 설정을 끝낸 뒤 다음 대로 넘어간다.

```bash
VBoxManage startvm pf-control --type gui
```

→ 콘솔에서 §7 설정 → 재부팅 → 맥에서 `ssh -p 2211 gihyeon@127.0.0.1` 확인
→ 성공하면 `pf-worker1`, 그 다음 `pf-worker2` 순으로 같은 절차를 반복한다.

**한 대씩 하는 이유**: 복제본 3대는 hostname·IP가 전부 동일한 상태로 출발한다.
동시에 띄우면 어느 창이 어느 노드인지 구분이 안 되고, 고정 IP를 넣기 전까지는
주소도 겹친다.

## 7. 각 노드 안에서 개별 설정

> 연결된 복제는 **hostname·machine-id·SSH 호스트키가 전부 동일**하다.
> 그대로 두면 DHCP 충돌, SSH 호스트키 경고, Hadoop 노드 식별 오류가 난다. 반드시 노드마다 바꾼다.

각 노드 콘솔(VirtualBox GUI)에서 `<NAME>`/`<IP>`를 해당 값으로 바꿔 실행:

```bash
# (0) 인터페이스 이름부터 확인 — enp0s8이라고 단정하지 말 것
ip -br link
cat /etc/netplan/50-cloud-init.yaml   # 기존 설정에 match/macaddress가 있는지 확인
```

> 현 `pufferfish-lab`은 `enp0s8`이고, 같은 `nic1` 슬롯을 쓰면 이름이 유지될 가능성이 높다
> (인터페이스 이름은 MAC이 아니라 PCI 슬롯 기반). 다만 복제 시 MAC은 새로 생성되므로,
> 기존 netplan이 `match: macaddress:`로 인터페이스를 지정하고 있으면 그 설정은 맞지 않게 된다.
> 이 환경은 `cloud-init status = disabled`라 cloud-init이 netplan을 재생성하지는 않는다.

```bash
# (1) hostname
sudo hostnamectl set-hostname <NAME>          # pf-control / pf-worker1 / pf-worker2

# (2) machine-id — 비워두고 재부팅 시 생성되게 한다
sudo rm -f /var/lib/dbus/machine-id
sudo truncate -s 0 /etc/machine-id
sudo ln -sf /etc/machine-id /var/lib/dbus/machine-id

# (3) SSH 호스트키 재생성
sudo rm -f /etc/ssh/ssh_host_*
sudo dpkg-reconfigure -f noninteractive openssh-server

# (4) 고정 IP (netplan) — <IFACE>는 (0)에서 확인한 이름
sudo tee /etc/netplan/99-pfnet.yaml >/dev/null <<YAML
network:
  version: 2
  ethernets:
    <IFACE>:
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

### (2)를 `systemd-machine-id-setup` 대신 빈 파일 방식으로 쓰는 이유

- `machine-id(5)`가 **복제용 이미지의 공식 권장 방식**으로 "`/etc/machine-id`를 없애거나
  빈 파일로 둔다"를 명시한다. 빈 파일이면 다음 부팅 때 systemd가 새로 만든다
- 실행 중인 시스템에서 지웠다 `systemd-machine-id-setup`으로 다시 만드는 방식은
  생성 소스가 환경에 따라 달라진다(① D-Bus machine ID ② KVM UUID ③ 컨테이너 UUID
  ④ 랜덤). 이 VM은 `/var/lib/dbus/machine-id`가 `/etc/machine-id` 심볼릭 링크라
  결과적으로 ④로 떨어지지만, 결과가 환경에 의존한다는 점 자체가 바람직하지 않다
- 재부팅 후 3대의 값이 **서로 다른지** 반드시 확인한다: `cat /etc/machine-id`

## 8. SSH 키 배포 (pf-control에서)

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519   # 이미 있으면 생략
for h in pf-control pf-worker1 pf-worker2; do ssh-copy-id "$h"; done
for h in pf-control pf-worker1 pf-worker2; do ssh "$h" hostname; done
```

## 9. 맥에서의 접속 설정 (`~/.ssh/config`)

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

### 기본

- [ ] `VBoxManage list runningvms`에 3대
- [ ] 각 노드에서 `hostname`이 서로 다름
- [ ] 각 노드에서 `cat /etc/machine-id`가 서로 다름
- [ ] `pf-control`에서 `ssh pf-worker1 hostname`, `ssh pf-worker2 hostname` 무암호 성공
- [ ] 각 노드에서 `getent hosts pf-worker1` → `10.10.0.12` (루프백 아님)
- [ ] 각 노드에서 외부 인터넷 접속 가능 (`curl -sI https://archive.ubuntu.com | head -1`)
- [ ] 맥에서 `ssh pf-control` 접속 성공

### 실험 조건 통제 (이게 빠지면 Step 6~9 비교가 무의미해진다)

```bash
# 각 노드에서
stat -fc %T /sys/fs/cgroup     # cgroup2fs 여야 함
swapon --show                  # 크기·타입·우선순위
cat /proc/sys/vm/swappiness
free -m
```

- [ ] 3대 모두 `cgroup2fs` (Hadoop 3.5 cgroup v2 활성화의 전제)
- [ ] **worker1 / worker2의 swap 크기·타입·`swappiness`가 완전히 동일**
  - 이 프로젝트는 swap이 결과에 직접 영향을 주므로 RAM만 맞추면 부족하다
  - 복제본이라 `/swap.img` 3.8GiB가 그대로 따라갈 가능성이 높지만, **확인하지 않으면
    두 worker 비교 자체가 성립하지 않는다**
- [ ] worker1 / worker2의 `free -m` total이 동일 (3584MB 설정 반영)

### 호스트 영향 기록

```bash
# 맥에서, 3대 기동 상태로
sysctl vm.swapusage
memory_pressure | tail -3
```

- [ ] 3대 기동 상태의 맥 swap 사용량·메모리 압력 기록
  - ⚠️ macOS swap은 앱을 종료해도 **즉시 줄지 않는다**(지연 회수 + 메모리 압축).
    따라서 절대값이 아니라 **기동 전/후 증가량과 `memory_pressure` 추세**를 본다
- [ ] control 1536MB는 **기동용 예산**으로 두고, Hadoop 기동 후 부족하면 Step 2에서 조정
