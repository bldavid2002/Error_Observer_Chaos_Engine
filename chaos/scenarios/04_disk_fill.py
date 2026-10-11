"""Consume worker container storage with a bounded temporary file."""

from typing import Any


DISK_FILE = "/tmp/.chaos-massive-file"


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


def inject(client: Any) -> None:
    result = _worker(client).exec_run(
        [
            "dd",
            "if=/dev/zero",
            f"of={DISK_FILE}",
            "bs=1M",
            "count=5000",
            "conv=fsync",
        ],
        user="root",
    )
    if result.exit_code != 0:
        output = result.output.decode(errors="replace").strip()
        if "No space left on device" not in output:
            raise RuntimeError(
                "Could not fill worker storage "
                f"(exit code {result.exit_code}): {output}"
            )


def revert(client: Any) -> None:
    result = _worker(client).exec_run(["rm", "-f", DISK_FILE], user="root")
    if result.exit_code != 0:
        output = result.output.decode(errors="replace").strip()
        raise RuntimeError(
            "Could not remove the temporary disk-fill file "
            f"(exit code {result.exit_code}): {output}"
        )


def get_hint() -> str:
    return (
        "Processing has stalled and logs may report 'No space left on device'. "
        "Check the worker container's writable storage."
    )
