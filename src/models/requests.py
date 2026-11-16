from datetime import date
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, StringConstraints

AS_OF = date(2026, 11, 1)

Trigger = Literal["renewal", "meeting_prep", "upsell", "at_risk"]
NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ClientRequest(BaseModel):
    request_id: NonBlankStr = Field(default_factory=lambda: str(uuid4()))
    client: NonBlankStr
    trigger: Trigger
    rep_context: str | None = None
    as_of: date = AS_OF
