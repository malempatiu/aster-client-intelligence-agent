# Current Feature: Contract Status Tool

<!-- Feature Name -->

## Status

<!-- Not Started|In Progress|Completed -->

In Progress

## Goals

<!-- Goals & requirements -->

- Implement `get_contract_status(client_id, as_of)` as the only new public tool; inputs are exactly `client_id` (canonical, from the resolver) and `as_of` (2026-11-01 for this exercise, supplied by configuration).
- Return a structured Pydantic v2 result covering: current-contract resolution (`confirmed` / `none` / `ambiguous` / `unknown`), the current contract, its products, header ARR vs. contract-line fee reconciliation, end date and days until end, notice deadline and days until notice, auto-renewal status, pending-signature contracts, ARR change at the latest signed renewal, structured data-quality warnings, and source IDs with physical rowids.
- Use the read-only SQLite database (`data/starter_pack/client_intel.db`) through the existing `database.connect()` as the only runtime data source. No CSV, no LLM, no writes to the database.
- Validate every TEXT date, numeric, and status value in Python before use. Never coerce invalid values to zero, infer missing dates, or infer `auto_renew`.
- Classify duplicate contract IDs (unique, identical, conflicting, missing/blank) and contract-line IDs. Exact duplicates count once and keep all rowids. Conflicting IDs are never silently resolved and are excluded from commercial calculations. No join multiplication of ARR or fees.
- Implement every formula in spec section 6: in-force rule (inclusive dates), days until end, notice deadline, auto-renew mapping, ARR reconciliation, and renewal ARR change labelled as chronological inference.
- Pytest tests with temporary SQLite databases covering spec section 10 (classification, duplicates, calculations, renewals, integration). Ruff passes.
- Integration checks against the real database for at least two clients, including `C006` (known duplicate `K-0010`). At least one result independently verified with SQL. Source database unchanged.

## Notes

- Spec: `docs/features/contract-status-tool.md`. Output requirements reference `tool_catalogue.md`, which has not been checked yet.
- Spec section 14 asks for a short implementation plan, and for any real-data ambiguities to be raised, before implementation begins.
- Known data facts from the spec: `contracts` has no PRIMARY KEY in SQLite, so duplicate `contract_id` rows exist. All columns are stored as TEXT. `rowid` is a locator for this snapshot only, not a permanent ID.
- Duplicate policy is in spec section 4. Do not rely on `SELECT DISTINCT` alone.
- Do not hardcode client, contract, line, product, ARR, or rowid values from the spec's illustrative JSON.
- Out of scope: usage, support, CRM, white-space, meeting notes, planner, orchestrator, LLM briefing writer, briefing verification, UI, and deployment. Public inputs must not change.
- Do not begin another feature until this one has been reviewed.

## History

<!-- Keep this updated. Earliest to latest -->

- **CLI Input and Request Validation** (2026-11-16): argparse CLI (`uv run -m src.main`) with `--client`, `--trigger`, `--context`, `--request-id`. `ClientRequest` Pydantic model in `src/models/requests.py` (trimmed non-blank client/request ID, four supported triggers, generated request ID, fixed `as_of` 2026-11-01). User-friendly errors with trigger suggestions. pytest added with 12 tests.
- **SQLite Database Connection** (2026-11-16): `src/database.py` with read-only `connect()` context manager (path resolved from module location, `?mode=ro` URI), parameterised `query()` returning dicts, and `health_check()` for the `clients` table and its 7 columns. `DatabaseError` for missing/unopenable databases. 14 pytest tests using temporary databases for destructive cases. ruff added as a dev dependency.
- **Client Resolver** (2026-11-16): `resolve_client()` in `src/resolver.py` matches exact client ID, exact name, then case/whitespace-normalised ID or name; `difflib` fuzzy suggestions (threshold 0.8, max 5) are never auto-selected. `ClientResolution`/`ClientCandidate` models in `src/models/resolution.py` with `resolved`/`ambiguous`/`not_found` status, match type, score and candidates. CLI prints the canonical client, lists suggestions when ambiguous, and exits 1 when unresolved. 14 new tests (41 total).
- **Client Profile Tool** (2026-11-16): `get_client_profile()` in `src/tools/client_profile.py` fetches a resolved client by exact `client_id` (parameterised, no name/fuzzy matching). `ClientProfile` model in `src/models/profile.py` with all seven fields, `source_table`, `source_primary_key` and data-quality warnings (missing/blank values kept as `None`, invalid `customer_since`, duplicate `client_id` rows). `ClientNotFoundError` for unknown IDs; SQLite errors raised as `DatabaseError`. CLI prints the profile after resolution. Client resolver moved to `src/tools/resolver.py`. 12 new tests (53 total).
