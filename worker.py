import json
import logging
import os
import uuid
from logging.handlers import RotatingFileHandler
from typing import Any

import pika
import psycopg
from prometheus_client import Counter, start_http_server


QUEUE_NAME = "tasks"
MESSAGES_PROCESSED = Counter(
    "messages_processed_total",
    "Number of messages successfully processed and stored in PostgreSQL",
)
MESSAGE_ERRORS = Counter(
    "message_processing_errors_total",
    "Number of messages that could not be processed",
)


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("worker")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_file = os.environ.get("LOG_FILE")
    if log_file:
        file_handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger


def get_database_connection() -> psycopg.Connection[Any]:
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "app"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
    )


def ensure_database_schema(connection: psycopg.Connection[Any]) -> None:
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id UUID PRIMARY KEY,
                    number INTEGER NOT NULL,
                    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )


def store_message(connection: psycopg.Connection[Any], body: bytes) -> tuple[str, int]:
    message: Any = json.loads(body)
    if not isinstance(message, dict):
        raise ValueError("message must be a JSON object")

    raw_message_id = message["id"]
    if not isinstance(raw_message_id, str):
        raise ValueError("message id must be a UUID string")
    message_id = uuid.UUID(raw_message_id)
    number = message["number"]
    if isinstance(number, bool) or not isinstance(number, int):
        raise ValueError("message number must be an integer")

    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tasks (id, number)
                VALUES (%s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (message_id, number),
            )
    return str(message_id), number


def main() -> None:
    logger = configure_logging()
    metrics_port = int(os.environ.get("METRICS_PORT", "8000"))
    start_http_server(metrics_port)
    logger.info("Prometheus metrics exposed on port %d", metrics_port)

    database = get_database_connection()
    ensure_database_schema(database)
    logger.info("Connected to PostgreSQL and ensured tasks table exists")

    credentials = pika.PlainCredentials(
        os.environ.get("RABBITMQ_USER", "guest"),
        os.environ.get("RABBITMQ_PASSWORD", "guest"),
    )
    parameters = pika.ConnectionParameters(
        host=os.environ.get("RABBITMQ_HOST", "localhost"),
        port=int(os.environ.get("RABBITMQ_PORT", "5672")),
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30,
        connection_attempts=10,
        retry_delay=3,
    )
    rabbitmq = pika.BlockingConnection(parameters)
    channel = rabbitmq.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)
    logger.info("Connected to RabbitMQ; consuming from queue %s", QUEUE_NAME)

    def handle_message(
        current_channel: pika.adapters.blocking_connection.BlockingChannel,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
    ) -> None:
        del properties
        try:
            message_id, number = store_message(database, body)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            MESSAGE_ERRORS.inc()
            logger.error("Discarding invalid message: %s", error)
            current_channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return
        except psycopg.Error:
            MESSAGE_ERRORS.inc()
            logger.exception("Database error while processing message; requeueing")
            current_channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            return

        MESSAGES_PROCESSED.inc()
        current_channel.basic_ack(delivery_tag=method.delivery_tag)
        logger.info("Stored message id=%s number=%d", message_id, number)

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=handle_message)
    try:
        channel.start_consuming()
    finally:
        if rabbitmq.is_open:
            rabbitmq.close()
        database.close()


if __name__ == "__main__":
    main()
