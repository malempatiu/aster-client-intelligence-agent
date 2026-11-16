# Current Feature: CLI Input and Request Validation

<!-- Feature Name -->

## Status

<!-- Not Started|In Progress|Completed -->

In Progress

## Goals

<!-- Goals & requirements -->

- A sales rep can submit a client intelligence request from the command line via `uv run -m src.main`
- CLI built with `argparse`, accepting:
  - `--client` (required): client name or client ID
  - `--trigger` (required): one of `renewal`, `meeting_prep`, `upsell`, `at_risk`
  - `--context` (optional): free-text context from the rep
  - `--request-id` (optional): caller-supplied request ID
- `ClientRequest` Pydantic v2 model in `src/models/requests.py` with fields: `request_id`, `client`, `trigger`, `rep_context`, `as_of`
- Validation rules:
  - `client` is required; empty or whitespace-only values are rejected
  - `client` is trimmed of leading/trailing whitespace
  - `trigger` must be one of the four supported values
  - `rep_context` is optional
  - `request_id` is optional; a unique ID is generated if not supplied
  - `as_of` is fixed to `2026-11-01` and cannot be overridden from the CLI
- CLI behaviour:
  - `--help` shows helpful usage information
  - Validation errors are displayed clearly
  - Missing required arguments exit gracefully (no stack trace)
  - Successful validation is clearly indicated
  - The validated request is printed in a readable format
- All example commands work:
  - `uv run -m src.main --client "Halden Bet" --trigger at_risk`
  - `uv run -m src.main --client C009 --trigger upsell`
  - `uv run -m src.main --client "Corvane Media" --trigger upsell --context "Meeting their head of digital next week"`
  - `uv run -m src.main --client "Halden Bet" --trigger at_risk --request-id R1`

## Notes

<!-- Any extra notes -->

- Spec: `docs/features/cli-input-and-request-validation.md`
- Stack: Python 3.12, argparse, Pydantic v2
- Scope restriction: this feature must ONLY implement CLI input and request validation. No client lookup, data loading, or downstream processing.
- `--request-id` appears in an example command but isn't listed under the spec's optional inputs. It's treated as an optional flag here so the example works.
- The `as_of` reporting date is a fixed constant (2026-11-01) and should not be exposed as a CLI flag.

## History

<!-- Keep this updated. Earliest to latest -->
