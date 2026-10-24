"""Swap preflight: 본 OCM 실험 전에 실행하는 dry-run 점검.

동일 workload 컨테이너를 대상으로 memory.swap.current가 실제로 0에서
증가하는지 확인한다. 증가하지 않으면 OCM 실험(container_monitor.py)을
시작하지 말고, host swap / VM swap 설정을 먼저 진단해야 한다.

memory.swap.current가 관찰 구간 내내 baseline(최초 값)보다 커지지 않으면
실패로 판정하고 진단 정보를 출력한다.

사용법:
    python3 swap_preflight.py <container> [--timeout 120] [--interval 1]
"""

import argparse
import sys
import time

from cgroup_precheck import check_container_swap_max, check_host_swap
from cgroup_utils import CgroupError, get_container_cgroup_path, read_value

DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_INTERVAL_SECONDS = 1.0


def run_preflight(container: str, timeout: float, interval: float) -> bool:
    cgroup_path = get_container_cgroup_path(container)
    swap_file = cgroup_path / "memory.swap.current"

    baseline = read_value(swap_file) or 0
    print(f"[swap_preflight] {container}: baseline memory.swap.current = {baseline} bytes")

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = read_value(swap_file) or 0
        print(f"[swap_preflight] {container}: memory.swap.current = {current} bytes")
        if current > baseline:
            print(
                f"[swap_preflight] {container}: swap 증가 확인 "
                f"({baseline} -> {current} bytes). OCM 실험을 시작해도 됩니다."
            )
            return True
        time.sleep(interval)

    print(
        f"[swap_preflight] {container}: {timeout}초 동안 memory.swap.current가 "
        f"{baseline} bytes에서 증가하지 않았습니다. OCM 실험을 시작하지 않습니다."
    )
    print("[swap_preflight] 진단:")
    check_host_swap()
    try:
        check_container_swap_max(container)
    except CgroupError as e:
        print(f"[FAIL] {container}: {e}")
    print(
        "[swap_preflight] 점검 포인트: host/VM에 swap이 있는지, "
        "docker run에 --memory-swap이 --memory보다 크게 설정됐는지, "
        "workload가 memory.max를 실제로 초과할 만큼 할당하는지 확인하세요."
    )
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="OCM 실험 전 swap 발생 여부 dry-run 점검")
    parser.add_argument("container")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    args = parser.parse_args()

    try:
        ok = run_preflight(args.container, args.timeout, args.interval)
    except CgroupError as e:
        print(f"[swap_preflight] 오류: {e}", file=sys.stderr)
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
