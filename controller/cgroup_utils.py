"""cgroup v2 helpers shared by container_monitor.py and suspend_manager.py.

Resolves a running container's cgroup path via its host PID (works for
both the cgroupfs and systemd cgroup drivers, unlike guessing the path
from the container name/ID) and provides small readers for the
key/value-style files under that path (memory.stat, cpu.stat, memory.events).
"""

import subprocess
from pathlib import Path

CGROUP_ROOT = Path("/sys/fs/cgroup")


class CgroupError(RuntimeError):
    pass


def docker_inspect(container: str, fmt: str) -> str:
    result = subprocess.run(
        ["docker", "inspect", "--format", fmt, container],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CgroupError(
            f"docker inspect 실패 (container={container}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


def get_container_pid(container: str) -> int:
    pid = docker_inspect(container, "{{.State.Pid}}")
    try:
        pid_int = int(pid)
    except ValueError as e:
        raise CgroupError(f"컨테이너 PID를 확인할 수 없습니다: {pid!r}") from e
    if pid_int <= 0:
        raise CgroupError(f"컨테이너가 실행 중이 아닙니다 (PID={pid_int})")
    return pid_int


def get_cgroup_path(pid: int) -> Path:
    """호스트 PID의 /proc/<pid>/cgroup을 읽어 cgroup v2 절대 경로를 반환한다."""
    proc_cgroup = Path(f"/proc/{pid}/cgroup")
    line = proc_cgroup.read_text().strip()
    # cgroup v2 unified hierarchy: "0::<path>"
    for entry in line.splitlines():
        if entry.startswith("0::"):
            relative = entry[len("0::") :]
            return CGROUP_ROOT / relative.lstrip("/")
    raise CgroupError(f"{proc_cgroup}에서 cgroup v2 항목을 찾을 수 없습니다: {line!r}")


def get_container_cgroup_path(container: str) -> Path:
    return get_cgroup_path(get_container_pid(container))


def read_text(path: Path) -> str:
    return path.read_text().strip()


def read_value(path: Path):
    """단일 값 파일을 읽는다. 'max'는 None으로, 그 외는 int로 반환한다."""
    text = read_text(path)
    if text == "max":
        return None
    return int(text)


def read_flat_kv(path: Path) -> dict:
    """'key value' 형식의 줄들로 이루어진 파일을 dict로 파싱한다.

    memory.stat, cpu.stat에 사용한다.
    """
    kv = {}
    for line in read_text(path).splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        key, value = parts
        try:
            kv[key] = int(value)
        except ValueError:
            kv[key] = value
    return kv


def read_events(path: Path) -> dict:
    """memory.events / memory.events.local ('key value' 줄) 파일을 파싱한다."""
    return read_flat_kv(path)
