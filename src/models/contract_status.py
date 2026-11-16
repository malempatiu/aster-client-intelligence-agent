from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

Resolution = Literal["confirmed", "none", "ambiguous", "unknown"]
ContractStatusValue = Literal["active", "expired", "pending_signature"]
ContractTypeValue = Literal["new", "renewal"]
AutoRenew = Literal["yes", "no", "unknown"]
RecordIntegrity = Literal["clean", "identical_duplicate", "conflicting", "invalid"]
Severity = Literal["low", "medium", "high"]
ReconciliationStatus = Literal["matched", "mismatch", "unavailable"]
ArrChangeStatus = Literal["calculated", "unavailable", "ambiguous"]


class ContractDataQualityWarning(BaseModel):
    code: str
    severity: Severity
    table: str
    record_id: str | None = None
    source_rowids: list[int] = []
    message: str
    recommended_treatment: str
    details: dict[str, Any] = {}


class SourceReference(BaseModel):
    table: str
    record_id: str
    source_rowids: list[int]


class ARRReconciliation(BaseModel):
    header_arr_eur: int | None
    line_fees_total_eur: int | None
    difference_eur: int | None
    status: ReconciliationStatus


class ContractSummary(BaseModel):
    contract_id: str
    contract_type: ContractTypeValue | None
    status: ContractStatusValue
    start_date: date
    end_date: date
    signed_date: date
    term_months: int | None
    days_until_end: int
    notice_period_days: int | None
    notice_deadline: date | None
    days_until_notice: int | None
    auto_renew: AutoRenew
    arr_eur: int | None
    arr_reconciliation: ARRReconciliation
    source_rowids: list[int]
    duplicate_count: int


class ContractProductLine(BaseModel):
    line_id: str
    contract_id: str
    product_id: str | None
    product_name: str | None
    annual_fee_eur: int | None
    included_units_monthly: int | None
    overage_rate_eur_per_unit: Decimal | None
    source_rowids: list[int]
    product_source_rowids: list[int]


class PendingContract(BaseModel):
    contract_id: str
    contract_type: ContractTypeValue | None
    start_date: date | None
    end_date: date | None
    signed_date: date | None
    arr_eur: int | None
    source_rowids: list[int]
    duplicate_count: int


class ARRChangeAtLastRenewal(BaseModel):
    status: ArrChangeStatus
    reason: str | None = None
    renewal_contract_id: str | None = None
    renewal_source_rowids: list[int] = []
    previous_contract_id: str | None = None
    previous_source_rowids: list[int] = []
    renewal_arr_eur: int | None = None
    previous_arr_eur: int | None = None
    change_eur: int | None = None
    change_percentage: Decimal | None = None
    relationship_basis: Literal["chronological_inference"] | None = None
    warning: str | None = None


class DuplicateSummary(BaseModel):
    duplicate_contract_ids: list[str]
    conflicting_contract_ids: list[str]
    duplicate_physical_rows: int


class ContractStatusResult(BaseModel):
    tool_name: Literal["get_contract_status"] = "get_contract_status"
    client_id: str
    as_of: date
    current_contract_resolution: Resolution
    current_contract: ContractSummary | None = None
    current_contract_candidates: list[ContractSummary] = []
    current_products: list[ContractProductLine] | None = None
    pending_contracts: list[PendingContract] = []
    arr_change_at_last_renewal: ARRChangeAtLastRenewal
    duplicate_summary: DuplicateSummary
    warnings: list[ContractDataQualityWarning] = []
    source_references: list[SourceReference] = []
