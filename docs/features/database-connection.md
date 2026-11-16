# SQLite database connection for Aster Intelligence.

## Objective

Create a reusable SQLite connection utility that all future analysis tools can use.
This utility should be under `src/database.py`

## Database

### Use:

- starter_pack/client_intel.db

SQLite is the exclusive runtime source of business data. Do not use CSV files.

## Requirements

- Use Python's built-in sqlite3 library.

- Open the database in read-only mode.

- Resolve the database path reliably, regardless of the terminal's current working directory.

- Provide a reusable connection utility.

- Support parameterised SQL queries.

- Ensure connections are closed safely.

- Handle missing databases and connection failures clearly.

- Never modify the supplied database.

- Do not introduce an ORM or additional database framework.

- Keep database access separate from business logic.

## Database health check

Implement a small health check that verifies:

- The database can be opened.

- The clients table exists.

- The expected client columns are available.

Use the actual supplied database schema rather than assuming it matches the documentation.

## Tests

Add pytest tests for:

- Successful database connection.

- Reading client records.

- Parameterised SQL queries.

- Missing database handling.

- Read-only behaviour.

- Connection cleanup.

- Database health check.

Use a temporary test database for destructive or failure tests. Never modify the original starter database.

