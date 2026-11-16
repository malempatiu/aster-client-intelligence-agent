import sqlite3
from datetime import date

import pytest

from src.database import CLIENT_COLUMNS, DB_PATH, DatabaseError
from src.main import main
from src.tools.client_profile import ClientNotFoundError, get_client_profile

ROWS = [
    ("C001", "Halden Bet", "Sportsbook", "GB", "Maya Lindgren", "2021-02-01", "Strategic"),
    ("C002", "Corvane Media", None, "DE", "  ", "2022-06-01", None),
    ("C003", "Brenmoor League", "League/Federation", "NL", "Tomas Ferreira", "01/08/2020", "Core"),
]


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "clients.db"
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE clients ({', '.join(CLIENT_COLUMNS)})")
    conn.executemany(f"INSERT INTO clients VALUES ({', '.join('?' * len(CLIENT_COLUMNS))})", ROWS)
    conn.commit()
    conn.close()
    return path


def test_successful_retrieval(db):
    p = get_client_profile("C001", db)
    assert p.client_id == "C001"
    assert p.warnings == []


def test_all_profile_fields(db):
    p = get_client_profile("C001", db)
    assert (p.client_name, p.segment, p.country, p.account_owner, p.customer_since, p.tier) == (
        "Halden Bet",
        "Sportsbook",
        "GB",
        "Maya Lindgren",
        date(2021, 2, 1),
        "Strategic",
    )


def test_source_primary_key_preserved(db):
    p = get_client_profile("C001", db)
    assert (p.source_table, p.source_primary_key) == ("clients", "C001")


def test_missing_optional_values(db):
    p = get_client_profile("C002", db)
    assert (p.segment, p.account_owner, p.tier) == (None, None, None)
    assert p.country == "DE"
    assert p.warnings == ["segment is missing", "account_owner is missing", "tier is missing"]


def test_invalid_customer_since(db):
    p = get_client_profile("C003", db)
    assert p.customer_since is None
    assert p.warnings == ["customer_since '01/08/2020' is not a valid date"]


def test_duplicate_client_id(db):
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO clients (client_id, client_name) VALUES ('C001', 'Halden Duplicate')")
    conn.commit()
    conn.close()
    p = get_client_profile("C001", db)
    assert p.client_name == "Halden Bet"
    assert p.warnings == ["2 rows share client_id 'C001'; using the first"]


def test_unknown_client_id(db):
    with pytest.raises(ClientNotFoundError, match="'C999'"):
        get_client_profile("C999", db)


def test_no_name_matching(db):
    with pytest.raises(ClientNotFoundError):
        get_client_profile("Halden Bet", db)


def test_missing_database(tmp_path):
    with pytest.raises(DatabaseError, match="Database not found"):
        get_client_profile("C001", tmp_path / "missing.db")


def test_missing_table(tmp_path):
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    with pytest.raises(DatabaseError, match="no such table"):
        get_client_profile("C001", path)


def test_supplied_database():
    before = DB_PATH.stat().st_mtime_ns
    p = get_client_profile("C009")
    assert (p.client_name, p.segment, p.country, p.account_owner, p.customer_since, p.tier) == (
        "Pellucid Odds",
        "Sportsbook",
        "MT",
        "Grace Okafor",
        date(2022, 1, 1),
        "Strategic",
    )
    assert p.source_primary_key == "C009" and p.warnings == []
    assert DB_PATH.stat().st_mtime_ns == before


def test_cli_shows_profile(capsys):
    assert main(["--client", "Pellucid Odds", "--trigger", "upsell"]) == 0
    out = capsys.readouterr().out
    assert "source: clients.client_id = C009" in out
    assert "Grace Okafor" in out and "2022-01-01" in out
