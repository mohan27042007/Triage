"""Unit checks for ordered, transactional PostgreSQL migration behavior."""

import unittest

from postgres_migrations import (
    CORE_POSTGRES_MIGRATIONS,
    HOSTED_POSTGRES_MIGRATIONS,
    PostgresMigration,
    apply_postgres_migrations,
)


class _Result:
    def __init__(self, rows=()) -> None:
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, applied=()) -> None:
        self.applied = set(applied)
        self.queries: list[tuple[str, object]] = []

    def execute(self, query: str, parameters=()):
        self.queries.append((query, parameters))
        if query == "SELECT id FROM postgres_schema_migrations":
            return _Result([{"id": identifier} for identifier in self.applied])
        if query.startswith("INSERT INTO postgres_schema_migrations"):
            self.applied.add(parameters[0])
        return _Result()


class PostgresMigrationTests(unittest.TestCase):
    def test_current_migration_inventory_is_ordered_and_unique(self) -> None:
        core_identifiers = [migration.identifier for migration in CORE_POSTGRES_MIGRATIONS]
        hosted_identifiers = [migration.identifier for migration in HOSTED_POSTGRES_MIGRATIONS]
        identifiers = [*core_identifiers, *hosted_identifiers]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(core_identifiers, sorted(core_identifiers))
        self.assertEqual(hosted_identifiers, sorted(hosted_identifiers))

    def test_applies_new_migrations_in_order_and_records_them(self) -> None:
        connection = _Connection(applied={"001-existing"})
        events: list[str] = []
        migrations = (
            PostgresMigration("001-existing", lambda _: events.append("existing")),
            PostgresMigration("002-next", lambda _: events.append("next")),
            PostgresMigration("003-last", lambda _: events.append("last")),
        )

        self.assertEqual(apply_postgres_migrations(connection, migrations), ["002-next", "003-last"])
        self.assertEqual(events, ["next", "last"])
        self.assertEqual(connection.applied, {"001-existing", "002-next", "003-last"})
        self.assertIn("SELECT pg_advisory_xact_lock(%s)", [query for query, _ in connection.queries])

    def test_failed_migration_is_not_recorded(self) -> None:
        connection = _Connection()

        def fail(_connection) -> None:
            raise RuntimeError("expected failure")

        with self.assertRaisesRegex(RuntimeError, "expected failure"):
            apply_postgres_migrations(connection, (PostgresMigration("001-fails", fail),))
        self.assertNotIn("001-fails", connection.applied)


if __name__ == "__main__":
    unittest.main()
