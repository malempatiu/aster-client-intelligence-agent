# Current Feature: Client Resolver

## Status

<!-- Not Started|In Progress|Completed -->

In Progress

## Goals

<!-- Goals & requirements -->

- Resolve free-text client input (client name or client ID) into a canonical client record
- Matching strategies applied in order: exact client ID → exact name → case-insensitive/whitespace-normalised name → conservative fuzzy matching (suggestions only)
- Never auto-select an ambiguous client (including ambiguous fuzzy matches)
- Deterministic fuzzy matching using the standard library (e.g. `difflib`), with documented thresholds; no fuzzy-matching dependency
- Return one of three statuses: `resolved`, `ambiguous`, `not_found`
- Pydantic `ClientResolution` model with: input value, status, canonical client ID/name (when resolved), match type, candidate matches, and confidence/similarity score where applicable
- Never invent clients or client IDs
- CLI integration after `ClientRequest` validation: show canonical ID and name when resolved, show candidate suggestions when ambiguous, exit with a clear error when not found
- Tests for: exact ID, exact name, case-insensitive name, leading/trailing whitespace, unique normalised match, ambiguous name, unknown client, empty input, fuzzy suggestions, no auto-resolution of ambiguous fuzzy match
- Use fixtures / temporary SQLite databases where appropriate, plus an integration smoke test against the supplied read-only database

## Notes

<!-- Any extra notes -->

- Spec: `docs/features/client-resolver.md`
- Out of scope: planner, orchestrator, and client profile retrieval
- Build on the existing read-only `src/database.py` (`connect()`, `query()`) and the `ClientRequest` model in `src/models/requests.py`
- After implementation: run pytest and Ruff; demonstrate resolution of "Halden Bet", "C009", and an unknown client; report all modified files and test results

## History

<!-- Keep this updated. Earliest to latest -->

- **CLI Input and Request Validation** (2026-11-16): argparse CLI (`uv run -m src.main`) with `--client`, `--trigger`, `--context`, `--request-id`. `ClientRequest` Pydantic model in `src/models/requests.py` (trimmed non-blank client/request ID, four supported triggers, generated request ID, fixed `as_of` 2026-11-01). User-friendly errors with trigger suggestions. pytest added with 12 tests.
- **SQLite Database Connection** (2026-11-16): `src/database.py` with read-only `connect()` context manager (path resolved from module location, `?mode=ro` URI), parameterised `query()` returning dicts, and `health_check()` for the `clients` table and its 7 columns. `DatabaseError` for missing/unopenable databases. 14 pytest tests using temporary databases for destructive cases. ruff added as a dev dependency.
