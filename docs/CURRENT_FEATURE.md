# Current Feature: Client Profile Tool

## Status

<!-- Not Started|In Progress|Completed -->

In Progress

## Goals

- Deterministic tool that retrieves a client's account profile by canonical (already-resolved) `client_id`
- No fuzzy matching or name resolution inside the tool
- Reuse the existing SQLite connection utility (`src/database.py`) with parameterised SQL against the `clients` table
- `ClientProfile` Pydantic model (create or reuse) returning all seven client fields, source table, source primary key (`client_id`), and data-quality warnings
- Retrieve segment, country, owner, customer_since, tier
- Parse `customer_since` as a date where valid; warn on invalid dates
- Preserve missing optional values as missing with a warning; never invent or substitute values
- Unknown `client_id` returns a clear not-found result or a documented exception
- CLI: after successful resolution, invoke the profile tool and display the profile readably
- pytest tests: successful retrieval, correct client ID, all fields retrieved, missing optional values, invalid `customer_since`, unknown client ID, database errors, source primary key preservation
- Temporary SQLite databases for controlled cases, plus an integration test against the supplied read-only database

## Notes

- Spec: `docs/features/client-profile-implementation.md`
- Before implementing: read AGENTS.md and TECH_STACK.md, inspect project structure, existing Pydantic models, and the actual `clients` table schema
- Location: use the existing `src/tools/` directory and naming conventions (spec recommends `src/tools/resolver.py`; avoid duplicating the client resolver — extend that module only if consistent with project structure)
- Working tree already has uncommitted changes moving `src/resolver.py` → `src/tools/resolver.py` (with `src/main.py` and `tests/test_resolver.py` import updates)
- Out of scope: contract analysis, usage analysis, LLM calls, planner, orchestrator, modifying the original database, CSV files

## History

<!-- Keep this updated. Earliest to latest -->

- **CLI Input and Request Validation** (2026-11-16): argparse CLI (`uv run -m src.main`) with `--client`, `--trigger`, `--context`, `--request-id`. `ClientRequest` Pydantic model in `src/models/requests.py` (trimmed non-blank client/request ID, four supported triggers, generated request ID, fixed `as_of` 2026-11-01). User-friendly errors with trigger suggestions. pytest added with 12 tests.
- **SQLite Database Connection** (2026-11-16): `src/database.py` with read-only `connect()` context manager (path resolved from module location, `?mode=ro` URI), parameterised `query()` returning dicts, and `health_check()` for the `clients` table and its 7 columns. `DatabaseError` for missing/unopenable databases. 14 pytest tests using temporary databases for destructive cases. ruff added as a dev dependency.
- **Client Resolver** (2026-11-16): `resolve_client()` in `src/resolver.py` matches exact client ID, exact name, then case/whitespace-normalised ID or name; `difflib` fuzzy suggestions (threshold 0.8, max 5) are never auto-selected. `ClientResolution`/`ClientCandidate` models in `src/models/resolution.py` with `resolved`/`ambiguous`/`not_found` status, match type, score and candidates. CLI prints the canonical client, lists suggestions when ambiguous, and exits 1 when unresolved. 14 new tests (41 total).
