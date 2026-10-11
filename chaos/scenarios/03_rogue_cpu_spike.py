"""Start and stop a marked CPU-bound process in the worker container."""

from typing import Any


PID_FILE = "/tmp/.chaos-rogue-cpu.pid"
PROCESS_MARKER = "chaos_rogue_cpu_marker"


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
    command = (
        f"nohup python -c 'while True: pass  # {PROCESS_MARKER}' "
        f">/dev/null 2>&1 & echo $! > {PID_FILE}"
    )
    _run(_worker(client), ["sh", "-c", command])


def revert(client: Any) -> None:
    command = (
        f"if [ -f {PID_FILE} ]; then "
        f"pid=$(cat {PID_FILE}); "
        'case "$pid" in ""|*[!0-9]*) exit 2 ;; esac; '
        f"if [ -r /proc/$pid/cmdline ]; then "
        f"cmdline=$(tr '\\000' ' ' < /proc/$pid/cmdline); "
        f"case \"$cmdline\" in *{PROCESS_MARKER}*) kill \"$pid\" ;; esac; "
        "fi; "
        f"rm -f {PID_FILE}; "
        "fi"
    )
    _run(_worker(client), ["sh", "-c", command])


def get_hint() -> str:
    return (
        "Processing has crawled to a halt. Take a look at the CPU "
        "utilization panel on your Grafana dashboard."
    )
