"""Add and remove packet loss on the worker's network interface."""

from typing import Any


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


def _run(container: Any, command: list[str]) -> None:
    result = container.exec_run(command, user="root")
    if result.exit_code != 0:
        output = result.output.decode(errors="replace").strip()
        raise RuntimeError(
            f"Command failed in worker container with exit code "
            f"{result.exit_code}: {output}"
        )


def inject(client: Any) -> None:
    _run(
        _worker(client),
        [
            "tc",
            "qdisc",
            "replace",
            "dev",
            "eth0",
            "root",
            "netem",
            "loss",
            "20%",
        ],
    )


def revert(client: Any) -> None:
    _run(_worker(client), ["tc", "qdisc", "del", "dev", "eth0", "root"])


def get_hint() -> str:
    return (
        "Processing is erratic rather than fully stopped. Look for intermittent "
        "timeouts and packet loss on the worker network interface."
    )
