import json
import logging
import os
import random
import time
import uuid
from logging.handlers import RotatingFileHandler

import pika


QUEUE_NAME = "tasks"


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("generator")
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


def main() -> None:
    logger = configure_logging()
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

    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    logger.info("Connected to RabbitMQ; publishing to queue %s", QUEUE_NAME)

    try:
        while True:
            message = {"id": str(uuid.uuid4()), "number": random.randint(0, 1000)}
            channel.basic_publish(
                exchange="",
                routing_key=QUEUE_NAME,
                body=json.dumps(message).encode("utf-8"),
                properties=pika.BasicProperties(
                    delivery_mode=pika.DeliveryMode.Persistent,
                    content_type="application/json",
                    message_id=message["id"],
                ),
            )
            logger.info("Published message id=%s number=%d", message["id"], message["number"])
            time.sleep(1)
    finally:
        if connection.is_open:
            connection.close()


if __name__ == "__main__":
    main()
