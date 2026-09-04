"""호스트 메모리 예산이 부족해지면 자동으로 reclaim_host()를 호출하는 감시 데몬.

cgroup 파일을 직접 읽거나 쓰지 않는다 — puff_manager가 이미 감싸둔
get_host_assigned_mb()/get_host_memory_total_mb()/reclaim_host()만 호출하는
평범한 폴링 루프다.

container_monitor.py가 컨테이너 하나의 급격한 순간 위기(OCM)를 500ms 주기로
감시하는 것과 달리, 이 데몬은 여러 컨테이너에 걸친 누적 추세(호스트 예산
소진)를 좀 더 느슨한 주기로 감시한다. 컨테이너 개수만큼 뜨는 게 아니라
호스트당 하나만 띄우면 된다.

RECLAIM_TRIGGER_RATIO를 puff()가 멈추는 기준(HOST_STOP_RATIO=0.8)보다 더
빡빡하게(기본 0.9) 잡은 이유: 두 기준이 같으면 puff가 막 거부되기 시작하는
바로 그 순간에 reclaim도 동시에 걸려서 서로 왔다갔다(thrashing)할 수 있다.
"""

import argparse
import time

import puff_manager

DEFAULT_INTERVAL_SECONDS = 5
RECLAIM_TRIGGER_RATIO = 0.9   # HOST_STOP_RATIO(0.8)보다 빡빡하게 잡아 puff와 안 부딪히게 함
RECLAIM_TARGET_FREE_MB = 300  # 회수해서 확보하고 싶은 최소 여유


def watch(interval: float) -> None:
    host_total = puff_manager.get_host_memory_total_mb()
    trigger_budget = host_total * RECLAIM_TRIGGER_RATIO
    print(
        f"[host_reclaim_daemon] 감시 시작 host_total={host_total}MiB "
        f"trigger_budget={trigger_budget:.0f}MiB interval={interval}s"
    )

    while True:
        time.sleep(interval)
        assigned = puff_manager.get_host_assigned_mb()

        if assigned >= trigger_budget:
            print(
                f"[host_reclaim_daemon] 예산 초과 위험 (assigned={assigned}MiB, "
                f"trigger={trigger_budget:.0f}MiB) -> reclaim_host 실행"
            )
            reclaimed = puff_manager.reclaim_host(RECLAIM_TARGET_FREE_MB)
            print(f"[host_reclaim_daemon] {reclaimed}MiB 회수 완료")
        else:
            print(f"[host_reclaim_daemon] assigned={assigned}MiB (여유 있음)")


def main() -> int:
    parser = argparse.ArgumentParser(description="호스트 메모리 예산 감시 후 자동 reclaim")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    args = parser.parse_args()
    watch(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
