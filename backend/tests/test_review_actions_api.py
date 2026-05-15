from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.review_actions import router
from app.api.review_actions import get_db as original_get_db


class FilterField:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)


class FakeAIExtractionLogModel:
    id = FilterField("id")


class FakeCleanRecordModel:
    raw_record_id = FilterField("raw_record_id")


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, condition):
        op, field_name, value = condition
        if op == "eq":
            self.items = [item for item in self.items if str(getattr(item, field_name)) == str(value)]
        return self

    def one_or_none(self):
        return self.items[0] if self.items else None


class FakeSession:
    def __init__(self):
        self.log = SimpleNamespace(
            id=str(uuid4()),
            raw_record_id="raw_123",
            ai_1_payload={"critical_fields": {"email": {"value": "bad-email"}}},
        )
        self.clean_record = SimpleNamespace(
            id=str(uuid4()),
            raw_record_id="raw_123",
            clean_payload={"email": "bad-email"},
            status="NEEDS_REVIEW",
        )
        self.added = []

    def query(self, model):
        if model is FakeAIExtractionLogModel:
            return FakeQuery([self.log])
        if model is FakeCleanRecordModel:
            return FakeQuery([self.clean_record])
        return FakeQuery([])

    def add(self, obj):
        if not getattr(obj, "id", None):
            obj.id = str(uuid4())
        self.added.append(obj)

    def commit(self):
        return None

    def refresh(self, _obj):
        return None


def build_client(session: FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def override_get_db():
        yield session

    app.dependency_overrides[original_get_db] = override_get_db
    return TestClient(app)


def test_submit_review_action_updates_clean_record(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.review_actions.AIExtractionLog", FakeAIExtractionLogModel)
    monkeypatch.setattr("app.api.review_actions.CleanRecord", FakeCleanRecordModel)

    response = client.post(
        "/api/v1/review-actions",
        json={
            "record_id": session.log.id,
            "field_name": "email",
            "action": "EDIT",
            "new_value": "info@example.edu",
            "note": "Fixed manually",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "SUCCESS"
    assert session.clean_record.clean_payload["email"] == "info@example.edu"
    assert session.clean_record.status == "REVIEWED"
