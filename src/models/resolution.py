from typing import Literal

from pydantic import BaseModel

Status = Literal["resolved", "ambiguous", "not_found"]
MatchType = Literal["client_id", "exact_name", "normalised_name", "fuzzy"]


class ClientCandidate(BaseModel):
    client_id: str
    client_name: str
    score: float


class ClientResolution(BaseModel):
    input: str
    status: Status
    client_id: str | None = None
    client_name: str | None = None
    match_type: MatchType | None = None
    score: float | None = None
    candidates: list[ClientCandidate] = []
