from pydantic import BaseModel


class ImportReadinessCheck(BaseModel):
    key: str
    label: str
    passed: bool
    blocker_count: int


class ImportReadinessBlocker(BaseModel):
    key: str
    label: str
    count: int


class ImportReadinessResponse(BaseModel):
    is_ready: bool
    checks: list[ImportReadinessCheck]
    blockers: list[ImportReadinessBlocker]
