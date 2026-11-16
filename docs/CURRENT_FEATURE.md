# Current Feature

<!-- Feature Name -->

## Status

<!-- Not Started|In Progress|Completed -->

Not Started

## Goals

<!-- Goals & requirements -->

## Notes

<!-- Any extra notes -->

## History

<!-- Keep this updated. Earliest to latest -->

- **CLI Input and Request Validation** (2026-11-16): argparse CLI (`uv run -m src.main`) with `--client`, `--trigger`, `--context`, `--request-id`. `ClientRequest` Pydantic model in `src/models/requests.py` (trimmed non-blank client/request ID, four supported triggers, generated request ID, fixed `as_of` 2026-11-01). User-friendly errors with trigger suggestions. pytest added with 12 tests.
- **SQLite Database Connection** (2026-11-16): `src/database.py` with read-only `connect()` context manager (path resolved from module location, `?mode=ro` URI), parameterised `query()` returning dicts, and `health_check()` for the `clients` table and its 7 columns. `DatabaseError` for missing/unopenable databases. 14 pytest tests using temporary databases for destructive cases. ruff added as a dev dependency.
- **Client Resolver** (2026-11-16): `resolve_client()` in `src/resolver.py` matches exact client ID, exact name, then case/whitespace-normalised ID or name; `difflib` fuzzy suggestions (threshold 0.8, max 5) are never auto-selected. `ClientResolution`/`ClientCandidate` models in `src/models/resolution.py` with `resolved`/`ambiguous`/`not_found` status, match type, score and candidates. CLI prints the canonical client, lists suggestions when ambiguous, and exits 1 when unresolved. 14 new tests (41 total).
