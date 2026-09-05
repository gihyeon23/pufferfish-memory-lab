"""신규 컨테이너 admission 시점 reclaim 트리거 (Pufferfish 논문 §4.3.1, p.263-264 재현).

논문에서 reclaim()은 호스트 사용률이 특정 비율을 넘었다고 주기적으로 호출되는
게 아니라, "새 컨테이너를 노드에 배치하려는데 가용 메모리가 부족할 때"만
호출되는 lazy reclaim이다:

    "reclaim() is called whenever a new container is to be launched on
    the node. At that moment, the Node Memory Manager needs to check if
    the node has enough memory. If not, it chooses one of the FLEX
    containers..." (p.263)

    "Pufferfish uses a lazy approach that delays the memory reclaim
    until the node memory cannot satisfy a newly scheduled container."
    (p.264)

이 스크립트는 그 admission 경로를 재현한다:

    1. 신규 컨테이너가 요구하는 메모리(--request-mb)와 현재 호스트 가용
       메모리(host_total - get_host_assigned_mb())를 비교한다.
    2. 부족하면 puff_manager.reclaim_host()로 기존에 puff됐던 컨테이너들의
       한도를 줄여 여유를 확보한다. (논문은 최저 우선순위 OCM 컨테이너부터
       회수하지만, 이 프로젝트는 우선순위 개념이 없어 puff_manager의
       "가장 최근에 puff된 컨테이너부터" 정책을 그대로 따른다 — 03/04 실습과
       동일한 한계)
    3. 확보된 여유로 docker run을 실행한다.

controller/host_reclaim_daemon.py는 호스트 사용률 임계값을 상시 폴링하는,
이 프로젝트가 독자적으로 만든 OOM 예방용 확장 정책이라 트리거 조건이 다르다.
이 스크립트가 논문에 실제로 쓰인 reclaim 트리거를 재현한 쪽이다. 자세한 비교는
docs/pufferfish-architecture.md 참고.

이 실습에서는 admission 큐/지연(논문 4.3.2의 스케줄러 플러그인 delay 로직)은
구현하지 않는다 — 단일 호스트에 컨테이너 몇 개뿐이라 reclaim 시도 후에도
여유가 부족하면 경고만 남기고 그대로 실행한다.
"""

import argparse
import subprocess
import sys

import puff_manager


def free_mb() -> int:
    """budget(host_total × HOST_STOP_RATIO) 대비 남은 여유(MiB).

    raw host_total 기준이 아니다 — puff()가 스스로 멈추는 천장과 같은
    기준을 써야, host 할당량이 puff의 80% 한도에 도달했을 때 admission도
    "여유 없음"으로 정확히 판단한다(라이브 테스트에서 raw 기준으로
    계산했다가 80% 도달 시에도 "여유 충분"으로 잘못 판단하는 버그를
    발견해 고쳤다).
    """
    return puff_manager.get_host_free_mb()


def ensure_capacity(request_mb: int) -> int:
    """request_mb만큼의 여유를 확보 시도한다. 확보 시도 후 실제 여유(MiB)를 반환한다.

    이미 충분하면 reclaim_host()를 호출하지 않는다(불필요한 reclaim 방지 —
    논문의 lazy 원칙과 동일).
    """
    free = free_mb()
    if free >= request_mb:
        print(f"[admission] 여유 충분 (free={free}MiB >= request={request_mb}MiB), reclaim 불필요")
        return free

    print(
        f"[admission] 여유 부족 (free={free}MiB < request={request_mb}MiB) "
        "-> reclaim_host 호출 (논문 §4.3.1 reclaim 트리거 재현)"
    )
    reclaimed = puff_manager.reclaim_host(target_free_mb=request_mb)
    free = free_mb()
    print(f"[admission] reclaim {reclaimed}MiB 회수, reclaim 후 여유 {free}MiB")
    return free


def launch_container(name: str, image: str, request_mb: int, extra_args: list[str]) -> int:
    free = ensure_capacity(request_mb)
    if free < request_mb:
        print(
            f"[admission] 경고: reclaim 후에도 여유({free}MiB)가 요청량"
            f"({request_mb}MiB)보다 적음 — 그래도 실행함 "
            "(이 실습은 admission 지연/큐를 구현하지 않음)",
            file=sys.stderr,
        )

    swap_mb = request_mb + puff_manager.SWAP_HEADROOM_MB
    cmd = [
        "docker", "run", "-d", "--name", name,
        "--memory", f"{request_mb}m",
        "--memory-swap", f"{swap_mb}m",
        *extra_args,
        image,
    ]
    print(f"[admission] 실행: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[admission] docker run 실패: {result.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"[admission] 컨테이너 시작됨: {result.stdout.strip()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="신규 컨테이너 admission 시 논문 방식 reclaim 트리거를 재현하는 docker run 래퍼"
    )
    parser.add_argument("name", help="컨테이너 이름")
    parser.add_argument("image", help="도커 이미지")
    parser.add_argument("--request-mb", type=int, required=True, help="요청 메모리(MiB)")
    parser.add_argument(
        "--env", action="append", default=[], metavar="KEY=VALUE",
        help="docker run -e 로 전달할 값 (반복 가능)",
    )
    args = parser.parse_args()

    extra_args = []
    for e in args.env:
        extra_args += ["-e", e]

    try:
        return launch_container(args.name, args.image, args.request_mb, extra_args)
    except puff_manager.PuffError as e:
        print(f"[admission] 오류: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
