"""Start and stop a marked memory-consuming process in the worker."""

import shlex
from typing import Any


PID_FILE = "/tmp/.chaos-memory-leak.pid"
PROCESS_MARKER = "chaos_memory_leak_marker"


def _worker(client: Any) -> Any:
    containers = client.containers.list(
        filters={"label": "com.docker.compose.service=worker"}
    )
    if len(containers) != 1:
        raise RuntimeError(
            "Expected exactly one running Compose 'worker' container; "
            f"found {len(containers)}."
        )
    return containers[0]


def _run(container: Any, command: list[str]) -> Any:
    result = container.exec_run(command, user="root")
    if result.exit_code != 0:
        output = result.output.decode(errors="replace").strip()
        raise RuntimeError(
            f"Command failed in worker container with exit code "
            f"{result.exit_code}: {output}"
        )
    return result


def inject(client: Any) -> None:
    code = (
        f"a = []  # {PROCESS_MARKER}\n"
        "while True:\n"
        "    a.append(' ' * 10**6)\n"
    )
    command = (
        f"nohup python -c {shlex.quote(code)} >/dev/null 2>&1 & "
        f"echo $! > {PID_FILE}"
    )
    _run(_worker(client), ["sh", "-c", command])


def revert(client: Any) -> None:
    command = (
        f"if [ -f {PID_FILE} ]; then "
        f"pid=$(cat {PID_FILE}); "
        'case "$pid" in ""|*[!0-9]*) exit 2 ;; esac; '
        f"if [ -r /proc/$pid/cmdline ]; then "
        "cmdline=$(tr '\\000' ' ' < /proc/$pid/cmdline); "
        f"case \"$cmdline\" in *{PROCESS_MARKER}*) kill \"$pid\" ;; esac; "
        "fi; "
        f"rm -f {PID_FILE}; "
        "fi"
    )
    _run(_worker(client), ["sh", "-c", command])


def get_hint() -> str:
    return (
        "Worker memory is climbing. Check container memory usage and whether "
        "the worker was OOM-killed or restarted."
    )
