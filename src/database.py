import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "starter_pack" / "client_intel.db"

CLIENT_COLUMNS = (
    "client_id",
    "client_name",
    "segment",
    "country",
    "account_owner",
    "customer_since",
    "tier",
)


class DatabaseError(Exception):
    pass


@contextmanager
def connect(path: Path = DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    """Open a read-only connection that is always closed on exit."""
    if not path.is_file():
        raise DatabaseError(f"Database not found: {path}")
    try:
        conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as e:
        raise DatabaseError(f"Could not open database {path}: {e}") from e
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def query(sql: str, params: tuple | dict = (), path: Path = DB_PATH) -> list[dict[str, Any]]:
    with connect(path) as conn:
        return [dict(row) for row in conn.execute(sql, params)]


def health_check(path: Path = DB_PATH) -> None:
    """Raise DatabaseError unless the database opens and the clients table has the expected columns."""
    with connect(path) as conn:
        try:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(clients)")}
        except sqlite3.Error as e:
            raise DatabaseError(f"Could not read database {path}: {e}") from e
    if not columns:
        raise DatabaseError(f"Table 'clients' not found in {path}")
    if missing := [c for c in CLIENT_COLUMNS if c not in columns]:
        raise DatabaseError(f"Table 'clients' is missing columns: {', '.join(missing)}")
