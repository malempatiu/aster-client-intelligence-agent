# Aster Client Intelligence

A Python CLI prototype for resolving client requests against a read-only SQLite snapshot. The intended product is a cited sales briefing; that end-to-end flow is not implemented yet.

## Run

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --locked
uv run -m src.main --client "Halden Bet" --trigger at_risk
```

`--client` accepts a client name or ID. Supported triggers are `renewal`, `meeting_prep`, `upsell`, and `at_risk`; optional arguments are `--context` and `--request-id`. The CLI validates the request, resolves the client (ambiguous fuzzy matches are suggestions only), and prints the client profile. The database path is resolved from the source tree, so the command does not depend on the working directory.

The current CLI does **not** call an LLM or require an API key. For a future LLM-enabled version, use a placeholder in local setup documentation, never a committed secret, for example `OPENAI_API_KEY=YOUR_API_KEY`.

## Design and status

The runtime flow implemented today is:

1. Pydantic validates and normalizes request fields; `as_of` is fixed at 2026-11-01.
2. Deterministic Python code resolves the client using exact ID/name and normalized matching; fuzzy matches never auto-select.
3. Parameterized SQLite queries read the client profile. The database is opened read-only; missing or invalid values are reported rather than filled in.

A deterministic contract-status tool also exists in `src/tools/contract_status.py`, but it is not connected to the CLI. No model is currently used. In the intended full flow, SQL/Python tools gather evidence and calculate figures; a model would only plan/write from that evidence, while code verifies citations and numbers.

Sample contract-tool output for `C006`:

```json
{
  "tool_name": "get_contract_status",
  "client_id": "C006",
  "as_of": "2026-11-01",
  "current_contract_resolution": "confirmed",
  "current_contract": {
    "contract_id": "K-0010",
    "contract_type": "renewal",
    "status": "active",
    "start_date": "2025-03-01",
    "end_date": "2027-02-28",
    "signed_date": "2025-02-03",
    "term_months": 24,
    "days_until_end": 119,
    "notice_period_days": 60,
    "notice_deadline": "2026-12-30",
    "days_until_notice": 59,
    "auto_renew": "yes",
    "arr_eur": 176000,
    "arr_reconciliation": {
      "header_arr_eur": 176000,
      "line_fees_total_eur": 176000,
      "difference_eur": 0,
      "status": "matched"
    },
    "source_rowids": [
      10,
      46
    ],
    "duplicate_count": 1
  },
  "current_contract_candidates": [],
  "current_products": [
    {
      "line_id": "L-00031",
      "contract_id": "K-0010",
      "product_id": "LIVE_DATA",
      "product_name": "Live Match Data Feed",
      "annual_fee_eur": 96000,
      "included_units_monthly": 4000,
      "overage_rate_eur_per_unit": "6.0",
      "source_rowids": [
        31
      ],
      "product_source_rowids": [
        1
      ]
    },
    {
      "line_id": "L-00032",
      "contract_id": "K-0010",
      "product_id": "STATS_ARCHIVE",
      "product_name": "Historical Stats Archive",
      "annual_fee_eur": 32000,
      "included_units_monthly": 160,
      "overage_rate_eur_per_unit": "50.0",
      "source_rowids": [
        32
      ],
      "product_source_rowids": [
        5
      ]
    },
    {
      "line_id": "L-00033",
      "contract_id": "K-0010",
      "product_id": "WIDGETS",
      "product_name": "Match Visualisation Widgets",
      "annual_fee_eur": 48000,
      "included_units_monthly": 32,
      "overage_rate_eur_per_unit": "300.0",
      "source_rowids": [
        33
      ],
      "product_source_rowids": [
        6
      ]
    }
  ],
  "pending_contracts": [],
  "arr_change_at_last_renewal": {
    "status": "calculated",
    "reason": null,
    "renewal_contract_id": "K-0010",
    "renewal_source_rowids": [
      10,
      46
    ],
    "previous_contract_id": "K-0009",
    "previous_source_rowids": [
      9
    ],
    "renewal_arr_eur": 176000,
    "previous_arr_eur": 168500,
    "change_eur": 7500,
    "change_percentage": "4.45",
    "relationship_basis": "chronological_inference",
    "warning": "No explicit predecessor contract ID exists; predecessor was inferred chronologically."
  },
  "duplicate_summary": {
    "duplicate_contract_ids": [
      "K-0010"
    ],
    "conflicting_contract_ids": [],
    "duplicate_physical_rows": 1
  },
  "warnings": [
    {
      "code": "duplicate_contract_record",
      "severity": "low",
      "table": "contracts",
      "record_id": "K-0010",
      "source_rowids": [
        10,
        46
      ],
      "message": "Contract K-0010 appears in 2 identical rows",
      "recommended_treatment": "Counted once; all rowids retained",
      "details": {}
    }
  ],
  "source_references": [
    {
      "table": "contracts",
      "record_id": "K-0010",
      "source_rowids": [
        10,
        46
      ]
    },
    {
      "table": "contract_lines",
      "record_id": "L-00031",
      "source_rowids": [
        31
      ]
    },
    {
      "table": "products",
      "record_id": "LIVE_DATA",
      "source_rowids": [
        1
      ]
    },
    {
      "table": "contract_lines",
      "record_id": "L-00032",
      "source_rowids": [
        32
      ]
    },
    {
      "table": "products",
      "record_id": "STATS_ARCHIVE",
      "source_rowids": [
        5
      ]
    },
    {
      "table": "contract_lines",
      "record_id": "L-00033",
      "source_rowids": [
        33
      ]
    },
    {
      "table": "products",
      "record_id": "WIDGETS",
      "source_rowids": [
        6
      ]
    },
    {
      "table": "contracts",
      "record_id": "K-0009",
      "source_rowids": [
        9
      ]
    }
  ]
}
```

There are no generated briefing/evidence samples or runtime model prompts in this checkout yet. The coding-tool instructions are in `AGENTS.md`, `docs/AI_INTERACTIONS.md`, and `.claude/skills/feature/`; the latter are workflow guidance, not agent runtime prompts.

## Evaluation

`uv run pytest -q`: **113 passed**. `uv run ruff check .`: **all checks passed**. These are unit and integration tests, including checks against the supplied database. The requested multi-client/multi-trigger briefing evaluation and unsupported-number check have not been implemented or run, so there are no evaluation briefings or evidence files to report yet.

## Assignment status

| Assignment requirement | Current status |
|---|---|
| CLI accepting client and trigger | Done |
| Support all 25 clients | Resolver implemented |
| Support four triggers | Input validation |
| Contract analysis | Implemented |
| Usage trends | Not implemented |
| White-space analysis | Not implemented |
| Support analysis | Not implemented |
| Meeting notes | Not implemented |
| CRM opportunities | Not implemented |
| Trigger-based planner | Missing |
| Orchestration | Missing |
| Evidence JSON | Missing |
| LLM briefing writer | Missing |
| Citation and number verifier | Missing |
| Six evaluation runs | Missing |

## Limitations and next steps

The CLI currently stops after displaying a profile. Usage, whitespace, support, opportunity, and meeting-note analyses; planning/orchestration; briefing generation; citation/number verification; saved evidence, traces, and formal evaluation are still missing. The data is a synthetic snapshot, not live systems.

Next, implement and test the remaining deterministic tools, add config-driven trigger plans and evidence output, then add a grounded writer and independent verifier. Run and report the required evaluation before treating this as production-ready. Production work would also need managed secrets, access controls, operational monitoring, and validation against live integrations.

## How I built it

I built the prototype in small feature slices: request validation, read-only database access, client resolution, profile retrieval, and contract status. The repository's `.claude/skills/feature/` defines a `/feature` workflow with `load`, `start`, `review`, `test`, `explain`, and `complete` actions. It uses `docs/CURRENT_FEATURE.md` to record goals and status; the documented process is to load a spec, implement on a feature branch, review and test, then complete and record the work. `AGENTS.md` and `docs/AI_INTERACTIONS.md` provide the broader coding guidance. Claude permissions allow `uv sync`, deny reading `.env`, and require approval for dependency additions and pushes. The skill is workflow guidance, not a runtime prompt; this project has no configured sub-agents or briefing prompts yet. I used pytest (including temporary databases) and Ruff as checks.