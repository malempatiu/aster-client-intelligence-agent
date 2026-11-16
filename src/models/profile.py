from datetime import date

from pydantic import BaseModel


class ClientProfile(BaseModel):
    client_id: str
    client_name: str | None
    segment: str | None
    country: str | None
    account_owner: str | None
    customer_since: date | None
    tier: str | None
    source_table: str = "clients"
    source_primary_key: str
    warnings: list[str] = []
