"""Pufferfish 스타일 puff/reclaim.

CPU가 suspend된(=OCM 상태의) 컨테이너에게 호스트에 여유 메모리가 있다면
cgroup 메모리 한도(memory.max)를 늘려준다(puff). 호스트 메모리가 빠듯해지면
이전에 puff했던 컨테이너의 한도를 다시 줄인다(reclaim), 단 puff하기 전
원래 한도 아래로는 내리지 않는다.

`docker update --memory/--memory-swap`으로 cgroup의 memory.max를 조정한다.
suspend_manager와 마찬가지로 puff 전 원래 한도를 컨테이너별로 저장해두고,
reclaim은 그 원래 한도를 하한선(floor)으로 삼는다.

알고리즘은 Pufferfish 논문(SoCC'19) 저자의 Hadoop YARN 구현
(NodeMemoryManager.MemoryBalloon/MemoryReclaim, ContainerImpl.reclaimMemory,
https://github.com/yncxcw/pufferfish)의 로직을 이 프로젝트의 단일 Docker
호스트/cgroup v2 환경에 맞게 옮긴 것이다. 기본 비율(PUFF_RATIO=0.4,
HOST_STOP_RATIO=0.8)도 해당 구현의 기본값(balloon.ratio, balloon.stop)을
따른다. MIN_PUFF_STEP_MB는 원 구현의 임계값(1000MB, 대규모 YARN 클러스터
기준)을 이 실습의 규모(32MiB 청크, 256MiB 컨테이너)에 맞게 낮춘 값이다.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from cgroup_utils import CgroupError, get_container_cgroup_path, read_value

STATE_DIR = Path(__file__).parent / "state"
MEMORY_STATE_SUFFIX = "_memory.json"

PUFF_RATIO = 0.4        # 한 번에 늘리는 비율 (현재 한도 대비)
HOST_STOP_RATIO = 0.8   # 호스트 메모리의 이 비율까지만 puff 허용
MIN_PUFF_STEP_MB = 16   # 늘어나는 양이 이보다 작으면 puff를 포기한다
SWAP_HEADROOM_MB = 128  # docker update --memory-swap = --memory + 이 여유분


class PuffError(RuntimeError):
    pass


def _state_path(container: str) -> Path:
    return STATE_DIR / f"{container}{MEMORY_STATE_SUFFIX}"


def is_puffed(container: str) -> bool:
    return _state_path(container).exists()


def get_host_memory_total_mb() -> int:
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) // 1024
    raise PuffError("/proc/meminfo에서 MemTotal을 찾을 수 없습니다")


def get_current_memory_limit_mb(container: str) -> int | None:
    """cgroup memory.max를 MiB로 반환한다. 무제한(max)이면 None."""
    cgroup_path = get_container_cgroup_path(container)
    value = read_value(cgroup_path / "memory.max")
    if value is None:
        return None
    return value // (1024 * 1024)


def _running_container_names() -> list[str]:
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PuffError(f"docker ps 실패: {result.stderr.strip()}")
    return [name for name in result.stdout.splitlines() if name]


def get_host_assigned_mb() -> int:
    """실행 중인 모든 컨테이너의 memory.max 합(MiB).

    한도가 없는(=max) 컨테이너는 상한을 알 수 없으므로 합산에서 제외한다.
    """
    total = 0
    for name in _running_container_names():
        try:
            limit = get_current_memory_limit_mb(name)
        except (CgroupError, OSError):
            continue
        if limit is not None:
            total += limit
    return total


def _apply_docker_memory_update(container: str, memory_mb: int) -> None:
    swap_mb = memory_mb + SWAP_HEADROOM_MB
    cmd = [
        "docker", "update",
        "--memory", f"{memory_mb}m",
        "--memory-swap", f"{swap_mb}m",
        container,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise PuffError(f"docker update 실패 ({' '.join(cmd)}): {result.stderr.strip()}")


def puff(container: str) -> int | None:
    """호스트에 여유가 있으면 컨테이너 메모리 한도를 늘린다.

    늘린 뒤의 새 한도(MiB)를 반환한다. 늘리지 못했으면(이미 무제한이거나,
    호스트 여유가 없거나, 증분이 너무 작으면) None을 반환한다.
    """
    current_mb = get_current_memory_limit_mb(container)
    if current_mb is None:
        print(f"[puff_manager] {container}: 이미 무제한(max) 상태, puff 불필요")
        return None

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path = _state_path(container)
    if not state_path.exists():
        state_path.write_text(json.dumps({"original_memory_max_mb": current_mb}))
        print(f"[puff_manager] {container}: 원래 메모리 한도 저장 {current_mb}MiB")

    host_total = get_host_memory_total_mb()
    host_assigned = get_host_assigned_mb()
    host_budget = host_total * HOST_STOP_RATIO
    available = host_budget - host_assigned
    if available < MIN_PUFF_STEP_MB:
        print(
            f"[puff_manager] {container}: 호스트 여유 없음 "
            f"(assigned={host_assigned}MiB budget={host_budget:.0f}MiB), puff 건너뜀"
        )
        return None

    step = min(current_mb * PUFF_RATIO, available)
    if step < MIN_PUFF_STEP_MB:
        print(f"[puff_manager] {container}: 증분이 너무 작음({step:.0f}MiB), puff 포기")
        return None

    new_mb = current_mb + int(step)
    _apply_docker_memory_update(container, new_mb)
    print(f"[puff_manager] {container}: puff 적용 {current_mb}MiB -> {new_mb}MiB")
    return new_mb


def reclaim(container: str, amount_mb: int | None = None) -> int:
    """puff했던 컨테이너의 메모리 한도를 줄인다.

    puff 전 원래 한도(floor) 아래로는 내리지 않는다. amount_mb가 None이면
    원래 한도까지 전부 회수한다. 실제로 회수한 MiB를 반환한다(회수할 게
    없으면 0).
    """
    state_path = _state_path(container)
    if not state_path.exists():
        print(f"[puff_manager] {container}: puff한 적 없음, reclaim 건너뜀")
        return 0

    floor_mb = json.loads(state_path.read_text())["original_memory_max_mb"]
    current_mb = get_current_memory_limit_mb(container)
    if current_mb is None or current_mb <= floor_mb:
        return 0

    new_mb = floor_mb if amount_mb is None else max(floor_mb, current_mb - amount_mb)
    if new_mb >= current_mb:
        return 0

    _apply_docker_memory_update(container, new_mb)
    reclaimed = current_mb - new_mb
    print(
        f"[puff_manager] {container}: reclaim 적용 {current_mb}MiB -> {new_mb}MiB "
        f"(회수 {reclaimed}MiB)"
    )

    if new_mb <= floor_mb:
        state_path.unlink()
        print(f"[puff_manager] {container}: 원래 한도로 완전히 복구되어 puff 상태 해제")

    return reclaimed


def reclaim_host(target_free_mb: int) -> int:
    """호스트 여유 메모리가 target_free_mb 이상이 될 때까지, puff했던
    컨테이너들 중 가장 최근에 puff한 것부터 순서대로 reclaim한다.

    여러 컨테이너에 걸쳐 reclaim할 때(다중 컨테이너 환경) 쓰는 host 레벨
    진입점이다. 실제로 회수한 총 MiB를 반환한다.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    host_total = get_host_memory_total_mb()
    candidates = sorted(
        STATE_DIR.glob(f"*{MEMORY_STATE_SUFFIX}"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    reclaimed_total = 0
    for state_path in candidates:
        free = host_total - get_host_assigned_mb()
        if free >= target_free_mb:
            break
        container = state_path.name[: -len(MEMORY_STATE_SUFFIX)]
        reclaimed_total += reclaim(container, target_free_mb - free)

    return reclaimed_total


def main() -> int:
    parser = argparse.ArgumentParser(description="Pufferfish 스타일 puff/reclaim")
    subparsers = parser.add_subparsers(dest="action", required=True)

    puff_parser = subparsers.add_parser("puff", help="컨테이너 메모리 한도를 늘린다")
    puff_parser.add_argument("container")

    reclaim_parser = subparsers.add_parser("reclaim", help="컨테이너 메모리 한도를 줄인다")
    reclaim_parser.add_argument("container")
    reclaim_parser.add_argument(
        "--amount-mb", type=int, default=None, help="회수할 양(MiB). 생략하면 원래 한도까지 전부 회수"
    )

    reclaim_host_parser = subparsers.add_parser(
        "reclaim-host", help="여러 컨테이너에서 host 여유 메모리를 확보한다"
    )
    reclaim_host_parser.add_argument("--target-free-mb", type=int, required=True)

    args = parser.parse_args()

    try:
        if args.action == "puff":
            puff(args.container)
        elif args.action == "reclaim":
            reclaim(args.container, args.amount_mb)
        else:
            reclaim_host(args.target_free_mb)
    except PuffError as e:
        print(f"[puff_manager] 오류: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
