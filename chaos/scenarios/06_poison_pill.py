"""Continuously publish malformed messages to the worker queue."""

from typing import Any


SCRIPT_FILE = "/tmp/.chaos-poison-pill.py"
PID_FILE = "/tmp/.chaos-poison-pill.pid"


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
    publisher = """\
import os
import time

import pika

marker = "chaos_poison_pill_marker"
credentials = pika.PlainCredentials(
    os.environ.get("RABBITMQ_USER", "guest"),
    os.environ.get("RABBITMQ_PASSWORD", "guest"),
)
parameters = pika.ConnectionParameters(
    host=os.environ.get("RABBITMQ_HOST", "rabbitmq"),
    port=int(os.environ.get("RABBITMQ_PORT", "5672")),
    credentials=credentials,
    heartbeat=60,
)
connection = pika.BlockingConnection(parameters)
channel = connection.channel()
channel.queue_declare(queue="tasks", durable=True)
try:
    while True:
        channel.basic_publish(
            exchange="",
            routing_key="tasks",
            body=b'{"id": 123, "data": "missing_bracket...',
        )
        time.sleep(0.1)
finally:
    if connection.is_open:
        connection.close()
"""
    command = (
        f"cat > {SCRIPT_FILE} <<'PY'\n{publisher}PY\n"
        f"nohup python {SCRIPT_FILE} >/dev/null 2>&1 & "
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
        f"case \"$cmdline\" in *{SCRIPT_FILE}*) kill \"$pid\" ;; esac; "
        "fi; "
        f"rm -f {PID_FILE}; "
        "fi; "
        f"rm -f {SCRIPT_FILE}"
    )
    _run(_worker(client), ["sh", "-c", command])


def get_hint() -> str:
    return (
        "The worker is receiving malformed JSON. Check for JSONDecodeError "
        "entries and a rising message_processing_errors_total counter."
    )
