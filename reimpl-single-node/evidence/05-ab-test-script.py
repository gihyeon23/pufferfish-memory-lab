"""OCM 판정 로직 A/B 검증 스크립트 (일회성 실험용).

같은 컨테이너를 500ms마다 폴링하면서, **동일한 스냅샷 데이터**에 대해
두 가지 판정 로직을 동시에 적용해 결과를 나란히 기록한다:

  OLD (수정 전, 3차에서 버그였던 로직): over_limit AND swap_activity
  NEW (현재 코드):                      over_limit AND (swap_activity OR swap_saturated)

같은 시점, 같은 입력값에 대해 두 로직을 비교하므로 "실행 조건이 달라서
결과가 달랐다"는 반박이 원천적으로 불가능하다. 두 판정이 갈리는 구간이
곧 "옛 로직이 놓쳤던 구간"이다.

puff/suspend 등 개입은 일절 하지 않는 순수 관찰 스크립트다.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/gihyeon/pufferfish-memory-lab/controller")

from cgroup_utils import CgroupError, get_container_cgroup_path  # noqa: E402
from container_monitor import SWAP_SATURATION_RATIO, read_snapshot  # noqa: E402


def evaluate_both(prev: dict, curr: dict) -> dict:
    mem_max = curr["mem_max"]
    over_limit = mem_max is not None and (
        curr["mem_current"] + curr["swap_current"] > mem_max
    )

    prev_stat, curr_stat = prev["mem_stat"], curr["mem_stat"]
    if all(k in s for k in ("pswpin", "pswpout") for s in (prev_stat, curr_stat)):
        d_in = curr_stat["pswpin"] - prev_stat["pswpin"]
        d_out = curr_stat["pswpout"] - prev_stat["pswpout"]
        swap_activity = d_in > 0 or d_out > 0
        method = "pswp_delta"
        delta_repr = f"pswpin+{d_in}/pswpout+{d_out}"
    else:
        d_swap = curr["swap_current"] - prev["swap_current"]
        swap_activity = d_swap > 0
        method = "swap_current_delta_fallback"
        delta_repr = f"delta_swap={d_swap}"

    swap_max = curr["swap_max"]
    swap_saturated = (
        swap_max is not None and curr["swap_current"] >= swap_max * SWAP_SATURATION_RATIO
    )

    return {
        "over_limit": over_limit,
        "swap_activity": swap_activity,
        "swap_saturated": swap_saturated,
        "method": method,
        "delta_repr": delta_repr,
        "OLD": over_limit and swap_activity,
        "NEW": over_limit and (swap_activity or swap_saturated),
    }


def mb(v):
    return "max" if v is None else f"{v / (1024 * 1024):.1f}"


def main(container: str, interval: float = 0.5) -> int:
    path = get_container_cgroup_path(container)
    prev = read_snapshot(path)
    n = 0
    old_fired = new_fired = disagree = 0
    t0 = time.time()

    while True:
        time.sleep(interval)
        try:
            curr = read_snapshot(path)
        except (CgroupError, OSError):
            print(f"\n=== 컨테이너 소멸 (총 {n}폴링, {time.time() - t0:.1f}초) ===")
            print(f"OLD 로직 OCM 발화 횟수: {old_fired}")
            print(f"NEW 로직 OCM 발화 횟수: {new_fired}")
            print(f"두 판정이 갈린 폴링 수: {disagree}")
            return 0

        n += 1
        r = evaluate_both(prev, curr)
        old_fired += r["OLD"]
        new_fired += r["NEW"]
        mark = ""
        if r["OLD"] != r["NEW"]:
            disagree += 1
            mark = "   <<<< 판정 불일치! OLD=미감지, NEW=감지"

        ev = curr["events"]
        print(
            f"[{time.time() - t0:7.1f}s] "
            f"cur={mb(curr['mem_current']):>7}MiB swap={mb(curr['swap_current']):>6}MiB "
            f"max={mb(curr['mem_max']):>7}MiB swapmax={mb(curr['swap_max']):>6}MiB | "
            f"over={int(r['over_limit'])} act={int(r['swap_activity'])} "
            f"sat={int(r['swap_saturated'])} ({r['delta_repr']}) | "
            f"OLD={'OCM' if r['OLD'] else ' - '} NEW={'OCM' if r['NEW'] else ' - '} | "
            f"oom={ev.get('oom')} oom_kill={ev.get('oom_kill')}{mark}",
            flush=True,
        )
        prev = curr


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
