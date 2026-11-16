"""Contract status for one client: contract in force, products, ARR and renewal position.

SQL returns physical rows. Python normalises them, classifies duplicates, resolves the
contract in force and performs every calculation. The database is opened read-only.
"""

import re
import sqlite3
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from src.database import DB_PATH, DatabaseError, connect
from src.models.contract_status import (
    ARRChangeAtLastRenewal,
    ARRReconciliation,
    AutoRenew,
    ContractDataQualityWarning,
    ContractProductLine,
    ContractStatusResult,
    ContractStatusValue,
    ContractSummary,
    ContractTypeValue,
    DuplicateSummary,
    PendingContract,
    Resolution,
    Severity,
    SourceReference,
)
from src.models.requests import AS_OF

CONTRACT_COLUMNS = (
    "contract_id",
    "client_id",
    "contract_type",
    "start_date",
    "end_date",
    "term_months",
    "auto_renew",
    "notice_period_days",
    "arr_eur",
    "currency",
    "status",
    "signed_date",
)
LINE_COLUMNS = (
    "line_id",
    "contract_id",
    "product_id",
    "annual_fee_eur",
    "included_units_monthly",
    "overage_rate_eur_per_unit",
)
SIGNED_STATUSES: tuple[ContractStatusValue, ...] = ("active", "expired")
CONTRACT_TYPE_VALUES: dict[str, ContractTypeValue] = {"new": "new", "renewal": "renewal"}
CONTRACT_STATUS_VALUES: dict[str, ContractStatusValue] = {
    "active": "active",
    "expired": "expired",
    "pending_signature": "pending_signature",
}
AUTO_RENEW_VALUES: dict[str, Literal["yes", "no"]] = {"Y": "yes", "N": "no"}
CHRONOLOGICAL_WARNING = "No explicit predecessor contract ID exists; predecessor was inferred chronologically."
UNAVAILABLE_TREATMENT = "Value left unavailable and not replaced with a default"

FIELD_CODES = {
    "start_date": "invalid_contract_date",
    "end_date": "invalid_contract_date",
    "signed_date": "invalid_contract_date",
    "status": "unknown_contract_status",
    "contract_type": "unknown_contract_type",
    "arr_eur": "invalid_arr_value",
    "auto_renew": "invalid_auto_renew_value",
    "notice_period_days": "missing_notice_period",
}
SEVERITY: dict[str, Severity] = {
    "missing_contract_id": "medium",
    "conflicting_contract_id": "high",
    "duplicate_contract_record": "low",
    "invalid_contract_date": "high",
    "missing_signed_date": "medium",
    "signed_date_after_as_of": "high",
    "contract_status_date_conflict": "high",
    "unknown_contract_status": "high",
    "unknown_contract_type": "low",
    "invalid_arr_value": "medium",
    "invalid_auto_renew_value": "medium",
    "missing_notice_period": "medium",
    "arr_line_fee_mismatch": "high",
    "missing_contract_lines": "medium",
    "contract_line_duplicate": "low",
    "conflicting_contract_line_id": "high",
    "missing_contract_line_id": "medium",
    "invalid_line_value": "medium",
    "unknown_product_id": "medium",
    "conflicting_product_id": "medium",
    "multiple_contracts_in_force": "high",
    "renewal_predecessor_unavailable": "medium",
    "renewal_predecessor_ambiguous": "high",
    "renewal_contract_ambiguous": "high",
}

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
INTEGER = re.compile(r"\d+")
DECIMAL = re.compile(r"\d+(\.\d+)?")


@dataclass
class NormalisedContract:
    rowid: int
    raw: dict[str, str | None]
    canonical: dict[str, str | None]
    issues: dict[str, str]
    contract_id: str | None
    client_id: str | None
    contract_type: ContractTypeValue | None
    start_date: date | None
    end_date: date | None
    term_months: int | None
    auto_renew: AutoRenew
    notice_period_days: int | None
    arr_eur: int | None
    status: ContractStatusValue | None
    signed_date: date | None

    @property
    def key(self) -> str | None:
        return self.contract_id


@dataclass
class NormalisedLine:
    rowid: int
    raw: dict[str, str | None]
    canonical: dict[str, str | None]
    issues: dict[str, str]
    line_id: str | None
    contract_id: str | None
    product_id: str | None
    annual_fee_eur: int | None
    included_units_monthly: int | None
    overage_rate_eur_per_unit: Decimal | None

    @property
    def key(self) -> str | None:
        return self.line_id


KeyedIntegrity = Literal["clean", "identical_duplicate", "conflicting"]


@dataclass
class Logical[T: (NormalisedContract, NormalisedLine)]:
    """One logical record: a key shared by one or more physical rows, and how those rows relate."""

    key: str
    rows: list[T]
    integrity: KeyedIntegrity

    @property
    def record(self) -> T:
        return self.rows[0]

    @property
    def source_rowids(self) -> list[int]:
        return [row.rowid for row in self.rows]

    @property
    def duplicate_count(self) -> int:
        return len(self.rows) - 1


# Raw retrieval


def fetch_contract_rows(
    conn: sqlite3.Connection, client_id: str
) -> list[tuple[int, dict[str, str | None]]]:
    """Physical contract rows for the client, plus any rows sharing a contract ID with them."""
    columns = ", ".join(CONTRACT_COLUMNS)
    rows = conn.execute(
        f"""SELECT rowid, {columns} FROM contracts
            WHERE TRIM(client_id) = :client_id
               OR TRIM(contract_id) IN (
                   SELECT TRIM(contract_id) FROM contracts WHERE TRIM(client_id) = :client_id)
            ORDER BY rowid""",
        {"client_id": client_id},
    )
    return [
        (row["rowid"], {column: row[column] for column in CONTRACT_COLUMNS})
        for row in rows
    ]


def fetch_line_rows(
    conn: sqlite3.Connection, contract_ids: list[str]
) -> list[tuple[int, dict[str, str | None]]]:
    if not contract_ids:
        return []
    columns = ", ".join(LINE_COLUMNS)
    placeholders = ",".join("?" for _ in contract_ids)
    rows = conn.execute(
        f"SELECT rowid, {columns} FROM contract_lines WHERE TRIM(contract_id) IN ({placeholders}) ORDER BY rowid",
        contract_ids,
    )
    return [
        (row["rowid"], {column: row[column] for column in LINE_COLUMNS}) for row in rows
    ]


def fetch_catalogue(
    conn: sqlite3.Connection, product_ids: set[str]
) -> dict[str, list[tuple[int, str | None]]]:
    if not product_ids:
        return {}
    placeholders = ",".join("?" for _ in product_ids)
    rows = conn.execute(
        f"""SELECT rowid, TRIM(product_id) AS product_id, TRIM(product_name) AS product_name
            FROM products WHERE TRIM(product_id) IN ({placeholders}) ORDER BY rowid""",
        sorted(product_ids),
    )
    catalogue: dict[str, list[tuple[int, str | None]]] = defaultdict(list)
    for row in rows:
        catalogue[row["product_id"]].append((row["rowid"], row["product_name"] or None))
    return catalogue


# Normalisation


def canonical(column: str, value: str | None) -> str | None:
    if value is None or not (text := str(value).strip()):
        return None
    if column in ("status", "contract_type"):
        return text.lower()
    if column == "auto_renew":
        return text.upper()
    return text


def parse_date(text: str) -> date | None:
    if not ISO_DATE.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def parse_int(text: str) -> int | None:
    return int(text) if INTEGER.fullmatch(text) else None


def parse_decimal(text: str) -> Decimal | None:
    return Decimal(text) if DECIMAL.fullmatch(text) else None


def parse_field(
    canon: dict[str, str | None],
    column: str,
    parse: Callable[[str], Any],
    issues: dict[str, str],
) -> Any:
    """Parse one canonical value. Missing and invalid values become None and are recorded in issues."""
    text = canon[column]
    if text is None:
        issues[column] = "missing"
        return None
    value = parse(text)
    if value is None:
        issues[column] = "invalid"
    return value


def normalise_contract(raw: dict[str, str | None], rowid: int) -> NormalisedContract:
    canon = {column: canonical(column, raw[column]) for column in CONTRACT_COLUMNS}
    issues: dict[str, str] = {}

    def field(column: str, parse: Callable[[str], Any]) -> Any:
        return parse_field(canon, column, parse, issues)

    return NormalisedContract(
        rowid=rowid,
        raw=raw,
        canonical=canon,
        issues=issues,
        contract_id=field("contract_id", str),
        client_id=field("client_id", str),
        contract_type=field("contract_type", CONTRACT_TYPE_VALUES.get),
        start_date=field("start_date", parse_date),
        end_date=field("end_date", parse_date),
        term_months=field("term_months", parse_int),
        auto_renew=field("auto_renew", AUTO_RENEW_VALUES.get) or "unknown",
        notice_period_days=field("notice_period_days", parse_int),
        arr_eur=field("arr_eur", parse_int),
        status=field("status", CONTRACT_STATUS_VALUES.get),
        signed_date=field("signed_date", parse_date),
    )


def normalise_line(raw: dict[str, str | None], rowid: int) -> NormalisedLine:
    canon = {column: canonical(column, raw[column]) for column in LINE_COLUMNS}
    issues: dict[str, str] = {}

    def field(column: str, parse: Callable[[str], Any]) -> Any:
        return parse_field(canon, column, parse, issues)

    return NormalisedLine(
        rowid=rowid,
        raw=raw,
        canonical=canon,
        issues=issues,
        line_id=field("line_id", str),
        contract_id=field("contract_id", str),
        product_id=field("product_id", str),
        annual_fee_eur=field("annual_fee_eur", parse_int),
        included_units_monthly=field("included_units_monthly", parse_int),
        overage_rate_eur_per_unit=field("overage_rate_eur_per_unit", parse_decimal),
    )


# Duplicate classification


def classify_rows[T: (NormalisedContract, NormalisedLine)](
    rows: list[T],
) -> tuple[list[Logical[T]], list[T]]:
    """Group rows by key. Rows with no key are returned separately: they are never authoritative."""
    groups: dict[str, list[T]] = {}
    invalid: list[T] = []
    for row in rows:
        key = row.key
        if key is None:
            invalid.append(row)
        else:
            groups.setdefault(key, []).append(row)

    logical: list[Logical[T]] = []
    for key, group in groups.items():
        integrity: KeyedIntegrity
        if len(group) == 1:
            integrity = "clean"
        elif all(row.canonical == group[0].canonical for row in group):
            integrity = "identical_duplicate"
        else:
            integrity = "conflicting"
        logical.append(Logical(key, group, integrity))
    return logical, invalid


def differing_fields[T: (NormalisedContract, NormalisedLine)](
    rows: list[T], columns: tuple[str, ...]
) -> list[str]:
    return [
        column for column in columns if len({row.canonical[column] for row in rows}) > 1
    ]


# Warnings


def warn(
    warnings: list[ContractDataQualityWarning],
    code: str,
    table: str,
    message: str,
    treatment: str,
    record_id: str | None = None,
    rowids: list[int] | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    warnings.append(
        ContractDataQualityWarning(
            code=code,
            severity=SEVERITY[code],
            table=table,
            record_id=record_id,
            source_rowids=rowids or [],
            message=message,
            recommended_treatment=treatment,
            details=details or {},
        )
    )


def contract_warnings(
    lc: Logical[NormalisedContract],
    as_of: date,
    warnings: list[ContractDataQualityWarning],
) -> None:
    if lc.integrity == "conflicting":
        differing = differing_fields(lc.rows, CONTRACT_COLUMNS)
        warn(
            warnings,
            "conflicting_contract_id",
            "contracts",
            f"Contract {lc.key} has {len(lc.rows)} rows with different values in {', '.join(differing)}",
            "Excluded from current, pending and renewal calculations; not resolved automatically",
            record_id=lc.key,
            rowids=lc.source_rowids,
            details={
                "differing_fields": differing,
                "candidates": [
                    {"rowid": r.rowid, "values": {f: r.raw[f] for f in differing}}
                    for r in lc.rows
                ],
            },
        )
        return

    row = lc.record
    if lc.integrity == "identical_duplicate":
        warn(
            warnings,
            "duplicate_contract_record",
            "contracts",
            f"Contract {lc.key} appears in {len(lc.rows)} identical rows",
            "Counted once; all rowids retained",
            record_id=lc.key,
            rowids=lc.source_rowids,
        )
    for column, problem in row.issues.items():
        if column == "signed_date" and problem == "missing":
            if row.status != "pending_signature":
                warn(
                    warnings,
                    "missing_signed_date",
                    "contracts",
                    f"Contract {lc.key} has no signed_date",
                    "Not confirmed as in force",
                    record_id=lc.key,
                    rowids=[row.rowid],
                )
        elif column in FIELD_CODES:
            warn(
                warnings,
                FIELD_CODES[column],
                "contracts",
                f"{column} is {problem} (raw value: {row.raw[column]!r})",
                UNAVAILABLE_TREATMENT,
                record_id=lc.key,
                rowids=[row.rowid],
            )
    status_date_warnings(row, as_of, warnings)


def invalid_contract_warnings(
    row: NormalisedContract, warnings: list[ContractDataQualityWarning]
) -> None:
    warn(
        warnings,
        "missing_contract_id",
        "contracts",
        f"Row {row.rowid} has no contract_id",
        "Not used as an authoritative contract; treated as unresolved",
        rowids=[row.rowid],
    )


def status_date_warnings(
    row: NormalisedContract, as_of: date, warnings: list[ContractDataQualityWarning]
) -> None:
    if row.signed_date is not None and row.signed_date > as_of:
        warn(
            warnings,
            "signed_date_after_as_of",
            "contracts",
            f"Contract {row.contract_id} was signed {row.signed_date}, after as_of {as_of}",
            "Not in force as of as_of",
            record_id=row.contract_id,
            rowids=[row.rowid],
        )
    dates_outside_as_of = (row.end_date is not None and row.end_date < as_of) or (
        row.start_date is not None and row.start_date > as_of
    )
    conflict = None
    if row.status == "active" and dates_outside_as_of:
        conflict = "status is active but the contract dates do not cover as_of"
    elif row.status == "expired" and row.end_date is not None and row.end_date >= as_of:
        conflict = "status is expired but end_date is on or after as_of"
    elif row.status == "pending_signature" and row.canonical["signed_date"] is not None:
        conflict = f"status is pending_signature but signed_date is populated ({row.canonical['signed_date']})"
    if conflict:
        warn(
            warnings,
            "contract_status_date_conflict",
            "contracts",
            f"Contract {row.contract_id}: {conflict}",
            "Stored status is kept; contract not treated as in force on dates alone",
            record_id=row.contract_id,
            rowids=[row.rowid],
        )


def line_warnings(
    ll: Logical[NormalisedLine], warnings: list[ContractDataQualityWarning]
) -> None:
    if ll.integrity == "conflicting":
        differing = differing_fields(ll.rows, LINE_COLUMNS)
        warn(
            warnings,
            "conflicting_contract_line_id",
            "contract_lines",
            f"Line {ll.key} has {len(ll.rows)} rows with different values in {', '.join(differing)}",
            "Excluded from products and fee totals; parent contract reconciliation unavailable",
            record_id=ll.key,
            rowids=ll.source_rowids,
            details={
                "differing_fields": differing,
                "candidates": [
                    {"rowid": r.rowid, "values": {f: r.raw[f] for f in differing}}
                    for r in ll.rows
                ],
            },
        )
        return

    row = ll.record
    if ll.integrity == "identical_duplicate":
        warn(
            warnings,
            "contract_line_duplicate",
            "contract_lines",
            f"Line {ll.key} appears in {len(ll.rows)} identical rows",
            "Counted once; all rowids retained",
            record_id=ll.key,
            rowids=ll.source_rowids,
        )
    for column, problem in row.issues.items():
        warn(
            warnings,
            "invalid_line_value",
            "contract_lines",
            f"{column} is {problem} (raw value: {row.raw[column]!r})",
            UNAVAILABLE_TREATMENT,
            record_id=ll.key,
            rowids=[row.rowid],
        )


def invalid_line_warnings(
    row: NormalisedLine, warnings: list[ContractDataQualityWarning]
) -> None:
    warn(
        warnings,
        "missing_contract_line_id",
        "contract_lines",
        f"Row {row.rowid} has no line_id",
        "Excluded from products and fee totals; parent contract reconciliation unavailable",
        rowids=[row.rowid],
    )


# Current contract resolution


def is_out_of_force(row: NormalisedContract, as_of: date) -> bool:
    """True when the record cannot be in force as of `as_of`, judged from its status and dates."""
    if row.status in ("expired", "pending_signature"):
        return True
    if row.end_date is not None and row.end_date < as_of:
        return True
    if row.start_date is not None and row.start_date > as_of:
        return True
    return row.signed_date is not None and row.signed_date > as_of


def qualifies(row: NormalisedContract, as_of: date) -> bool:
    return (
        row.status == "active"
        and row.signed_date is not None
        and row.start_date is not None
        and row.end_date is not None
        and not is_out_of_force(row, as_of)
    )


def resolve_current_contract(
    contracts: list[Logical[NormalisedContract]],
    invalid_contracts: list[NormalisedContract],
    as_of: date,
) -> tuple[Resolution, list[Logical[NormalisedContract]]]:
    qualifying: list[Logical[NormalisedContract]] = []
    unresolved = any(not is_out_of_force(row, as_of) for row in invalid_contracts)
    for lc in contracts:
        if lc.integrity == "conflicting":
            unresolved = unresolved or any(
                not is_out_of_force(row, as_of) for row in lc.rows
            )
        elif is_out_of_force(lc.record, as_of):
            continue
        elif qualifies(lc.record, as_of):
            qualifying.append(lc)
        else:
            unresolved = True

    if len(qualifying) > 1:
        return "ambiguous", qualifying
    if unresolved:
        return "unknown", qualifying
    if qualifying:
        return "confirmed", qualifying
    return "none", qualifying


# Calculations


def index_lines(
    lines: list[Logical[NormalisedLine]], invalid_lines: list[NormalisedLine]
) -> tuple[dict[str, list[Logical[NormalisedLine]]], dict[str, list[NormalisedLine]]]:
    """Attach keyed and invalid line rows to the contract IDs they reference."""
    keyed: dict[str, list[Logical[NormalisedLine]]] = defaultdict(list)
    invalid: dict[str, list[NormalisedLine]] = defaultdict(list)
    for ll in lines:
        for contract_id in {row.contract_id for row in ll.rows if row.contract_id is not None}:
            keyed[contract_id].append(ll)
    for row in invalid_lines:
        if row.contract_id is not None:
            invalid[row.contract_id].append(row)
    return keyed, invalid


def reconcile_arr(
    lc: Logical[NormalisedContract],
    lines: list[Logical[NormalisedLine]],
    invalid_lines: list[NormalisedLine],
    warnings: list[ContractDataQualityWarning],
) -> ARRReconciliation:
    header = lc.record.arr_eur
    unavailable = ARRReconciliation(
        header_arr_eur=header,
        line_fees_total_eur=None,
        difference_eur=None,
        status="unavailable",
    )
    if header is None:
        return unavailable
    if not lines and not invalid_lines:
        warn(
            warnings,
            "missing_contract_lines",
            "contract_lines",
            f"Contract {lc.key} has no contract lines",
            "Line fee reconciliation unavailable",
            record_id=lc.key,
            rowids=lc.source_rowids,
        )
        return unavailable
    if invalid_lines or any(ll.integrity == "conflicting" for ll in lines):
        return unavailable
    fees = [ll.record.annual_fee_eur for ll in lines]
    if any(fee is None for fee in fees):
        return unavailable

    total = sum(fee for fee in fees if fee is not None)
    difference = header - total
    if difference == 0:
        return ARRReconciliation(
            header_arr_eur=header,
            line_fees_total_eur=total,
            difference_eur=0,
            status="matched",
        )
    warn(
        warnings,
        "arr_line_fee_mismatch",
        "contracts",
        f"Header ARR {header} differs from line fee total {total} by {difference}",
        "Header ARR kept as the reported contractual ARR; difference flagged",
        record_id=lc.key,
        rowids=lc.source_rowids,
    )
    return ARRReconciliation(
        header_arr_eur=header,
        line_fees_total_eur=total,
        difference_eur=difference,
        status="mismatch",
    )


def build_summary(
    lc: Logical[NormalisedContract],
    as_of: date,
    lines: list[Logical[NormalisedLine]],
    invalid_lines: list[NormalisedLine],
    warnings: list[ContractDataQualityWarning],
) -> ContractSummary:
    row = lc.record
    # Only contracts that qualify as in force reach this point; qualifies() guarantees these values.
    assert row.status == "active" and row.start_date and row.end_date and row.signed_date
    notice_deadline = (
        None
        if row.notice_period_days is None
        else row.end_date - timedelta(days=row.notice_period_days)
    )
    days_until_notice = (
        None if notice_deadline is None else (notice_deadline - as_of).days
    )
    return ContractSummary(
        contract_id=lc.key,
        contract_type=row.contract_type,
        status=row.status,
        start_date=row.start_date,
        end_date=row.end_date,
        signed_date=row.signed_date,
        term_months=row.term_months,
        days_until_end=(row.end_date - as_of).days,
        notice_period_days=row.notice_period_days,
        notice_deadline=notice_deadline,
        days_until_notice=days_until_notice,
        auto_renew=row.auto_renew,
        arr_eur=row.arr_eur,
        arr_reconciliation=reconcile_arr(lc, lines, invalid_lines, warnings),
        source_rowids=lc.source_rowids,
        duplicate_count=lc.duplicate_count,
    )


def resolve_product(
    row: NormalisedLine,
    catalogue: dict[str, list[tuple[int, str | None]]],
    warnings: list[ContractDataQualityWarning],
) -> tuple[str | None, list[int]]:
    if row.product_id is None:
        return None, []
    matches = catalogue.get(row.product_id, [])
    if not matches:
        warn(
            warnings,
            "unknown_product_id",
            "contract_lines",
            f"product_id {row.product_id} on line {row.line_id} is not in the products table",
            "Product name left unresolved; line kept",
            record_id=row.line_id,
            rowids=[row.rowid],
        )
        return None, []
    if len(matches) > 1:
        rowids = [rowid for rowid, _ in matches]
        warn(
            warnings,
            "conflicting_product_id",
            "products",
            f"product_id {row.product_id} has {len(matches)} catalogue rows",
            "Product name left unresolved; line kept",
            record_id=row.product_id,
            rowids=rowids,
        )
        return None, rowids
    rowid, name = matches[0]
    return name, [rowid]


def product_lines(
    lc: Logical[NormalisedContract],
    lines: list[Logical[NormalisedLine]],
    catalogue: dict[str, list[tuple[int, str | None]]],
    warnings: list[ContractDataQualityWarning],
) -> list[ContractProductLine]:
    result: list[ContractProductLine] = []
    for ll in lines:
        if ll.integrity == "conflicting":
            continue
        row = ll.record
        name, product_rowids = resolve_product(row, catalogue, warnings)
        result.append(
            ContractProductLine(
                line_id=ll.key,
                contract_id=lc.key,
                product_id=row.product_id,
                product_name=name,
                annual_fee_eur=row.annual_fee_eur,
                included_units_monthly=row.included_units_monthly,
                overage_rate_eur_per_unit=row.overage_rate_eur_per_unit,
                source_rowids=ll.source_rowids,
                product_source_rowids=product_rowids,
            )
        )
    return result


def build_pending(
    contracts: list[Logical[NormalisedContract]],
) -> list[PendingContract]:
    return [
        PendingContract(
            contract_id=lc.key,
            contract_type=lc.record.contract_type,
            start_date=lc.record.start_date,
            end_date=lc.record.end_date,
            signed_date=lc.record.signed_date,
            arr_eur=lc.record.arr_eur,
            source_rowids=lc.source_rowids,
            duplicate_count=lc.duplicate_count,
        )
        for lc in contracts
        if lc.integrity != "conflicting" and lc.record.status == "pending_signature"
    ]


def is_signed_renewal(row: NormalisedContract, as_of: date) -> bool:
    return (
        row.contract_type == "renewal"
        and row.status in SIGNED_STATUSES
        and row.signed_date is not None
        and row.signed_date <= as_of
    )


def is_predecessor(row: NormalisedContract, renewal_start: date, renewal_signed: date) -> bool:
    return (
        row.status in SIGNED_STATUSES
        and row.signed_date is not None
        and row.end_date is not None
        and row.signed_date < renewal_signed
        and row.end_date < renewal_start
    )


def arr_change_at_last_renewal(
    contracts: list[Logical[NormalisedContract]],
    invalid_contracts: list[NormalisedContract],
    as_of: date,
    warnings: list[ContractDataQualityWarning],
) -> ARRChangeAtLastRenewal:
    """ARR change between the latest signed renewal and its nearest preceding signed contract.

    The predecessor link is inferred from dates because the schema has no predecessor key.
    """
    usable = [lc for lc in contracts if lc.integrity != "conflicting"]
    unresolved_rows = [
        row for lc in contracts if lc.integrity == "conflicting" for row in lc.rows
    ] + invalid_contracts
    maybe_renewals = [row for row in unresolved_rows if row.contract_type != "new"]

    signed_renewals = [lc for lc in usable if is_signed_renewal(lc.record, as_of)]
    if not signed_renewals:
        reason = "no signed renewal contract on record as of as_of"
        if maybe_renewals:
            reason = "a conflicting or invalid contract record may be a renewal; last signed renewal not established"
        return ARRChangeAtLastRenewal(status="unavailable", reason=reason)

    latest_date = max(
        lc.record.signed_date for lc in signed_renewals if lc.record.signed_date is not None
    )
    latest = [lc for lc in signed_renewals if lc.record.signed_date == latest_date]
    if len({lc.key for lc in latest}) > 1:
        ids = sorted(lc.key for lc in latest)
        warn(
            warnings,
            "renewal_contract_ambiguous",
            "contracts",
            f"Renewals {', '.join(ids)} share the latest signed date {latest_date}",
            "ARR change at last renewal not calculated",
            rowids=[rowid for lc in latest for rowid in lc.source_rowids],
        )
        return ARRChangeAtLastRenewal(
            status="ambiguous",
            reason=f"renewals {', '.join(ids)} share the latest signed date {latest_date}",
        )

    renewal = latest[0]
    renewal_row = renewal.record
    renewal_fields = {
        "renewal_contract_id": renewal.key,
        "renewal_source_rowids": renewal.source_rowids,
        "renewal_arr_eur": renewal_row.arr_eur,
    }
    if any(row.signed_date is None or row.signed_date >= latest_date for row in maybe_renewals):
        return ARRChangeAtLastRenewal(
            status="unavailable",
            reason="a conflicting or invalid contract record may be a later renewal",
            **renewal_fields,
        )
    if renewal_row.arr_eur is None or renewal_row.start_date is None:
        return ARRChangeAtLastRenewal(
            status="unavailable",
            reason=f"latest renewal {renewal.key} has invalid or missing ARR or start date",
            **renewal_fields,
        )
    renewal_start = renewal_row.start_date

    predecessors = [
        lc
        for lc in usable
        if lc.key != renewal.key and is_predecessor(lc.record, renewal_start, latest_date)
    ]
    if not predecessors:
        warn(
            warnings,
            "renewal_predecessor_unavailable",
            "contracts",
            f"No eligible preceding signed contract for renewal {renewal.key}",
            "ARR change at last renewal not calculated",
            record_id=renewal.key,
            rowids=renewal.source_rowids,
        )
        return ARRChangeAtLastRenewal(
            status="unavailable",
            reason="no eligible preceding signed contract",
            **renewal_fields,
        )

    nearest_end = max(
        lc.record.end_date for lc in predecessors if lc.record.end_date is not None
    )
    nearest = [lc for lc in predecessors if lc.record.end_date == nearest_end]
    if len({lc.key for lc in nearest}) > 1:
        ids = sorted(lc.key for lc in nearest)
        warn(
            warnings,
            "renewal_predecessor_ambiguous",
            "contracts",
            f"Predecessors {', '.join(ids)} for renewal {renewal.key} share end date {nearest_end}",
            "ARR change at last renewal not calculated",
            record_id=renewal.key,
            rowids=renewal.source_rowids,
        )
        return ARRChangeAtLastRenewal(
            status="ambiguous",
            reason=f"predecessors {', '.join(ids)} share end date {nearest_end}",
            **renewal_fields,
        )

    previous = nearest[0]
    previous_row = previous.record
    if previous_row.arr_eur is None:
        return ARRChangeAtLastRenewal(
            status="unavailable",
            reason=f"predecessor {previous.key} has invalid or missing ARR",
            **renewal_fields,
        )

    change = renewal_row.arr_eur - previous_row.arr_eur
    percentage = None
    reason = None
    if previous_row.arr_eur == 0:
        reason = "previous ARR is zero; percentage change is undefined"
    else:
        percentage = (Decimal(change) / Decimal(previous_row.arr_eur) * 100).quantize(
            Decimal("0.01")
        )
    return ARRChangeAtLastRenewal(
        status="calculated",
        reason=reason,
        previous_contract_id=previous.key,
        previous_source_rowids=previous.source_rowids,
        previous_arr_eur=previous_row.arr_eur,
        change_eur=change,
        change_percentage=percentage,
        relationship_basis="chronological_inference",
        warning=CHRONOLOGICAL_WARNING,
        **renewal_fields,
    )


def duplicate_summary(
    contracts: list[Logical[NormalisedContract]],
) -> DuplicateSummary:
    duplicated = [lc for lc in contracts if lc.integrity == "identical_duplicate"]
    conflicting = [lc for lc in contracts if lc.integrity == "conflicting"]
    return DuplicateSummary(
        duplicate_contract_ids=[lc.key for lc in duplicated],
        conflicting_contract_ids=[lc.key for lc in conflicting],
        duplicate_physical_rows=sum(
            lc.duplicate_count for lc in duplicated + conflicting
        ),
    )


def source_references(
    summaries: list[ContractSummary],
    products: list[ContractProductLine],
    pending: list[PendingContract],
    arr: ARRChangeAtLastRenewal,
) -> list[SourceReference]:
    refs: dict[tuple[str, str], SourceReference] = {}

    def add(table: str, record_id: str | None, rowids: list[int]) -> None:
        if record_id is not None and rowids:
            refs.setdefault(
                (table, record_id),
                SourceReference(table=table, record_id=record_id, source_rowids=rowids),
            )

    for summary in summaries:
        add("contracts", summary.contract_id, summary.source_rowids)
    for line in products:
        add("contract_lines", line.line_id, line.source_rowids)
        add("products", line.product_id, line.product_source_rowids)
    for pending_contract in pending:
        add("contracts", pending_contract.contract_id, pending_contract.source_rowids)
    add("contracts", arr.renewal_contract_id, arr.renewal_source_rowids)
    add("contracts", arr.previous_contract_id, arr.previous_source_rowids)
    return list(refs.values())


def build_result(
    client_id: str,
    as_of: date,
    contracts: list[Logical[NormalisedContract]],
    invalid_contracts: list[NormalisedContract],
    lines: list[Logical[NormalisedLine]],
    invalid_lines: list[NormalisedLine],
    catalogue: dict[str, list[tuple[int, str | None]]],
) -> ContractStatusResult:
    warnings: list[ContractDataQualityWarning] = []
    for lc in contracts:
        contract_warnings(lc, as_of, warnings)
    for row in invalid_contracts:
        invalid_contract_warnings(row, warnings)
    for ll in lines:
        line_warnings(ll, warnings)
    for line_row in invalid_lines:
        invalid_line_warnings(line_row, warnings)

    keyed_lines, invalid_by_contract = index_lines(lines, invalid_lines)
    resolution, qualifying = resolve_current_contract(contracts, invalid_contracts, as_of)
    if resolution == "ambiguous":
        warn(
            warnings,
            "multiple_contracts_in_force",
            "contracts",
            f"{len(qualifying)} clean contracts qualify as in force: {', '.join(lc.key for lc in qualifying)}",
            "No contract selected; candidates listed",
            rowids=[rowid for lc in qualifying for rowid in lc.source_rowids],
        )

    summaries = [
        build_summary(
            lc,
            as_of,
            keyed_lines.get(lc.key, []),
            invalid_by_contract.get(lc.key, []),
            warnings,
        )
        for lc in qualifying
    ]
    current = summaries[0] if resolution == "confirmed" else None
    current_products = None
    if resolution == "confirmed":
        current_products = product_lines(
            qualifying[0],
            keyed_lines.get(qualifying[0].key, []),
            catalogue,
            warnings,
        )
    candidates = summaries if resolution in ("ambiguous", "unknown") else []
    pending = build_pending(contracts)
    arr = arr_change_at_last_renewal(contracts, invalid_contracts, as_of, warnings)

    return ContractStatusResult(
        client_id=client_id,
        as_of=as_of,
        current_contract_resolution=resolution,
        current_contract=current,
        current_contract_candidates=candidates,
        current_products=current_products,
        pending_contracts=pending,
        arr_change_at_last_renewal=arr,
        duplicate_summary=duplicate_summary(contracts),
        warnings=warnings,
        source_references=source_references(
            summaries, current_products or [], pending, arr
        ),
    )


def get_contract_status(
    client_id: str, as_of: date = AS_OF, path: Path = DB_PATH
) -> ContractStatusResult:
    """Contract in force, products, ARR, notice and renewal position for a canonical client ID."""
    try:
        with connect(path) as conn:
            contracts, invalid_contracts = classify_rows(
                [
                    normalise_contract(raw, rowid)
                    for rowid, raw in fetch_contract_rows(conn, client_id)
                ]
            )
            contract_ids = sorted({lc.key for lc in contracts})
            lines, invalid_lines = classify_rows(
                [
                    normalise_line(raw, rowid)
                    for rowid, raw in fetch_line_rows(conn, contract_ids)
                ]
            )
            line_rows = [row for ll in lines for row in ll.rows] + invalid_lines
            catalogue = fetch_catalogue(
                conn, {row.product_id for row in line_rows if row.product_id is not None}
            )
    except sqlite3.Error as e:
        raise DatabaseError(f"Could not read contract status from {path}: {e}") from e
    return build_result(
        client_id, as_of, contracts, invalid_contracts, lines, invalid_lines, catalogue
    )


if __name__ == '__main__':
    print(get_contract_status('C006').model_dump_json(indent=2))
