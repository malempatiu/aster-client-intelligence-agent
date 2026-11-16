"""Retrieve a client's account profile by canonical client ID.

The client ID must already be resolved; no name or fuzzy matching happens here.
Missing or invalid values are kept as None and reported in `warnings`.
"""

import sqlite3
from datetime import date
from pathlib import Path

from src.database import CLIENT_COLUMNS, DB_PATH, DatabaseError, query
from src.models.profile import ClientProfile

SOURCE_TABLE = "clients"
OPTIONAL_FIELDS = ("client_name", "segment", "country", "account_owner", "customer_since", "tier")


class ClientNotFoundError(LookupError):
    """Raised when no client row exists for the given client ID."""


def get_client_profile(client_id: str, path: Path = DB_PATH) -> ClientProfile:
    sql = f"SELECT {', '.join(CLIENT_COLUMNS)} FROM {SOURCE_TABLE} WHERE client_id = ?"
    try:
        rows = query(sql, (client_id,), path=path)
    except sqlite3.Error as e:
        raise DatabaseError(f"Could not read client profile from {path}: {e}") from e
    if not rows:
        raise ClientNotFoundError(f"No client found with ID '{client_id}'")

    row = rows[0]
    warnings = []
    if len(rows) > 1:
        warnings.append(f"{len(rows)} rows share client_id '{client_id}'; using the first")
    for field in OPTIONAL_FIELDS:
        value = row[field]
        if value is None or not str(value).strip():
            row[field] = None
            warnings.append(f"{field} is missing")

    if (raw := row["customer_since"]) is not None:
        try:
            row["customer_since"] = date.fromisoformat(str(raw).strip())
        except ValueError:
            row["customer_since"] = None
            warnings.append(f"customer_since '{raw}' is not a valid date")

    return ClientProfile(**row, source_table=SOURCE_TABLE, source_primary_key=row["client_id"], warnings=warnings)
