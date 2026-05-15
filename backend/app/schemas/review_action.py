from typing import Literal

from pydantic import BaseModel


class ReviewActionRequest(BaseModel):
    record_id: str
    field_name: str
    action: Literal["ACCEPT", "EDIT", "REJECT", "UNKNOWN"]
    new_value: str | int | float | bool | None = None
    note: str | None = None


class ReviewActionResponse(BaseModel):
    status: str
    message: str
    review_action_id: str | None = None
