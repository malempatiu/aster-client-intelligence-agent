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
