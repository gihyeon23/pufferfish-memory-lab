"""cgroup 상태를 관찰만 하는 샘플러 (suspend/puff 일절 하지 않음).

container_monitor.py는 OCM을 감지하면 suspend(CPU 1%)와 puff를 수행하는데,
suspend는 워크로드의 할당 소요시간을 swap과 무관하게 느리게 만든다.
swap 지연만 분리해서 측정하려면 아무 개입도 하지 않는 관찰자가 필요하다.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "controller"))
from cgroup_utils import CgroupError, get_container_cgroup_path, read_value  # noqa: E402


def sample(container: str, interval: float) -> None:
    path = get_container_cgroup_path(container)
    print(f"[sampler] {container}: cgroup={path}", flush=True)
    while True:
        try:
            cur = read_value(path / "memory.current") or 0
            mmax = read_value(path / "memory.max")
            swp = read_value(path / "memory.swap.current") or 0
            smax = read_value(path / "memory.swap.max")
            ev = {}
            for line in (path / "memory.events").read_text().splitlines():
                k, v = line.split()
                ev[k] = int(v)
        except (CgroupError, OSError):
            print(f"[sampler] {container}: cgroup 읽기 불가 — 종료(컨테이너 사망 추정)", flush=True)
            return

        mb = lambda v: "max" if v is None else f"{v / 1048576:.1f}"
        print(
            f"[sampler] {container}: current={mb(cur)}MiB swap={mb(swp)}MiB "
            f"memory.max={mb(mmax)}MiB swap.max={mb(smax)}MiB "
            f"oom={ev.get('oom', 0)} oom_kill={ev.get('oom_kill', 0)} max_ev={ev.get('max', 0)}",
            flush=True,
        )
        time.sleep(interval)


if __name__ == "__main__":
    sample(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0.5)
