"""Override the worker's PostgreSQL host entry to a loopback address."""

from typing import Any


HOSTS_BACKUP = "/tmp/.chaos-hosts-backup"
HOSTS_TEMP = "/tmp/.chaos-hosts"


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


def _run(container: Any, command: str) -> None:
    result = container.exec_run(["sh", "-c", command], user="root")
    if result.exit_code != 0:
        output = result.output.decode(errors="replace").strip()
        raise RuntimeError(
            f"Command failed in worker container with exit code "
            f"{result.exit_code}: {output}"
        )


def inject(client: Any) -> None:
    command = (
        f"set -eu; test ! -e {HOSTS_BACKUP}; "
        f"cp /etc/hosts {HOSTS_BACKUP}; "
        "awk '{ for (i = 2; i <= NF; i++) "
        "if ($i == \"postgres\") next; print }' /etc/hosts "
        f"> {HOSTS_TEMP}; "
        f"printf '127.0.0.1 postgres\\n' >> {HOSTS_TEMP}; "
        f"cat {HOSTS_TEMP} > /etc/hosts; "
        f"rm -f {HOSTS_TEMP}"
    )
    _run(_worker(client), command)


def revert(client: Any) -> None:
    command = (
        f"set -eu; test -f {HOSTS_BACKUP}; "
        f"cat {HOSTS_BACKUP} > /etc/hosts; "
        f"rm -f {HOSTS_BACKUP} {HOSTS_TEMP}"
    )
    _run(_worker(client), command)


def get_hint() -> str:
    return (
        "The worker's PostgreSQL hostname is resolving to loopback. Check "
        "host resolution and database connection errors."
    )
