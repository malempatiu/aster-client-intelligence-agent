# Current Feature: SQLite Database Connection

## Status

<!-- Not Started|In Progress|Completed -->

In Progress

## Goals

- Create a reusable SQLite connection utility in `src/database.py` using Python's built-in `sqlite3`
- Open `starter_pack/client_intel.db` in read-only mode; never modify the supplied database
- Resolve the database path reliably, independent of the current working directory
- Support parameterised SQL queries
- Close connections safely (e.g. context manager)
- Raise clear errors for missing databases and connection failures
- Health check verifying: database opens, `clients` table exists, expected client columns are present (based on the actual schema, not the docs)
- pytest tests covering: successful connection, reading client records, parameterised queries, missing database handling, read-only behaviour, connection cleanup, health check

## Notes

- SQLite is the exclusive runtime source of business data — do not use CSV files.
- No ORM or additional database framework.
- Keep database access separate from business logic.
- Use a temporary test database for destructive or failure tests; never touch the original starter database.

## History

<!-- Keep this updated. Earliest to latest -->

- **CLI Input and Request Validation** (2026-11-16): argparse CLI (`uv run -m src.main`) with `--client`, `--trigger`, `--context`, `--request-id`. `ClientRequest` Pydantic model in `src/models/requests.py` (trimmed non-blank client/request ID, four supported triggers, generated request ID, fixed `as_of` 2026-11-01). User-friendly errors with trigger suggestions. pytest added with 12 tests.
