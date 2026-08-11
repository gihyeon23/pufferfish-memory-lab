"""cgroup v2 / swap 사전 확인 스크립트.

컨테이너를 모니터링하기 전에 실행 환경이 실험 전제를 만족하는지 확인한다.

- Docker가 cgroup v2를 사용하는지
- 호스트에 swap이 존재하는지
- (컨테이너가 실행 중이면) 해당 컨테이너 cgroup의 memory.swap.max가 설정돼 있는지
- (컨테이너가 실행 중이면) memory.stat에 pswpin/pswpout 키가 존재하는지

사용법:
    python3 cgroup_precheck.py [container]
"""

import subprocess
import sys
from pathlib import Path

from cgroup_utils import CgroupError, get_container_cgroup_path, read_flat_kv, read_value

PROC_MEMINFO = Path("/proc/meminfo")


def check_docker_cgroup_version() -> bool:
    result = subprocess.run(
        ["docker", "info", "--format", "{{.CgroupVersion}}"],
        capture_output=True,
        text=True,
    )
    version = result.stdout.strip()
    ok = result.returncode == 0 and version == "2"
    print(f"[{'OK' if ok else 'FAIL'}] Docker cgroup version = {version or result.stderr.strip()}")
    return ok


def check_host_swap() -> bool:
    swap_total_kb = 0
    for line in PROC_MEMINFO.read_text().splitlines():
        if line.startswith("SwapTotal:"):
            swap_total_kb = int(line.split()[1])
            break
    ok = swap_total_kb > 0
    print(f"[{'OK' if ok else 'FAIL'}] host SwapTotal = {swap_total_kb} kB")
    return ok


def check_container_swap_max(container: str) -> bool:
    cgroup_path = get_container_cgroup_path(container)
    swap_max = read_value(cgroup_path / "memory.swap.max")
    ok = swap_max is None or swap_max > 0
    display = "max" if swap_max is None else swap_max
    print(f"[{'OK' if ok else 'FAIL'}] {container}: memory.swap.max = {display}")
    return ok


def check_memory_stat_swap_keys(container: str) -> bool:
    cgroup_path = get_container_cgroup_path(container)
    stat = read_flat_kv(cgroup_path / "memory.stat")
    has_keys = "pswpin" in stat and "pswpout" in stat
    print(
        f"[{'OK' if has_keys else 'FAIL'}] {container}: memory.stat has pswpin/pswpout "
        f"(pswpin={stat.get('pswpin')}, pswpout={stat.get('pswpout')})"
    )
    return has_keys


def main() -> int:
    container = sys.argv[1] if len(sys.argv) > 1 else None

    checks = [check_docker_cgroup_version(), check_host_swap()]

    if container:
        try:
            checks.append(check_container_swap_max(container))
            checks.append(check_memory_stat_swap_keys(container))
        except CgroupError as e:
            print(f"[FAIL] {container}: {e}")
            checks.append(False)
    else:
        print("(컨테이너 이름이 주어지지 않아 컨테이너별 cgroup 확인은 건너뜁니다)")

    all_ok = all(checks)
    print("결과:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
