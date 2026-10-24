"""Pufferfish 스타일 suspend/resume.

`docker pause`는 사용하지 않는다. Pufferfish는 컨테이너가 완전히 멈추지 않고
heartbeat를 유지할 수 있도록 CPU를 소량(1%) 남겨두는 방식으로 스로틀링하므로,
`docker update --cpus --cpuset-cpus`로 CPU 쿼터와 실행 가능 코어를 제한한다.

suspend() 호출 전의 CPU 설정을 컨테이너별로 저장해두고, resume()은 임의의
값이 아니라 저장된 원래 설정으로 복구한다.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from cgroup_utils import CgroupError, get_container_cgroup_path, read_text

STATE_DIR = Path(__file__).parent / "state"

SUSPEND_CPUS = "0.01"
SUSPEND_CPUSET_CPUS = "0"


class SuspendError(RuntimeError):
    pass


def _state_path(container: str) -> Path:
    return STATE_DIR / f"{container}.json"


def get_current_cpu_config(container: str) -> dict:
    """suspend 직전의 실제 cgroup 상태를 읽어 복구 가능한 형태로 반환한다.

    docker inspect의 HostConfig.NanoCpus/CpusetCpus는 `docker update --cpus 0
    --cpuset-cpus ""`로 되돌리려 해도 실제 cgroup(cpu.max, cpuset.cpus)에
    반영되지 않는 경우가 있어(테스트로 확인) 신뢰할 수 없다. 대신 cgroup
    파일을 직접 읽어 저장하고, resume 시 --cpu-quota/--cpu-period/--cpuset-cpus
    저수준 플래그로 동일한 상태를 복원한다.
    """
    cgroup_path = get_container_cgroup_path(container)
    cpu_max = read_text(cgroup_path / "cpu.max")  # "<quota|max> <period>"
    cpuset_cpus = read_text(cgroup_path / "cpuset.cpus")
    if not cpuset_cpus:
        # 미설정 상태(전체 코어 허용)에서는 cpuset.cpus가 비어 있으므로
        # 실제 허용 범위인 cpuset.cpus.effective로 대체한다.
        cpuset_cpus = read_text(cgroup_path / "cpuset.cpus.effective")
    return {"cpu_max": cpu_max, "cpuset_cpus": cpuset_cpus}


def _apply_docker_update(container: str, args: list) -> None:
    cmd = ["docker", "update", *args, container]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SuspendError(f"docker update 실패 ({' '.join(cmd)}): {result.stderr.strip()}")


def _suspend_update_args() -> list:
    return ["--cpus", SUSPEND_CPUS, "--cpuset-cpus", SUSPEND_CPUSET_CPUS]


def _resume_update_args(saved: dict) -> list:
    quota, period = saved["cpu_max"].split()
    if quota == "max":
        cpu_args = ["--cpu-quota", "-1"]
    else:
        cpu_args = ["--cpu-quota", quota, "--cpu-period", period]
    return [*cpu_args, "--cpuset-cpus", saved["cpuset_cpus"]]


def _log_effective_cgroup_cpu(container: str) -> None:
    try:
        cgroup_path = get_container_cgroup_path(container)
        cpu_max = read_text(cgroup_path / "cpu.max")
        cpuset_cpus = read_text(cgroup_path / "cpuset.cpus")
        print(f"[suspend_manager] {container}: cgroup cpu.max='{cpu_max}' cpuset.cpus='{cpuset_cpus}'")
    except (CgroupError, OSError) as e:
        print(f"[suspend_manager] {container}: cgroup 상태 확인 실패: {e}")


def suspend(container: str) -> None:
    """CPU를 1%(cpuset 0번 코어만)로 제한한다. 원래 설정은 최초 1회만 저장한다."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path = _state_path(container)

    if not state_path.exists():
        original = get_current_cpu_config(container)
        state_path.write_text(json.dumps(original))
        print(f"[suspend_manager] {container}: 원래 CPU 설정 저장 {original}")
    else:
        print(f"[suspend_manager] {container}: 이미 suspend 상태 (저장된 설정 유지)")

    _apply_docker_update(container, _suspend_update_args())
    print(f"[suspend_manager] {container}: suspend 적용 (--cpus {SUSPEND_CPUS} --cpuset-cpus {SUSPEND_CPUSET_CPUS})")
    _log_effective_cgroup_cpu(container)


def resume(container: str) -> None:
    """suspend() 이전에 저장해둔 CPU 설정으로 복구한다."""
    state_path = _state_path(container)
    if not state_path.exists():
        print(f"[suspend_manager] {container}: 저장된 원래 설정이 없어 resume을 건너뜁니다")
        return

    original = json.loads(state_path.read_text())
    _apply_docker_update(container, _resume_update_args(original))
    print(f"[suspend_manager] {container}: resume 적용 {original}")
    _log_effective_cgroup_cpu(container)
    state_path.unlink()


def is_suspended(container: str) -> bool:
    return _state_path(container).exists()


def main() -> int:
    parser = argparse.ArgumentParser(description="Pufferfish 스타일 CPU suspend/resume")
    parser.add_argument("action", choices=["suspend", "resume"])
    parser.add_argument("container")
    args = parser.parse_args()

    try:
        if args.action == "suspend":
            suspend(args.container)
        else:
            resume(args.container)
    except SuspendError as e:
        print(f"[suspend_manager] 오류: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
