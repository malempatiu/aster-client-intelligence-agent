import hashlib
import sqlite3
from datetime import date, timedelta

import pytest

from src.database import DB_PATH
from src.models.contract_status import (
    ContractProductLine,
    ContractStatusResult,
    ContractSummary,
)
from src.tools.contract_status import (
    CONTRACT_COLUMNS,
    LINE_COLUMNS,
    get_contract_status,
)

AS_OF = date(2026, 11, 1)
PRODUCT_COLUMNS = ("product_id", "product_name")


def contract(**overrides):
    row = {
        "contract_id": "K-1",
        "client_id": "C1",
        "contract_type": "new",
        "start_date": "2025-01-01",
        "end_date": "2027-12-31",
        "term_months": "36",
        "auto_renew": "Y",
        "notice_period_days": "90",
        "arr_eur": "120000",
        "currency": "EUR",
        "status": "active",
        "signed_date": "2024-12-01",
    }
    row.update(overrides)
    return row


def line(**overrides):
    row = {
        "line_id": "L-1",
        "contract_id": "K-1",
        "product_id": "LIVE_DATA",
        "annual_fee_eur": "120000",
        "included_units_monthly": "1000",
        "overage_rate_eur_per_unit": "6.0",
    }
    row.update(overrides)
    return row


def product(**overrides):
    row = {"product_id": "LIVE_DATA", "product_name": "Live Match Data Feed"}
    row.update(overrides)
    return row


DEFAULT_PRODUCTS = [
    product(),
    product(product_id="STREAM", product_name="Live Streaming"),
]


def make_db(tmp_path, contracts=(), lines=(), products=DEFAULT_PRODUCTS):
    path = tmp_path / "test.db"
    conn = sqlite3.connect(path)
    for table, columns, rows in (
        ("contracts", CONTRACT_COLUMNS, contracts),
        ("contract_lines", LINE_COLUMNS, lines),
        ("products", PRODUCT_COLUMNS, products),
    ):
        conn.execute(
            f"CREATE TABLE {table} ({', '.join(f'{c} TEXT' for c in columns)})"
        )
        placeholders = ",".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
            [tuple(row[c] for c in columns) for row in rows],
        )
    conn.commit()
    conn.close()
    return path


def run(path, as_of=AS_OF, client_id="C1"):
    return get_contract_status(client_id, as_of, path)


def codes(result):
    return {w.code for w in result.warnings}


def warning(result, code):
    return next(w for w in result.warnings if w.code == code)


def summary_of(result: ContractStatusResult) -> ContractSummary:
    assert result.current_contract is not None
    return result.current_contract


def products_of(result: ContractStatusResult) -> list[ContractProductLine]:
    assert result.current_products is not None
    return result.current_products


# Contract classification (spec 10.1)


def test_active_contract_in_force_is_confirmed(tmp_path):
    result = run(make_db(tmp_path, contracts=[contract()], lines=[line()]))
    assert result.current_contract_resolution == "confirmed"
    assert summary_of(result).contract_id == "K-1"
    assert [p.line_id for p in products_of(result)] == ["L-1"]


def test_end_date_on_as_of_is_in_force(tmp_path):
    result = run(
        make_db(tmp_path, contracts=[contract(end_date="2026-11-01")], lines=[line()])
    )
    assert result.current_contract_resolution == "confirmed"
    assert summary_of(result).days_until_end == 0


def test_start_date_on_as_of_is_in_force(tmp_path):
    result = run(
        make_db(
            tmp_path,
            contracts=[contract(start_date="2026-11-01", signed_date="2026-10-01")],
            lines=[line()],
        )
    )
    assert result.current_contract_resolution == "confirmed"


def test_active_starting_after_as_of_is_not_in_force(tmp_path):
    result = run(make_db(tmp_path, contracts=[contract(start_date="2026-12-01")]))
    assert result.current_contract_resolution == "none"
    assert "contract_status_date_conflict" in codes(result)


def test_active_ended_before_as_of_is_not_in_force(tmp_path):
    result = run(make_db(tmp_path, contracts=[contract(end_date="2026-10-31")]))
    assert result.current_contract_resolution == "none"
    assert "contract_status_date_conflict" in codes(result)


@pytest.mark.parametrize(
    ("signed", "code"),
    [("", "missing_signed_date"), ("2026/01/05", "invalid_contract_date")],
)
def test_active_without_valid_signed_date_is_unknown(tmp_path, signed, code):
    result = run(
        make_db(tmp_path, contracts=[contract(signed_date=signed)], lines=[line()])
    )
    assert result.current_contract_resolution == "unknown"
    assert result.current_contract is None
    assert result.current_products is None
    assert code in codes(result)


def test_signed_after_as_of_is_not_confirmed(tmp_path):
    result = run(make_db(tmp_path, contracts=[contract(signed_date="2026-11-05")]))
    assert result.current_contract_resolution == "none"
    assert "signed_date_after_as_of" in codes(result)


def test_expired_contract_is_not_in_force(tmp_path):
    result = run(
        make_db(tmp_path, contracts=[contract(status="expired", end_date="2026-09-30")])
    )
    assert result.current_contract_resolution == "none"
    assert result.current_products is None


def test_expired_status_with_future_end_warns(tmp_path):
    result = run(make_db(tmp_path, contracts=[contract(status="expired")]))
    assert result.current_contract_resolution == "none"
    assert "contract_status_date_conflict" in codes(result)


def test_pending_contract_is_listed_separately_and_not_in_force(tmp_path):
    pending = contract(
        contract_id="K-P",
        status="pending_signature",
        signed_date="",
        start_date="2026-12-01",
    )
    result = run(
        make_db(tmp_path, contracts=[pending], lines=[line(contract_id="K-P")])
    )
    assert result.current_contract_resolution == "none"
    assert [p.contract_id for p in result.pending_contracts] == ["K-P"]
    assert result.pending_contracts[0].signed_date is None
    assert "contract_status_date_conflict" not in codes(result)


def test_pending_contract_with_signed_date_warns(tmp_path):
    pending = contract(
        contract_id="K-P", status="pending_signature", signed_date="2026-10-01"
    )
    result = run(make_db(tmp_path, contracts=[pending]))
    assert result.current_contract_resolution == "none"
    assert [p.contract_id for p in result.pending_contracts] == ["K-P"]
    assert "contract_status_date_conflict" in codes(result)


def test_no_contracts_resolves_to_none(tmp_path):
    result = run(make_db(tmp_path))
    assert result.current_contract_resolution == "none"
    assert result.current_contract is None
    assert result.current_products is None
    assert result.pending_contracts == []


def test_two_clean_contracts_in_force_are_ambiguous(tmp_path):
    result = run(
        make_db(
            tmp_path,
            contracts=[
                contract(contract_id="K-1"),
                contract(contract_id="K-2", arr_eur="50000"),
            ],
            lines=[
                line(),
                line(line_id="L-2", contract_id="K-2", annual_fee_eur="50000"),
            ],
        )
    )
    assert result.current_contract_resolution == "ambiguous"
    assert result.current_contract is None
    assert result.current_products is None
    assert {c.contract_id for c in result.current_contract_candidates} == {"K-1", "K-2"}
    assert "multiple_contracts_in_force" in codes(result)


def test_conflicting_duplicate_that_could_be_in_force_is_unknown(tmp_path):
    result = run(
        make_db(
            tmp_path,
            contracts=[contract(), contract(arr_eur="130000")],
            lines=[line()],
        )
    )
    assert result.current_contract_resolution == "unknown"
    assert result.current_contract is None
    assert result.current_products is None
    warn = warning(result, "conflicting_contract_id")
    assert warn.source_rowids == [1, 2]
    assert warn.details["differing_fields"] == ["arr_eur"]


def test_conflicting_duplicate_that_cannot_be_in_force_does_not_block(tmp_path):
    result = run(
        make_db(
            tmp_path,
            contracts=[
                contract(),
                contract(contract_id="K-2", status="expired", end_date="2026-09-30"),
                contract(
                    contract_id="K-2",
                    status="expired",
                    end_date="2026-09-30",
                    arr_eur="90000",
                ),
            ],
            lines=[line()],
        )
    )
    assert result.current_contract_resolution == "confirmed"
    assert summary_of(result).contract_id == "K-1"
    assert result.duplicate_summary.conflicting_contract_ids == ["K-2"]


# Duplicates (spec 10.2)


def test_single_row_has_no_duplicate_warnings(tmp_path):
    result = run(make_db(tmp_path, contracts=[contract()], lines=[line()]))
    assert summary_of(result).source_rowids == [1]
    assert summary_of(result).duplicate_count == 0
    assert not {"duplicate_contract_record", "conflicting_contract_id"} & codes(result)


def test_identical_duplicates_count_once_and_keep_rowids(tmp_path):
    result = run(make_db(tmp_path, contracts=[contract(), contract()], lines=[line()]))
    assert result.current_contract_resolution == "confirmed"
    assert summary_of(result).source_rowids == [1, 2]
    assert summary_of(result).duplicate_count == 1
    assert summary_of(result).arr_eur == 120000
    assert summary_of(result).arr_reconciliation.status == "matched"
    assert result.duplicate_summary.duplicate_contract_ids == ["K-1"]
    assert result.duplicate_summary.duplicate_physical_rows == 1
    assert "duplicate_contract_record" in codes(result)


def test_semantically_identical_duplicates_with_whitespace_and_case(tmp_path):
    rows = [
        contract(),
        contract(contract_id=" K-1 ", client_id=" C1", status=" Active "),
    ]
    result = run(make_db(tmp_path, contracts=rows, lines=[line()]))
    assert result.current_contract_resolution == "confirmed"
    assert summary_of(result).source_rowids == [1, 2]
    assert result.duplicate_summary.conflicting_contract_ids == []


def test_blank_contract_id_is_not_authoritative_and_blocks_confirmation(tmp_path):
    result = run(
        make_db(
            tmp_path, contracts=[contract(), contract(contract_id="")], lines=[line()]
        )
    )
    assert result.current_contract_resolution == "unknown"
    assert warning(result, "missing_contract_id").source_rowids == [2]


def test_duplicate_line_ids_identical_count_once(tmp_path):
    result = run(make_db(tmp_path, contracts=[contract()], lines=[line(), line()]))
    assert summary_of(result).arr_reconciliation.status == "matched"
    assert summary_of(result).arr_reconciliation.line_fees_total_eur == 120000
    assert len(products_of(result)) == 1
    assert products_of(result)[0].source_rowids == [1, 2]
    assert "contract_line_duplicate" in codes(result)


def test_conflicting_line_id_excluded_and_reconciliation_unavailable(tmp_path):
    result = run(
        make_db(
            tmp_path,
            contracts=[contract()],
            lines=[line(), line(annual_fee_eur="50000")],
        )
    )
    assert result.current_contract_resolution == "confirmed"
    assert summary_of(result).arr_reconciliation.status == "unavailable"
    assert result.current_products == []
    assert warning(result, "conflicting_contract_line_id").source_rowids == [1, 2]


def test_line_for_unknown_contract_is_not_attributed(tmp_path):
    result = run(
        make_db(
            tmp_path,
            contracts=[contract()],
            lines=[line(), line(line_id="L-9", contract_id="K-9")],
        )
    )
    assert [p.line_id for p in products_of(result)] == ["L-1"]


def test_unknown_product_keeps_line_with_null_name(tmp_path):
    result = run(
        make_db(tmp_path, contracts=[contract()], lines=[line(product_id="NOPE")])
    )
    assert products_of(result)[0].product_id == "NOPE"
    assert products_of(result)[0].product_name is None
    assert "unknown_product_id" in codes(result)


def test_duplicate_product_rows_do_not_multiply_lines(tmp_path):
    products = DEFAULT_PRODUCTS + [product()]
    result = run(
        make_db(tmp_path, contracts=[contract()], lines=[line()], products=products)
    )
    assert len(products_of(result)) == 1
    assert products_of(result)[0].product_name is None
    assert "conflicting_product_id" in codes(result)


# Calculations (spec 10.3)


@pytest.mark.parametrize("days_from_deadline", [5, 0, -5])
def test_days_until_notice_positive_zero_negative(tmp_path, days_from_deadline):
    end = date(2027, 12, 31)
    deadline = end - timedelta(days=90)
    as_of = deadline - timedelta(days=days_from_deadline)
    result = run(make_db(tmp_path, contracts=[contract()], lines=[line()]), as_of=as_of)
    assert summary_of(result).notice_deadline == deadline
    assert summary_of(result).days_until_notice == days_from_deadline
    assert summary_of(result).days_until_end == (end - as_of).days


def test_days_until_end_is_not_off_by_one(tmp_path):
    result = run(
        make_db(tmp_path, contracts=[contract(end_date="2026-12-01")], lines=[line()])
    )
    assert summary_of(result).days_until_end == 30


def test_missing_notice_period_leaves_deadline_null(tmp_path):
    result = run(
        make_db(tmp_path, contracts=[contract(notice_period_days="")], lines=[line()])
    )
    assert summary_of(result).notice_deadline is None
    assert summary_of(result).days_until_notice is None
    assert "missing_notice_period" in codes(result)


def test_header_arr_matching_line_total(tmp_path):
    result = run(make_db(tmp_path, contracts=[contract()], lines=[line()]))
    recon = summary_of(result).arr_reconciliation
    assert (
        recon.header_arr_eur,
        recon.line_fees_total_eur,
        recon.difference_eur,
        recon.status,
    ) == (
        120000,
        120000,
        0,
        "matched",
    )


def test_header_arr_differing_from_line_total_is_mismatch(tmp_path):
    result = run(
        make_db(tmp_path, contracts=[contract()], lines=[line(annual_fee_eur="100000")])
    )
    recon = summary_of(result).arr_reconciliation
    assert (
        recon.header_arr_eur,
        recon.line_fees_total_eur,
        recon.difference_eur,
        recon.status,
    ) == (
        120000,
        100000,
        20000,
        "mismatch",
    )
    assert summary_of(result).arr_eur == 120000
    assert "arr_line_fee_mismatch" in codes(result)


@pytest.mark.parametrize("arr", ["", "12k"])
def test_missing_or_invalid_arr_is_unavailable(tmp_path, arr):
    result = run(make_db(tmp_path, contracts=[contract(arr_eur=arr)], lines=[line()]))
    assert summary_of(result).arr_eur is None
    assert summary_of(result).arr_reconciliation.status == "unavailable"
    assert "invalid_arr_value" in codes(result)


@pytest.mark.parametrize("fee", ["", "abc"])
def test_missing_or_invalid_line_fee_makes_reconciliation_unavailable(tmp_path, fee):
    result = run(
        make_db(tmp_path, contracts=[contract()], lines=[line(annual_fee_eur=fee)])
    )
    assert summary_of(result).arr_reconciliation.status == "unavailable"
    assert products_of(result)[0].annual_fee_eur is None
    assert "invalid_line_value" in codes(result)


def test_contract_without_lines_is_unavailable_not_mismatch(tmp_path):
    result = run(make_db(tmp_path, contracts=[contract()]))
    assert summary_of(result).arr_reconciliation.status == "unavailable"
    assert result.current_products == []
    assert "missing_contract_lines" in codes(result)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Y", "yes"), ("N", "no"), ("", "unknown"), ("maybe", "unknown")],
)
def test_auto_renew_normalisation(tmp_path, raw, expected):
    result = run(
        make_db(tmp_path, contracts=[contract(auto_renew=raw)], lines=[line()])
    )
    assert summary_of(result).auto_renew == expected
    assert ("invalid_auto_renew_value" in codes(result)) == (expected == "unknown")


# ARR at last renewal (spec 10.4)

PREVIOUS = contract(
    contract_id="K-0",
    contract_type="new",
    start_date="2023-01-01",
    end_date="2025-12-31",
    arr_eur="100000",
    status="expired",
    signed_date="2022-12-01",
)


def renewal(**overrides):
    return contract(
        **{
            "contract_id": "K-1",
            "contract_type": "renewal",
            "start_date": "2026-01-01",
            "end_date": "2027-12-31",
            "arr_eur": "120000",
            "signed_date": "2025-11-01",
            **overrides,
        }
    )


def test_renewal_with_clear_predecessor_is_calculated_as_chronological_inference(
    tmp_path,
):
    result = run(make_db(tmp_path, contracts=[PREVIOUS, renewal()], lines=[line()]))
    arr = result.arr_change_at_last_renewal
    assert arr.status == "calculated"
    assert (arr.previous_contract_id, arr.renewal_contract_id) == ("K-0", "K-1")
    assert (arr.previous_arr_eur, arr.renewal_arr_eur, arr.change_eur) == (
        100000,
        120000,
        20000,
    )
    assert arr.change_percentage == 20 and str(arr.change_percentage) == "20.00"
    assert arr.relationship_basis == "chronological_inference"
    assert arr.warning


@pytest.mark.parametrize(
    ("new_arr", "change", "pct"),
    [("80000", -20000, "-20.00"), ("120000", 20000, "20.00")],
)
def test_arr_decrease_and_increase(tmp_path, new_arr, change, pct):
    result = run(make_db(tmp_path, contracts=[PREVIOUS, renewal(arr_eur=new_arr)]))
    arr = result.arr_change_at_last_renewal
    assert arr.change_eur == change
    assert str(arr.change_percentage) == pct


def test_no_predecessor_is_unavailable(tmp_path):
    result = run(make_db(tmp_path, contracts=[renewal()]))
    assert result.arr_change_at_last_renewal.status == "unavailable"
    assert "renewal_predecessor_unavailable" in codes(result)


def test_predecessors_sharing_nearest_end_date_are_ambiguous(tmp_path):
    other = dict(PREVIOUS, contract_id="K-0A", arr_eur="90000")
    result = run(make_db(tmp_path, contracts=[PREVIOUS, other, renewal()]))
    assert result.arr_change_at_last_renewal.status == "ambiguous"
    assert "renewal_predecessor_ambiguous" in codes(result)


def test_renewals_sharing_latest_signed_date_are_ambiguous(tmp_path):
    other = renewal(contract_id="K-2")
    result = run(make_db(tmp_path, contracts=[PREVIOUS, renewal(), other]))
    assert result.arr_change_at_last_renewal.status == "ambiguous"
    assert "renewal_contract_ambiguous" in codes(result)


def test_conflicting_duplicate_renewal_blocks_comparison(tmp_path):
    result = run(
        make_db(tmp_path, contracts=[PREVIOUS, renewal(), renewal(arr_eur="130000")])
    )
    assert result.arr_change_at_last_renewal.status == "unavailable"
    assert "conflicting_contract_id" in codes(result)


@pytest.mark.parametrize("arr", ["", "12k"])
def test_missing_or_invalid_renewal_arr_is_unavailable(tmp_path, arr):
    result = run(make_db(tmp_path, contracts=[PREVIOUS, renewal(arr_eur=arr)]))
    assert result.arr_change_at_last_renewal.status == "unavailable"
    assert result.arr_change_at_last_renewal.change_eur is None


def test_previous_arr_zero_gives_absolute_change_and_null_percentage(tmp_path):
    result = run(make_db(tmp_path, contracts=[dict(PREVIOUS, arr_eur="0"), renewal()]))
    arr = result.arr_change_at_last_renewal
    assert arr.status == "calculated"
    assert arr.change_eur == 120000
    assert arr.change_percentage is None
    assert arr.reason is not None and "undefined" in arr.reason


def test_identical_duplicate_predecessor_does_not_create_ambiguity(tmp_path):
    result = run(make_db(tmp_path, contracts=[PREVIOUS, dict(PREVIOUS), renewal()]))
    arr = result.arr_change_at_last_renewal
    assert arr.status == "calculated"
    assert arr.previous_source_rowids == [1, 2]


# Source references and warnings


def test_source_references_keep_physical_rowids(tmp_path):
    result = run(make_db(tmp_path, contracts=[contract(), contract()], lines=[line()]))
    refs = {(r.table, r.record_id): r.source_rowids for r in result.source_references}
    assert refs[("contracts", "K-1")] == [1, 2]
    assert refs[("contract_lines", "L-1")] == [1]
    assert refs[("products", "LIVE_DATA")] == [1]


def test_every_warning_is_structured(tmp_path):
    result = run(
        make_db(
            tmp_path, contracts=[contract(), contract(arr_eur="130000")], lines=[line()]
        )
    )
    for w in result.warnings:
        assert w.severity in ("low", "medium", "high")
        assert w.table and w.message and w.recommended_treatment


# Integration against the supplied database (spec 10.5 and 11)


def _sql(sql, params=()):
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_database_c006_duplicate_contract_counted_once():
    before = _file_hash(DB_PATH)
    result = get_contract_status("C006", AS_OF)
    assert _file_hash(DB_PATH) == before

    rowids = [
        r
        for (r,) in _sql(
            "SELECT rowid FROM contracts WHERE contract_id = 'K-0010' ORDER BY rowid"
        )
    ]
    arr, end = _sql(
        "SELECT arr_eur, end_date FROM contracts WHERE contract_id = 'K-0010' LIMIT 1"
    )[0]

    assert result.current_contract_resolution == "confirmed"
    assert summary_of(result).contract_id == "K-0010"
    assert summary_of(result).source_rowids == rowids
    assert summary_of(result).duplicate_count == len(rowids) - 1
    assert summary_of(result).arr_eur == int(arr)
    assert summary_of(result).days_until_end == (date.fromisoformat(end) - AS_OF).days
    assert result.duplicate_summary.duplicate_contract_ids == ["K-0010"]


def test_real_database_c006_fee_reconciliation_matches_sql():
    result = get_contract_status("C006", AS_OF)
    unique_lines = _sql(
        "SELECT DISTINCT line_id, annual_fee_eur FROM contract_lines WHERE contract_id = 'K-0010'"
    )
    expected_total = sum(int(fee) for _, fee in unique_lines)
    recon = summary_of(result).arr_reconciliation
    assert recon.line_fees_total_eur == expected_total
    assert recon.status == (
        "matched" if expected_total == summary_of(result).arr_eur else "mismatch"
    )
    assert len(products_of(result)) == len(unique_lines)


def test_real_database_c006_renewal_change_matches_sql():
    result = get_contract_status("C006", AS_OF)
    arr = result.arr_change_at_last_renewal
    prev_arr = int(
        _sql("SELECT arr_eur FROM contracts WHERE contract_id = 'K-0009'")[0][0]
    )
    renewal_arr = int(
        _sql("SELECT arr_eur FROM contracts WHERE contract_id = 'K-0010' LIMIT 1")[0][0]
    )
    assert arr.status == "calculated"
    assert arr.previous_contract_id == "K-0009"
    assert arr.change_eur == renewal_arr - prev_arr


def test_real_database_c005_negative_notice_days():
    result = get_contract_status("C005", AS_OF)
    assert result.current_contract_resolution == "confirmed"
    assert summary_of(result).contract_id == "K-0008"
    assert summary_of(result).days_until_notice == -31
    assert result.arr_change_at_last_renewal.previous_contract_id == "K-0007"


def test_real_database_c007_pending_only_is_not_in_force():
    result = get_contract_status("C007", AS_OF)
    assert result.current_contract_resolution == "none"
    assert result.current_products is None
    assert [p.contract_id for p in result.pending_contracts] == ["K-0045"]
    assert result.pending_contracts[0].signed_date is None
    assert result.arr_change_at_last_renewal.status == "unavailable"


def test_real_database_every_client_runs_without_error():
    client_ids = [
        r for (r,) in _sql("SELECT client_id FROM clients ORDER BY client_id")
    ]
    before = _file_hash(DB_PATH)
    for client_id in client_ids:
        result = get_contract_status(client_id, AS_OF)
        assert result.current_contract_resolution in (
            "confirmed",
            "none",
            "ambiguous",
            "unknown",
        )
    assert _file_hash(DB_PATH) == before
