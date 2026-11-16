# Contract Status Tool Implementation


## 1. Objective

Implement a deterministic contract and renewal analysis tool for Aster Intelligence.

The tool answers the questions defined in `tool_catalogue.md`:

> Given a `client_id` and `as_of` date, return the contract in force (or none), products, ARR, end date, days to end, notice deadline, auto-renewal status, pending contracts, and ARR change at the last renewal.

The tool must use the supplied SQLite database as its only runtime business-data source. It must not read CSV files, modify the source database, call an LLM, or invent missing values.

**Core rule:** SQL retrieves source records; Python performs deterministic validation and calculations. The LLM is not involved in this tool.

## 2. Tool contract

### 2.1 Input

The public tool interface must accept exactly these business inputs:

| Input | Type | Meaning |
|---|---|---|
| `client_id` | non-empty string | Canonical client ID returned by the client resolver |
| `as_of` | date | Reporting reference date; use `2026-11-01` for this exercise |

The tool must not accept a client name, arbitrary date range, or user-provided ARR value. `as_of` is supplied by application configuration, not typed by the sales representative.

Example:

```text
get_contract_status(client_id="C006", as_of=date(2026, 11, 1))
```

### 2.2 Required output

The result must cover:

1. Contract in force, or an explicit result that none / an ambiguous / an unknown position can be established.
2. Products included in the confirmed current contract.
3. Contract-header ARR and contract-line fee reconciliation.
4. Contract end date and days until end.
5. Notice deadline and days until notice deadline.
6. Auto-renewal status.
7. Pending-signature contracts.
8. ARR change at the latest identifiable signed renewal.
9. Duplicate and data-quality warnings.
10. Source record identifiers and physical row locators where needed.

The result must be structured and validated with Pydantic. Do not return only a prose summary.

## 3. Database and schema facts

Use `data/starter_pack/client_intel.db` through the project's existing read-only SQLite connection utility.

Relevant tables:

- `contracts`
- `contract_lines`
- `products`

The data dictionary describes `contracts.contract_id`, `contract_lines.line_id`, and `products.product_id` as primary keys. However, the supplied SQLite schema has been inspected and the `contracts` table is defined without a `PRIMARY KEY` constraint. Duplicate `contract_id` values therefore exist in the physical table.

Do not assume that a documented primary key is physically enforced. Inspect the actual schemas and duplicate patterns for all three relevant tables before implementing joins or aggregations.

The SQLite columns are stored as `TEXT`, even when the data dictionary describes them as dates, integers, or numeric values. Parse and validate values in Python before using them in business calculations.

### 3.1 Read-only and source preservation

- Open the supplied SQLite database in read-only mode.
- Never `DELETE`, `UPDATE`, `INSERT`, `CREATE`, `ALTER`, or otherwise modify the supplied database.
- Do not clean the source records in place.
- Perform normalisation and deduplication in memory only.
- Use parameterised SQL queries.

## 4. Duplicate-row policy — mandatory

This policy is essential because duplicate contract rows have already been observed in the supplied database.

### 4.1 Preserve physical row identity

For the supplied ordinary SQLite rowid table, retrieve `rowid` together with every contract row. `rowid` is a physical source-row locator, not a replacement business key.

Preserve both:

- `contract_id`: documented logical/business identifier.
- `source_rowids`: physical SQLite row identifiers for the row or duplicate group.

Citations should use the business identifier, for example `[contracts:K-0010]`, and the evidence JSON should also retain the physical `rowid` values for duplicate diagnosis.

Do not claim `rowid` is a permanent identifier across database rebuilds. It is a locator for this supplied, read-only database snapshot.

### 4.2 Normalise rows before comparing them

Create an internal normalisation step. Preserve original raw values for diagnostics, but build a canonical comparison representation:

- Trim surrounding whitespace from text.
- Treat empty strings as missing (`None`) for comparison.
- Normalise status and contract type to lowercase after trimming.
- Normalise `auto_renew` to uppercase after trimming.
- Parse valid ISO dates to Python `date` values.
- Parse integer-valued fields strictly.
- Parse monetary fields using `Decimal` before converting to the documented integer EUR representation.
- Do not silently coerce malformed values to zero.

Use the complete set of business columns from `contracts` when comparing records. Exclude `rowid` from the comparison signature.

### 4.3 Classify duplicate contract IDs

Group physical rows by the trimmed, non-empty `contract_id`.

For each group:

**A. Unique contract ID**

- One physical row exists.
- Treat it as one logical contract, subject to field validation.

**B. Identical / semantically identical duplicates**

- Multiple physical rows have the same `contract_id`.
- Their canonical business-field signatures are identical.
- Treat them as one logical contract for all calculations.
- Preserve every physical `rowid` and the duplicate count.
- Emit a `duplicate_contract_record` warning.
- Never multiply ARR, line totals, products, or renewal comparisons by the number of duplicate physical rows.

**C. Conflicting duplicate contract ID**

- Multiple physical rows have the same `contract_id` but their canonical business-field signatures differ.
- Mark the entire logical contract ID as `conflicting` / ambiguous.
- Do not select the first or latest physical row as authoritative.
- Exclude the conflicted contract from confirmed-current-contract selection, current ARR, product holdings, pending-contract assertions, and ARR predecessor calculations.
- Preserve all candidate rowids and the differing fields in the warning/evidence output.

**D. Missing or blank contract ID**

- Mark the physical row invalid.
- Do not use it as an authoritative contract.
- Preserve its `rowid` and emit a warning.

Do not use `SELECT DISTINCT` as the sole duplicate-handling strategy. It can hide conflicting records and does not preserve diagnostic provenance.

### 4.4 Contract-line duplicates

Inspect whether `contract_lines.line_id` is actually unique in SQLite.

Apply the same conservative logical-record policy to contract lines:

- Identical duplicate rows sharing a `line_id` count once and produce a warning.
- Conflicting rows sharing a `line_id` are ambiguous; exclude that line from fee reconciliation and product details, and flag the affected contract.
- Missing `line_id` rows are invalid and must not silently contribute to line totals.
- Preserve all physical rowids and source `line_id` values.

Do not treat two different line IDs for the same product as duplicates automatically. Multiple genuine lines for one product may exist; retain them separately unless the data dictionary or verified business rule says otherwise.

### 4.5 Avoid join multiplication

Do not join raw duplicate contract headers directly to contract lines and then aggregate. That can multiply line fees and ARR.

Recommended approach:

1. Fetch physical contract rows, including `rowid`.
2. Normalise and classify contract duplicates in Python.
3. Produce one clean logical contract record per non-conflicting `contract_id`.
4. Fetch contract lines separately, including `rowid`.
5. Normalise and classify line duplicates.
6. Fetch product catalogue records and validate product IDs.
7. Assemble contract, line, and product records in Python using validated logical identifiers.

A carefully constructed SQL approach is acceptable only if it gives the same results and preserves duplicate diagnostics without multiplying records.

## 5. Normalised internal data model

Keep raw SQLite rows separate from clean internal records. Do not pass unvalidated TEXT values directly into calculations.

Create Pydantic models (or equivalent typed models) for the following internal structures.

### 5.1 `NormalisedContract`

Suggested fields:

| Field | Type | Notes |
|---|---|---|
| `contract_id` | `str` | Non-empty logical identifier |
| `client_id` | `str` | Canonical client ID |
| `contract_type` | enum/string | Normalised `new` or `renewal`; unknown values flagged |
| `start_date` | `date | None` | Strict ISO parse |
| `end_date` | `date | None` | Strict ISO parse |
| `term_months` | `int | None` | Strict integer parse |
| `auto_renew` | `Y / N / None` | Unknown/invalid values flagged |
| `notice_period_days` | `int | None` | Strict non-negative integer |
| `arr_eur` | `int | None` | Strict integer EUR; invalid values remain unavailable |
| `currency` | `str | None` | Expected `EUR` |
| `status` | enum/string | `active`, `expired`, `pending_signature`, or unknown |
| `signed_date` | `date | None` | Strict ISO parse |
| `source_rowids` | `list[int]` | All physical rows represented |
| `duplicate_count` | `int` | Number of extra physical rows; zero for unique row |
| `record_integrity` | enum | `clean`, `identical_duplicate`, `conflicting`, `invalid` |

### 5.2 `NormalisedContractLine`

Suggested fields:

| Field | Type | Notes |
|---|---|---|
| `line_id` | `str` | Logical line identifier |
| `contract_id` | `str` | Parent logical contract ID |
| `product_id` | `str` | Product catalogue identifier |
| `annual_fee_eur` | `int | None` | Strict integer EUR |
| `included_units_monthly` | `int | None` | Strict numeric/integer value per dictionary |
| `overage_rate_eur_per_unit` | `Decimal | None` | Preserve precision |
| `source_rowids` | `list[int]` | Physical source rows |
| `duplicate_count` | `int` | Extra physical rows |
| `record_integrity` | enum | `clean`, `identical_duplicate`, `conflicting`, `invalid` |

### 5.3 Clean-data rules

- Do not replace invalid or missing numeric fields with zero.
- Do not replace missing dates with `as_of`.
- Do not infer `auto_renew = N` from a blank value.
- Do not infer contract status from dates when the stored status conflicts.
- Retain the original raw values in diagnostic details where practical.
- Use Python `date` objects internally and ISO `YYYY-MM-DD` strings in JSON output.
- Use integer EUR for documented integer money fields and `Decimal` for rates/calculation intermediates.
- All calculations must identify when they are unavailable and why.

## 6. Business rules and formulas

All date calculations use the supplied `as_of` argument. For this exercise, it is `2026-11-01`. Do not use the machine's current date.

### 6.1 Confirmed contract in force

A clean, non-conflicting logical contract is confirmed in force only when all conditions hold:

```text
normalised status == "active"
signed_date is present and valid
signed_date <= as_of
start_date is valid and start_date <= as_of
end_date is valid and end_date >= as_of
```

Start and end dates are inclusive.

Equivalent date condition:

```text
start_date <= as_of <= end_date
```

A `pending_signature` contract is never in force.

Do not mark a contract confirmed if its required dates or signed date are missing or invalid. Report the uncertainty as a warning.

### 6.2 Current-contract resolution status

Return one of these values:

- `confirmed`: exactly one clean logical contract qualifies, with no unresolved competing record that could change the conclusion.
- `none`: no contract qualifies and there are no unresolved records that could plausibly be in force.
- `ambiguous`: more than one clean logical contract qualifies as in force.
- `unknown`: conflicting duplicate IDs, invalid critical fields, or contradictory records prevent a reliable conclusion.

Only populate `current_contract` when status is `confirmed`.

When status is `ambiguous` or `unknown`, return `current_contract: null`, preserve qualifying candidates in `current_contract_candidates`, and explain the reason in warnings. Do not pick one silently.

### 6.3 Contract products

For a confirmed current contract, include its clean, non-conflicting contract lines and product catalogue details.

Each product-line output must retain:

- `line_id`
- `contract_id`
- `product_id`
- `product_name` when uniquely resolvable
- `annual_fee_eur`
- `included_units_monthly`
- `overage_rate_eur_per_unit`
- source references for the line and product

Do not include products from pending-signature contracts as current holdings.

If a contract line references an unknown or conflicting product catalogue record, retain the `product_id`, set unresolved descriptive fields to null, and emit a warning. Do not allow duplicate product catalogue rows to multiply contract lines.

If current-contract resolution is ambiguous or unknown, `current_products` must be `null` rather than an empty list that could be misread as “no products”. If a contract is confirmed and has no valid lines, return an empty list and an appropriate warning.

### 6.4 Contract-header ARR

For a confirmed current contract:

```text
current_arr_eur = contracts.arr_eur
```

This is the recorded contract-header ARR and is the authoritative reported contractual ARR for this tool.

### 6.5 Contract-line fee total and ARR reconciliation

For a contract with fully usable, uniquely identified lines:

```text
line_fees_total_eur = SUM(unique valid contract_lines.annual_fee_eur)
arr_difference_eur = header_arr_eur - line_fees_total_eur
```

Set reconciliation status:

- `matched` when difference is zero.
- `mismatch` when difference is non-zero.
- `unavailable` if header ARR, one or more relevant line fees, or line integrity is insufficient to calculate a trustworthy total.

Do not substitute the line-fee total for header ARR. Do not sum a duplicate physical line more than once. If a line ID is conflicting, the total is unavailable rather than silently omitting the conflict and claiming a complete reconciliation.

### 6.6 Contract end date

Retrieve the contract's valid `end_date`. Do not derive or invent it.

### 6.7 Days until contract end

```text
days_until_end = (end_date - as_of).days
```

Interpretation:

- Positive: the end date is in the future.
- Zero: the contract ends on `as_of` and is still in force on that inclusive final day.
- Negative: the end date is before `as_of`.

Do not add one to the date difference.

### 6.8 Notice deadline

When `end_date` and a valid non-negative `notice_period_days` are available:

```text
notice_deadline = end_date - timedelta(days=notice_period_days)
days_until_notice = (notice_deadline - as_of).days
```

Interpretation:

- Positive: upcoming.
- Zero: due on `as_of`.
- Negative: passed.

Do not add or subtract an extra day beyond the stated formula. If the notice period is missing or invalid, return null and a warning.

### 6.9 Auto-renewal

Retrieve and normalise `auto_renew`:

- `Y` -> `yes`
- `N` -> `no`
- blank, null, or any other value -> `unknown` plus warning

Do not infer this value from contract type, status, or CRM.

### 6.10 Pending-signature contracts

Return clean, unique logical contracts where normalised status is `pending_signature`, separately from current contracts.

They are not in force and must not contribute to current ARR or current product holdings.

If a pending-signature row has a populated or invalid `signed_date`, retain it in the pending/exception output with an inconsistency warning; do not describe it as a clean pending contract without qualification.

### 6.11 ARR change at the latest signed renewal

There is no explicit predecessor-contract foreign key in the supplied contract schema. Therefore, any predecessor match is a documented chronological inference, not a guaranteed relationship.

Use this conservative procedure:

1. Consider only clean, non-conflicting logical contracts for this client.
2. Find renewal contracts with `contract_type = renewal`, a valid `signed_date`, and `signed_date <= as_of`.
3. Exclude pending-signature contracts. A renewal candidate must be a signed historical/current contract with a valid header ARR and dates.
4. Select the latest renewal by `signed_date`. If more than one distinct renewal shares the latest signed date and cannot be disambiguated, return the comparison as unavailable/ambiguous.
5. Find eligible preceding signed contracts for the same client with valid ARR and `previous.end_date < renewal.start_date` and `previous.signed_date < renewal.signed_date`.
6. Select the eligible predecessor with the latest `end_date` (the nearest non-overlapping predecessor).
7. If multiple distinct predecessors share the same latest end date, return unavailable/ambiguous.
8. If no predecessor exists, return unavailable with a reason.
9. Preserve the fact that the link is inferred chronologically because no explicit predecessor ID exists.

When both ARR values are valid:

```text
arr_change_eur = renewal_arr_eur - previous_arr_eur
```

If `previous_arr_eur != 0`:

```text
arr_change_percentage = (arr_change_eur / previous_arr_eur) * 100
```

If previous ARR is zero, return the absolute change but set percentage change to null and explain that division by zero is undefined.

Use `Decimal` for percentage calculation and round only for presentation (recommended: two decimal places). Do not round source ARR values.

Return an explicit basis such as `chronological_inference` and a warning that the dataset has no explicit predecessor relationship.

## 7. Data-quality warnings

Warnings must be structured, not only prose. Each warning should include:

- `code`
- `severity` (`low`, `medium`, `high`)
- `table`
- `record_id` where available
- `source_rowids` where available
- `message`
- `impact` or `recommended_treatment`

At minimum, handle these warning codes:

- `duplicate_contract_record`
- `conflicting_contract_id`
- `missing_contract_id`
- `invalid_contract_date`
- `missing_signed_date`
- `signed_date_after_as_of`
- `contract_status_date_conflict`
- `unknown_contract_status`
- `invalid_arr_value`
- `arr_line_fee_mismatch`
- `contract_line_duplicate`
- `conflicting_contract_line_id`
- `missing_contract_line_id`
- `orphan_contract_line`
- `unknown_product_id`
- `missing_notice_period`
- `invalid_auto_renew_value`
- `multiple_contracts_in_force`
- `renewal_predecessor_unavailable`
- `renewal_predecessor_ambiguous`

Do not report every missing optional field as a critical error. Severity should reflect its impact on the tool's conclusions.

## 8. Required clean output model

Create Pydantic v2 models. Use clear enums/literals and typed nested structures rather than an unstructured dictionary.

The public result should have the following shape (field names may be adapted to existing project conventions, but preserve the semantics).

```json
{
  "tool_name": "get_contract_status",
  "client_id": "C006",
  "as_of": "2026-11-01",
  "current_contract_resolution": "confirmed",
  "current_contract": {
    "contract_id": "K-0010",
    "contract_type": "new",
    "status": "active",
    "start_date": "2025-03-01",
    "end_date": "2027-02-28",
    "signed_date": "2025-02-03",
    "term_months": 24,
    "days_until_end": 119,
    "notice_period_days": 90,
    "notice_deadline": "2026-11-30",
    "days_until_notice": 29,
    "auto_renew": "yes",
    "arr_eur": 176000,
    "arr_reconciliation": {
      "header_arr_eur": 176000,
      "line_fees_total_eur": 176000,
      "difference_eur": 0,
      "status": "matched"
    },
    "products": [
      {
        "line_id": "L-00012",
        "product_id": "LIVE_DATA",
        "product_name": "Example product",
        "annual_fee_eur": 176000,
        "included_units_monthly": 1000000,
        "overage_rate_eur_per_unit": "0.01",
        "source_rowids": [12]
      }
    ],
    "source_rowids": [10, 11],
    "duplicate_count": 1
  },
  "current_contract_candidates": [],
  "current_products": [],
  "pending_contracts": [],
  "arr_change_at_last_renewal": {
    "status": "calculated",
    "previous_contract_id": "K-0008",
    "renewal_contract_id": "K-0010",
    "previous_arr_eur": 160000,
    "renewal_arr_eur": 176000,
    "change_eur": 16000,
    "change_percentage": "10.00",
    "relationship_basis": "chronological_inference",
    "warning": "No explicit predecessor contract ID exists; predecessor was inferred chronologically."
  },
  "duplicate_summary": {
    "duplicate_contract_ids": ["K-0010"],
    "conflicting_contract_ids": [],
    "duplicate_physical_rows": 1
  },
  "warnings": [],
  "source_references": [
    {
      "table": "contracts",
      "record_id": "K-0010",
      "source_rowids": [10, 11]
    },
    {
      "table": "contract_lines",
      "record_id": "L-00012",
      "source_rowids": [12]
    },
    {
      "table": "products",
      "record_id": "LIVE_DATA",
      "source_rowids": [1]
    }
  ]
}
```

**Important:** All values in the JSON example are illustrative. Do not copy these example client, contract, line, product, ARR, or rowid values into implementation logic. Use actual database values.

### 8.1 Model semantics

Recommended top-level models:

- `ContractStatusResult`
- `ContractSummary`
- `ContractProductLine`
- `ARRReconciliation`
- `ARRChangeAtLastRenewal`
- `DuplicateSummary`
- `ContractDataQualityWarning`
- `SourceReference`

Use nullable fields when a value cannot be established. Do not use zero, empty string, or an empty list to mean “unknown”.

`current_contract_resolution` must be one of `confirmed`, `none`, `ambiguous`, or `unknown`.

- `current_contract` is populated only when resolution is `confirmed`.
- `current_contract_candidates` lists valid qualifying candidates when there are multiple.
- `current_products` is `null` when current-contract resolution is ambiguous/unknown, and an empty list only when a uniquely confirmed contract has no usable product lines.
- `pending_contracts` is a list of separately identified non-current contracts; inconsistent pending records must carry warnings.
- `arr_change_at_last_renewal.status` should distinguish `calculated`, `unavailable`, and `ambiguous`.

The exact nested layout may follow existing Pydantic conventions, but these distinctions must be preserved.

## 9. Citation and evidence requirements

The tool itself must not write a narrative briefing, but its output must support later citations.

Preserve:

- `contract_id` for contract citations, e.g. `[contracts:K-0010]`.
- `line_id` for line citations, e.g. `[contract_lines:L-00012]`.
- `product_id` for catalogue citations, e.g. `[products:LIVE_DATA]`.
- `source_rowids` for physical duplicate diagnosis.

Every calculated result must include its method/period/inputs or have enough structured provenance for the evidence aggregator to record them.

Do not cite a calculated value only to an ID without retaining the tool output and the source row IDs used to calculate it.

## 10. Testing requirements

Use pytest and temporary SQLite databases for controlled tests. Never mutate the supplied starter database during tests.

### 10.1 Contract classification tests

- One clean active contract satisfying all conditions -> `confirmed`.
- Active contract with `end_date == as_of` -> in force.
- Active contract with `start_date == as_of` -> in force.
- Active contract with `start_date > as_of` -> not in force; warning if status conflicts.
- Active contract with `end_date < as_of` -> not in force; status/date warning.
- Active contract with missing/invalid signed date -> not confirmed; unknown if current status cannot be established.
- Signed date after `as_of` -> not confirmed; warning.
- Expired contract -> not in force.
- Expired status with future end date -> conflict warning.
- Pending-signature contract -> not in force and appears separately.
- Pending-signature with populated signed date -> inconsistency warning.
- No contracts -> resolution `none`.
- Multiple valid current contracts -> resolution `ambiguous`.
- Conflicting duplicate rows that could affect current status -> resolution `unknown`.

### 10.2 Duplicate tests

- Single contract row.
- Two exact physical duplicate rows with same `contract_id`.
- Semantically identical values with harmless surrounding whitespace.
- Same `contract_id` with different ARR.
- Same `contract_id` with different dates/status.
- Missing/blank contract ID.
- Duplicate line ID with identical rows.
- Duplicate line ID with conflicting values.
- Orphan contract line.
- Confirm duplicate physical rows do not double-count ARR or line fees.
- Confirm all physical rowids are retained in warnings/source references.

### 10.3 Calculation tests

- Days until end for future, today, and past dates.
- Notice deadline calculation.
- Days until notice positive, zero, and negative.
- Header ARR equals line total.
- Header ARR differs from line total.
- Missing ARR.
- Invalid ARR.
- Missing/invalid fee.
- Conflicting line prevents trustworthy reconciliation.
- Auto-renew `Y`, `N`, blank, and invalid value.

### 10.4 ARR renewal tests

- Renewal with one clear preceding signed contract.
- ARR increase.
- ARR decrease.
- No predecessor.
- Multiple possible predecessors with same nearest end date.
- Multiple latest renewals sharing a signed date.
- Conflicting duplicate renewal contract.
- Missing or invalid ARR.
- Previous ARR equal to zero.
- Ensure identical duplicate physical rows do not create duplicate predecessors.
- Ensure the output states chronological inference because no explicit predecessor link exists.

### 10.5 Integration tests

Against the supplied read-only database:

- Run `get_contract_status` for at least two clients, including `C006` (which has a known duplicate `K-0010` in the supplied inspection).
- Verify actual returned source IDs and rowids.
- Confirm no source database changes occur.
- Compare selected values against independent SQL queries.

## 11. Independent verification procedure

Do not treat passing unit tests as proof by themselves. For at least one real client, independently verify the result with SQL.

Useful inspection queries:

```sql
-- Inspect all physical rows for a contract ID.
SELECT rowid, *
FROM contracts
WHERE contract_id = 'K-0010';
```

```sql
-- Find duplicate logical contract IDs.
SELECT contract_id, COUNT(*) AS physical_rows
FROM contracts
WHERE contract_id IS NOT NULL AND TRIM(contract_id) <> ''
GROUP BY TRIM(contract_id)
HAVING COUNT(*) > 1;
```

```sql
-- Inspect a client's contract history.
SELECT rowid, contract_id, client_id, contract_type,
       start_date, end_date, signed_date, arr_eur,
       auto_renew, notice_period_days, status
FROM contracts
WHERE client_id = 'C006'
ORDER BY start_date, signed_date;
```

```sql
-- Inspect contract-line rows for a logical contract.
SELECT rowid, *
FROM contract_lines
WHERE contract_id = 'K-0010';
```

When comparing totals, first account for duplicate and conflicting logical IDs. Do not join raw duplicated headers to lines and then SUM fees.

## 12. Scope boundaries

This feature must implement only `get_contract_status` and the models/helpers it needs.

Do not implement:

- Usage trend analysis.
- Support analysis.
- CRM opportunity analysis.
- White-space analysis.
- Meeting-note retrieval or interpretation.
- Planner.
- Orchestrator.
- LLM briefing writer.
- Final briefing verification.
- UI or deployment functionality.

Do not change the public tool inputs from `client_id` and `as_of`.

## 13. Definition of done

The feature is complete only when:

- [ ] Public tool input is exactly `client_id` and `as_of`.
- [ ] All output requirements from the tool catalogue are represented in a clean Pydantic model.
- [ ] SQLite is read-only and is the only runtime data source.
- [ ] All TEXT date/numeric/status values are validated before use.
- [ ] Duplicate contract headers are detected and classified.
- [ ] Exact duplicates count once for calculations and preserve all physical rowids.
- [ ] Conflicting duplicate IDs are never silently resolved.
- [ ] Contract-line duplicates are detected and cannot multiply totals.
- [ ] All formulas in Section 6 are implemented and tested.
- [ ] Pending contracts are separate from current contracts and ARR.
- [ ] ARR reconciliation is transparent.
- [ ] ARR renewal comparison is labelled as chronological inference.
- [ ] Source identifiers and physical row locators are preserved.
- [ ] Warnings are structured and included in the output.
- [ ] Unit and integration tests pass.
- [ ] Ruff checks pass.
- [ ] At least one real database result is independently checked with SQL.
- [ ] The original database remains unchanged.

## 14. Instructions to Claude 

1. Read `AGENTS.md`, `TECH_STACK.md`, the `starter_pack\data_dictionary.md`, the `starter_pack\data_dictionary.md`, and this specification before implementation.
2. Inspect the actual schemas for `contracts`, `contract_lines`, and `products`; do not assume declared primary keys are enforced.
3. First present a short implementation plan and identify any ambiguity in the real data.
4. Implement only this feature.
5. Keep raw-row retrieval, normalisation, duplicate classification, business calculations, and output construction as separately testable functions.
6. Do not hardcode any client ID, contract ID, ARR value, expected output, or rowid from the examples in this document.
7. Do not modify the supplied SQLite database or use CSV files.
8. Add tests alongside implementation, including duplicates and conflicts.
9. Run pytest and Ruff.
10. Independently verify at least one real result against SQL.
11. Report files changed, tests run, results, assumptions, and remaining limitations.
12. Do not begin another feature until this implementation has been reviewed.

**Engineering principle:** Preserve every source row for auditability, but only allow unambiguous logical records to contribute to commercial calculations.
