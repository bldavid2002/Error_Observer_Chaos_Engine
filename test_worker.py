import json
import unittest
from contextlib import nullcontext
from uuid import UUID

from worker import ensure_database_schema, store_message


class FakeCursor:
    def __init__(self) -> None:
        self.query: str | None = None
        self.parameters: tuple[UUID, int] | None = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(
        self, query: str, parameters: tuple[UUID, int] | None = None
    ) -> None:
        self.query = query
        self.parameters = parameters


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()
        self.transactions_started = 0

    def transaction(self):
        self.transactions_started += 1
        return nullcontext()

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


class StoreMessageTests(unittest.TestCase):
    def test_creates_schema_in_a_transaction(self) -> None:
        connection = FakeConnection()

        ensure_database_schema(connection)

        self.assertEqual(connection.transactions_started, 1)
        self.assertIn("CREATE TABLE IF NOT EXISTS tasks", connection.cursor_instance.query or "")

    def test_stores_a_valid_message_idempotently(self) -> None:
        connection = FakeConnection()
        message_id = "b865f2e8-e7ea-4e9d-a3c9-b9d1c45eeb55"

        result = store_message(
            connection, json.dumps({"id": message_id, "number": 42}).encode("utf-8")
        )

        self.assertEqual(result, (message_id, 42))
        self.assertEqual(
            connection.cursor_instance.parameters, (UUID(message_id), 42)
        )
        self.assertIn("ON CONFLICT (id) DO NOTHING", connection.cursor_instance.query or "")

    def test_rejects_a_non_integer_number(self) -> None:
        connection = FakeConnection()
        body = json.dumps(
            {"id": "b865f2e8-e7ea-4e9d-a3c9-b9d1c45eeb55", "number": True}
        ).encode("utf-8")

        with self.assertRaisesRegex(ValueError, "number must be an integer"):
            store_message(connection, body)

        self.assertIsNone(connection.cursor_instance.query)


if __name__ == "__main__":
    unittest.main()
