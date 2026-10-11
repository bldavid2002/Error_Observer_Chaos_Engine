# DevOps Practice

A local Docker Compose demo: a Python generator publishes one random-number
message per second to RabbitMQ, and a worker stores messages in PostgreSQL.
Prometheus scrapes the worker's counters, while Promtail forwards both Python
services' log files to Loki.

## Start

```powershell
docker compose up --build -d
docker compose ps
```

Stop the services with `docker compose down`. PostgreSQL, Prometheus and Loki
data are kept in named volumes; remove them with `docker compose down -v` only
if you also want to delete the stored data.

## Local endpoints

| Service | Address | Credentials |
| --- | --- | --- |
| PostgreSQL | `localhost:5432` | database `app`, user `postgres`, password `postgres` |
| RabbitMQ AMQP | `localhost:5672` | user `guest`, password `guest` |
| RabbitMQ management | <http://localhost:15672> | user `guest`, password `guest` |
| Worker metrics | <http://localhost:8000/metrics> | |
| Prometheus | <http://localhost:9090> | |
| Loki API | <http://localhost:3100> | |

The `tasks` table contains `id`, `number`, and `received_at`. The worker exports
`messages_processed_total` and `message_processing_errors_total`. Query stored
logs in Loki with LogQL, for example `{job="python"}`; the `service` label
distinguishes `generator` and `worker`.

These default credentials are intentionally for local development only. Do not
expose these services or reuse the credentials in a shared or production
environment.

## Chaos scenarios

The optional chaos controller can inject one failure into this local Compose
stack and revert the most recent injection. Omit the scenario name to choose
randomly, or name one explicitly:

```powershell
python -m venv .venv-chaos
.\.venv-chaos\Scripts\python.exe -m pip install -r chaos/requirements.txt
.\.venv-chaos\Scripts\python.exe chaos/chaos.py trigger
.\.venv-chaos\Scripts\python.exe chaos/chaos.py trigger 04_disk_fill
.\.venv-chaos\Scripts\python.exe chaos/chaos.py hint
.\.venv-chaos\Scripts\python.exe chaos/chaos.py revert
```

Available scenarios:

| Scenario | Effect |
| --- | --- |
| `01_network_latency` | Adds 2 seconds of network latency to the worker. |
| `02_db_auth_fail` | Changes the PostgreSQL password to break worker database access. |
| `03_rogue_cpu_spike` | Starts a CPU-bound process in the worker. |
| `04_disk_fill` | Writes up to 5,000 MiB to a temporary file in the worker. |
| `05_memory_leak` | Starts an unbounded memory-allocation process in the worker. |
| `06_poison_pill` | Publishes malformed messages continuously to RabbitMQ. |
| `07_dns_failure` | Overrides the worker's `postgres` host entry to loopback. |
| `08_network_packet_loss` | Drops 20% of packets on the worker's network interface. |

Run `revert` after each scenario. The disk scenario can consume up to 5 GiB in
Docker's storage until reverted; make sure the host has enough free space. The
worker has a 512 MiB memory limit so the memory scenario cannot consume host
memory without bound. Inspect container memory and restart behavior with
`docker compose stats` / `docker compose ps`.

The poison-pill publisher sends a continuous stream of invalid messages. The
current worker rejects malformed messages without requeueing, so this drives a
sustained error rate without creating an unbounded redelivery loop.

Rebuild the worker image after the first-time setup so it includes `tc`:

```powershell
docker compose up --build -d
```

The worker is granted the `NET_ADMIN` capability for the latency and packet
loss scenarios. These scenarios interrupt service and are intended only for
this local practice stack. If you changed the PostgreSQL password, set
`POSTGRES_PASSWORD` in the shell running the controller so `revert` restores
the matching value.
