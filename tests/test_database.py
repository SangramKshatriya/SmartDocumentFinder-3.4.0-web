# Basic schema smoke test. The production database path is intentionally not touched here.
import sqlite3


def test_sqlite_fts5_available():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE VIRTUAL TABLE docs USING fts5(name, content)")
    connection.execute("INSERT INTO docs(name, content) VALUES ('PAN.pdf', 'permanent account number')")
    row = connection.execute("SELECT name FROM docs WHERE docs MATCH 'PAN'").fetchone()
    assert row[0] == "PAN.pdf"
