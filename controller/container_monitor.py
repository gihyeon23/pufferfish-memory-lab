"""컨테이너 cgroup 상태를 500ms 주기로 폴링하고 OCM(On-Container Memory
pressure)을 감지하면 suspend_manager로 CPU를 1%로 제한한다.

OCM 판정:
    (memory.current + memory.swap.current > memory.max)
    AND swapping activity

swapping activity는 다음 순서로 판단한다 (fallback):
    1) memory.stat에 pswpin/pswpout 키가 있으면 두 값의 delta 중 하나라도 > 0
    2) 없으면 memory.swap.current의 delta > 0 을 대신 사용한다
workingset_refault_anon은 존재하면 보조 관측값으로만 로그에 남기고,
판정에는 사용하지 않는다.

OCM 감지 시 CPU를 1%로 제한하는 것(suspend)과 별도로, 호스트에 메모리
여유가 있으면 puff_manager로 컨테이너의 memory.max도 늘려본다(puff).
"""

import argparse
import time
from pathlib import Path

import puff_manager
import suspend_manager
from cgroup_utils import (
    CgroupError,
    get_container_cgroup_path,
    read_events,
    read_flat_kv,
    read_value,
)

DEFAULT_INTERVAL_SECONDS = 0.5


def read_snapshot(cgroup_path: Path) -> dict:
    return {
        "mem_current": read_value(cgroup_path / "memory.current") or 0,
        "mem_max": read_value(cgroup_path / "memory.max"),
        "swap_current": read_value(cgroup_path / "memory.swap.current") or 0,
        "events": read_events(cgroup_path / "memory.events"),
        "mem_stat": read_flat_kv(cgroup_path / "memory.stat"),
        "cpu_stat": read_flat_kv(cgroup_path / "cpu.stat"),
    }


def evaluate_ocm(prev: dict, curr: dict) -> tuple[bool, str, dict]:
    """(ocm 여부, swap activity 판정에 사용한 방법, 보조 정보)를 반환한다."""
    mem_max = curr["mem_max"]
    over_limit = mem_max is not None and (
        curr["mem_current"] + curr["swap_current"] > mem_max
    )

    prev_stat = prev["mem_stat"]
    curr_stat = curr["mem_stat"]

    if "pswpin" in curr_stat and "pswpout" in curr_stat and "pswpin" in prev_stat and "pswpout" in prev_stat:
        delta_pswpin = curr_stat["pswpin"] - prev_stat["pswpin"]
        delta_pswpout = curr_stat["pswpout"] - prev_stat["pswpout"]
        swap_activity = delta_pswpin > 0 or delta_pswpout > 0
        method = "pswp_delta"
        detail = {"delta_pswpin": delta_pswpin, "delta_pswpout": delta_pswpout}
    else:
        delta_swap_current = curr["swap_current"] - prev["swap_current"]
        swap_activity = delta_swap_current > 0
        method = "swap_current_delta_fallback"
        detail = {"delta_swap_current": delta_swap_current}

    # 보조 관측값: 판정에는 사용하지 않고 로그에만 남긴다.
    if "workingset_refault_anon" in curr_stat:
        detail["workingset_refault_anon"] = curr_stat["workingset_refault_anon"]

    return (over_limit and swap_activity), method, detail


def format_bytes_mb(value):
    if value is None:
        return "max"
    return f"{value / (1024 * 1024):.1f}MiB"


def monitor(container: str, interval: float, once: bool) -> None:
    cgroup_path = get_container_cgroup_path(container)
    print(f"[container_monitor] {container}: cgroup path = {cgroup_path}")

    prev = read_snapshot(cgroup_path)

    while True:
        time.sleep(interval)
        try:
            curr = read_snapshot(cgroup_path)
        except (CgroupError, OSError):
            print(
                f"[container_monitor] {container}: cgroup을 더 이상 읽을 수 없습니다 "
                "(컨테이너 종료 또는 OOM-kill로 추정) — 모니터링을 종료합니다. "
                f"`docker inspect {container} --format "
                "'OOMKilled={{.State.OOMKilled}} ExitCode={{.State.ExitCode}}'`로 확인해보세요."
            )
            return

        ocm, method, detail = evaluate_ocm(prev, curr)

        print(
            f"[container_monitor] {container}: "
            f"current={format_bytes_mb(curr['mem_current'])} "
            f"swap={format_bytes_mb(curr['swap_current'])} "
            f"max={format_bytes_mb(curr['mem_max'])} "
            f"cpu.usage_usec={curr['cpu_stat'].get('usage_usec')} "
            f"method={method} detail={detail} "
            f"events={curr['events']}"
        )

        if ocm:
            print(f"[container_monitor] {container}: OCM 감지 (method={method}, detail={detail})")
            new_limit = puff_manager.puff(container)
            if new_limit is not None:
                print(f"[container_monitor] {container}: puff 완료, 새 메모리 한도 {new_limit}MiB")
            if not suspend_manager.is_suspended(container):
                suspend_manager.suspend(container)
            else:
                print(f"[container_monitor] {container}: 이미 suspend 상태, 재적용 생략")

        prev = curr

        if once:
            return


def main() -> int:
    parser = argparse.ArgumentParser(description="cgroup v2 기반 OCM 모니터 (500ms 폴링)")
    parser.add_argument("container")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--once", action="store_true", help="한 번만 폴링하고 종료 (테스트용)")
    args = parser.parse_args()

    try:
        monitor(args.container, args.interval, args.once)
    except KeyboardInterrupt:
        print(f"\n[container_monitor] {args.container}: 종료합니다")
    except CgroupError as e:
        print(f"[container_monitor] 오류: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
