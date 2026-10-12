"""Simulate and revert a PostgreSQL password drift."""

import os
import secrets
from typing import Any


def _postgres(client: Any) -> Any:
    containers = client.containers.list(
        filters={"label": "com.docker.compose.service=postgres"}
    )
    if len(containers) != 1:
        raise RuntimeError(
            "Expected exactly one running Compose 'postgres' container; "
            f"found {len(containers)}."
        )
    return containers[0]


def _set_password(client: Any, password: str) -> None:
    sql_password = password.replace("'", "''")
    sql = (f"ALTER USER postgres WITH PASSWORD '{sql_password}'; " 
           "SELECT pg_terminate_backend(pid) FROM pg_stat_activity " 
           "WHERE datname = 'app' AND pid <> pg_backend_pid(); "
           )
    result = _postgres(client).exec_run(
        ["psql", "-U", "postgres", "-d", "app", "-c", sql],
        user="postgres",
    )
    if result.exit_code != 0:
        output = result.output.decode(errors="replace").strip()
        raise RuntimeError(
            f"Could not change the PostgreSQL password "
            f"(exit code {result.exit_code}): {output}"
        )


def inject(client: Any) -> None:
    _set_password(client, secrets.token_urlsafe(24))


def revert(client: Any) -> None:
    _set_password(client, os.environ.get("POSTGRES_PASSWORD", "postgres"))


def get_hint() -> str:
    return (
        "The worker is crashing rapidly. Are there any 'Access Denied' or "
        "'Connection Refused' errors in the Loki logs?"
    )
