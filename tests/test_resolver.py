import sqlite3

import pytest

from src.database import CLIENT_COLUMNS
from src.main import main
from src.resolver import resolve_client

CLIENTS = [
    ("C001", "Halden Bet"),
    ("C002", "Corvane Media"),
    ("C003", "Northgate Sports"),
    ("C004", "northgate  sports"),
    ("C005", "Brightfold Play"),
    ("C006", "Brightfold Plays"),
]


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "clients.db"
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE clients ({', '.join(CLIENT_COLUMNS)})")
    conn.executemany("INSERT INTO clients (client_id, client_name) VALUES (?, ?)", CLIENTS)
    conn.commit()
    conn.close()
    return path


def test_exact_client_id(db):
    r = resolve_client("C002", db)
    assert (r.status, r.client_id, r.client_name, r.match_type) == ("resolved", "C002", "Corvane Media", "client_id")


def test_exact_name(db):
    r = resolve_client("Halden Bet", db)
    assert (r.status, r.client_id, r.match_type) == ("resolved", "C001", "exact_name")


def test_case_insensitive_name(db):
    r = resolve_client("HALDEN bet", db)
    assert (r.status, r.client_id, r.match_type) == ("resolved", "C001", "normalised_name")


def test_leading_and_trailing_whitespace(db):
    r = resolve_client("  Corvane Media  ", db)
    assert (r.status, r.client_id, r.match_type) == ("resolved", "C002", "exact_name")
    assert r.input == "  Corvane Media  "


def test_unique_normalised_match(db):
    r = resolve_client("corvane    MEDIA", db)
    assert (r.status, r.client_id, r.match_type, r.score) == ("resolved", "C002", "normalised_name", 1.0)


def test_ambiguous_name(db):
    r = resolve_client("NORTHGATE SPORTS", db)
    assert r.status == "ambiguous"
    assert r.client_id is None
    assert [c.client_id for c in r.candidates] == ["C003", "C004"]


def test_unknown_client(db):
    r = resolve_client("Acme Widgets", db)
    assert r.status == "not_found"
    assert r.client_id is None and r.candidates == []


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_input(db, value):
    r = resolve_client(value, db)
    assert r.status == "not_found"
    assert r.candidates == []


def test_fuzzy_suggestion(db):
    r = resolve_client("Haldan Bet", db)
    assert r.status == "ambiguous"
    assert r.match_type == "fuzzy"
    assert r.client_id is None
    assert [c.client_id for c in r.candidates] == ["C001"]
    assert 0.8 <= r.candidates[0].score < 1


def test_ambiguous_fuzzy_not_resolved(db):
    r = resolve_client("Brightfold Pla", db)
    assert r.status == "ambiguous"
    assert r.client_id is None and r.client_name is None
    assert {c.client_id for c in r.candidates} == {"C005", "C006"}


def test_smoke_supplied_database():
    assert resolve_client("Halden Bet").client_id == "C001"
    assert resolve_client("C009").client_name == "Pellucid Odds"
    assert resolve_client("Unknown Client Ltd").status == "not_found"


def test_cli_resolved(capsys):
    assert main(["--client", "C009", "--trigger", "upsell"]) == 0
    assert "Client resolved: C009 Pellucid Odds" in capsys.readouterr().out


def test_cli_ambiguous_suggests(capsys):
    assert main(["--client", "Haldan Bet", "--trigger", "at_risk"]) == 1
    err = capsys.readouterr().err
    assert "Did you mean" in err and "C001  Halden Bet" in err


def test_cli_not_found(capsys):
    assert main(["--client", "Unknown Client Ltd", "--trigger", "renewal"]) == 1
    assert "no client found matching 'Unknown Client Ltd'" in capsys.readouterr().err
