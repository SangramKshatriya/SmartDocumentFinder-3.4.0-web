import os
import pytest

import history_store
from history_store import backend_name, database_url


def test_backend_auto_uses_sqlite_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert backend_name() == "sqlite"


def test_backend_auto_uses_postgres_for_postgres_url(monkeypatch):
    monkeypatch.delenv("DATABASE_BACKEND", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://user:pass@localhost:5432/smartdocumentfinder",
    )
    assert backend_name() == "postgresql"


def test_explicit_postgres_requires_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_BACKEND", "postgresql")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        database_url()


def test_postgres_url_is_normalized_to_psycopg_v3(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    assert database_url() == "postgresql+psycopg://u:p@localhost/db"


@pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_URL"),
    reason="Set TEST_POSTGRES_URL to run the real PostgreSQL integration test",
)
def test_real_postgres_history_round_trip(monkeypatch):
    import history_store
    from uuid import uuid4

    monkeypatch.setenv("DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_POSTGRES_URL"])

    history_store.initialize_postgresql()

    username = f"pytest_{uuid4().hex[:8]}"
    session_id = history_store.start_session_pg(username, "Pytest User")
    search_id = history_store.record_search_history_pg(
        username=username,
        display_name="Pytest User",
        session_id=session_id,
        original_query="show my PAN card",
        canonical_query="pan card",
        input_mode="voice",
        provider="sarvam",
        document_type="pan",
        results_count=1,
        success=True,
    )
    assert search_id > 0
    assert history_store.get_search_history_pg(username, 10)[0]["document_type"] == "pan"

    history_store.record_document_access_pg(
        username=username,
        display_name="Pytest User",
        session_id=session_id,
        document_name="PAN Card.pdf",
        document_path="/documents/PAN Card.pdf",
        source="local",
        search_history_id=search_id,
    )
    assert history_store.get_document_history_pg(username, 10)[0]["document_name"] == "PAN Card.pdf"
    history_store.end_session_pg(session_id)
    assert history_store.get_session_history_pg(username, 10)[0]["logout_status"] == "PASS"

class _FakeRow:
    def __init__(self, values):
        self._mapping = values


class _FakeResult:
    def __init__(self, scalar=1, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one(self):
        return self._scalar

    def __iter__(self):
        return iter(self._rows)


class _FakeConnection:
    def __init__(self):
        self.statements = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, params))
        if "SELECT *" in sql and "event_type = 'SEARCH'" in sql:
            return _FakeResult(rows=[_FakeRow({
                "id": 1,
                "username": "tester",
                "display_name": "Test User",
                "event_type": "SEARCH",
                "event_time": __import__("datetime").datetime(2026, 10, 8, 10, 0, tzinfo=__import__("datetime").timezone.utc),
                "searched_at": __import__("datetime").datetime(2026, 10, 8, 10, 0, tzinfo=__import__("datetime").timezone.utc),
                "completed_at": __import__("datetime").datetime(2026, 10, 8, 10, 1, tzinfo=__import__("datetime").timezone.utc),
                "status": "PASS",
                "document_type": "pan",
            })])
        return _FakeResult()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _FakeBegin:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_):
        return False


class _FakeEngine:
    def __init__(self):
        self.connection = _FakeConnection()

    def begin(self):
        return _FakeBegin(self.connection)


def test_postgres_search_history_uses_parameterized_queries(monkeypatch):
    fake = _FakeEngine()
    monkeypatch.setattr(history_store, "_pg_engine", lambda: fake)

    inserted = history_store.record_search_history_pg(
        username="tester",
        display_name="Test User",
        original_query="show my PAN card",
        canonical_query="pan card",
        input_mode="voice",
        provider="sarvam",
        document_type="pan",
        results_count=1,
        success=True,
    )
    rows = history_store.get_search_history_pg("tester", 10)

    assert inserted == 1
    assert rows[0]["document_type"] == "pan"
    assert rows[0]["searched_at"].endswith("+00:00")
    insert_sql, insert_params = fake.connection.statements[0]
    assert ":username" in insert_sql
    assert "show my PAN card" not in insert_sql
    assert insert_params["original_query"] == "show my PAN card"

def test_database_routes_activity_calls_to_postgres(monkeypatch):
    import database

    monkeypatch.setenv("DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")

    called = []

    monkeypatch.setattr(
        database,
        "record_search_history_pg",
        lambda **kwargs: called.append(kwargs) or 42,
    )
    result = database.record_search_history(
        username="tester",
        original_query="show pan",
        success=True,
    )
    assert result == 42
    assert called[0]["username"] == "tester"
    assert called[0]["original_query"] == "show pan"

def test_initialize_database_initializes_postgres_without_creating_local_activity_table(monkeypatch, tmp_path):
    import database

    monkeypatch.setenv("DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "docs.db")
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)

    calls = []
    monkeypatch.setattr(database, "initialize_postgresql_history", lambda: calls.append(True))

    database.initialize_database()
    assert calls == [True]

    with database.get_connection() as connection:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "documents" in tables
    assert "activity_history" not in tables
