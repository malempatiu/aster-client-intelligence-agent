import sqlite3

import pytest

from src.database import (
    CLIENT_COLUMNS,
    DB_PATH,
    DatabaseError,
    connect,
    health_check,
    query,
)


@pytest.fixture
def temp_db(tmp_path):
    path = tmp_path / "test.db"
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE clients ({', '.join(CLIENT_COLUMNS)})")
    conn.execute("INSERT INTO clients (client_id, client_name) VALUES ('C001', 'Test Client')")
    conn.commit()
    conn.close()
    return path


def test_connects_to_starter_database():
    with connect() as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_reads_client_records():
    rows = query("SELECT * FROM clients")
    assert len(rows) > 0
    assert set(CLIENT_COLUMNS) <= rows[0].keys()


def test_parameterised_query():
    rows = query("SELECT client_name FROM clients WHERE client_id = ?", ("C001",))
    assert rows == [{"client_name": "Halden Bet"}]
    rows = query("SELECT client_id FROM clients WHERE client_name = :name", {"name": "Halden Bet"})
    assert rows == [{"client_id": "C001"}]


def test_parameters_are_not_interpolated():
    assert query("SELECT * FROM clients WHERE client_id = ?", ("C001' OR '1'='1",)) == []


def test_missing_database(tmp_path):
    with pytest.raises(DatabaseError, match="Database not found"), connect(tmp_path / "missing.db"):
        pass


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(DatabaseError):
        query("SELECT 1", path=path)
    assert not path.exists()


def test_writes_are_rejected(temp_db):
    with connect(temp_db) as conn, pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("DELETE FROM clients")
    assert len(query("SELECT * FROM clients", path=temp_db)) == 1


def test_connection_closed_after_use(temp_db):
    with connect(temp_db) as conn:
        pass
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_connection_closed_after_error(temp_db):
    with pytest.raises(RuntimeError), connect(temp_db) as conn:
        raise RuntimeError
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_health_check_passes_on_starter_database():
    health_check()


def test_starter_database_unchanged():
    before = DB_PATH.stat().st_mtime_ns
    health_check()
    query("SELECT * FROM clients")
    assert DB_PATH.stat().st_mtime_ns == before


def test_health_check_missing_table(tmp_path):
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    with pytest.raises(DatabaseError, match="'clients' not found"):
        health_check(path)


def test_health_check_missing_columns(tmp_path):
    path = tmp_path / "partial.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE clients (client_id, client_name)")
    conn.close()
    with pytest.raises(DatabaseError, match="missing columns: segment"):
        health_check(path)


def test_health_check_invalid_file(tmp_path):
    path = tmp_path / "not_a_db.db"
    path.write_text("not a database")
    with pytest.raises(DatabaseError, match="Could not read database"):
        health_check(path)
