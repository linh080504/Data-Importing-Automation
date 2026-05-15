from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.review import router
from app.api.review import get_db as original_get_db


class FilterField:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)


class InFilterField:
    def __init__(self, name: str):
        self.name = name

    def in_(self, values):
        return ("in", self.name, values)


class OrderField:
    def __init__(self, name: str):
        self.name = name

    def desc(self):
        return ("desc", self.name)


class FakeCrawlJobModel:
    id = FilterField("id")


class FakeRawRecordModel:
    job_id = FilterField("job_id")
    id = InFilterField("id")


class FakeAIExtractionLogModel:
    raw_record_id = InFilterField("raw_record_id")
    processed_at = OrderField("processed_at")


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, condition):
        op, field_name, value = condition
        if op == "eq":
            self.items = [item for item in self.items if str(getattr(item, field_name)) == str(value)]
        elif op == "in":
            allowed = {str(item) for item in value}
            self.items = [item for item in self.items if str(getattr(item, field_name)) in allowed]
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def offset(self, n):
        self.items = self.items[n:]
        return self

    def limit(self, n):
        self.items = self.items[:n]
        return self

    def all(self):
        return self.items

    def one_or_none(self):
        return self.items[0] if self.items else None


class FakeSession:
    def __init__(self):
        self.job = SimpleNamespace(id=str(uuid4()))
        self.raw_records = [SimpleNamespace(id="raw_123", job_id=self.job.id)]
        self.logs = [
            SimpleNamespace(
                id=str(uuid4()),
                raw_record_id="raw_123",
                overall_confidence=78,
                processed_at=1,
                ai_1_payload={
                    "critical_fields": {
                        "email": {"value": "bad-email", "confidence": 0.62, "source_excerpt": "Contact bad-email"}
                    }
                },
                ai_2_validation={
                    "judge_output": {
                        "fields_validation": {
                            "email": {
                                "is_correct": False,
                                "corrected_value": "info@example.edu",
                                "confidence": 72,
                                "reason": "Invalid format",
                            }
                        }
                    }
                },
            )
        ]

    def query(self, model):
        if model is FakeCrawlJobModel:
            return FakeQuery([self.job])
        if model is FakeRawRecordModel:
            return FakeQuery(list(self.raw_records))
        if model is FakeAIExtractionLogModel:
            return FakeQuery(list(self.logs))
        return FakeQuery([])


def build_client(session: FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def override_get_db():
        yield session

    app.dependency_overrides[original_get_db] = override_get_db
    return TestClient(app)


def test_review_queue_returns_items_needing_review(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.review.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.review.RawRecord", FakeRawRecordModel)
    monkeypatch.setattr("app.api.review.AIExtractionLog", FakeAIExtractionLogModel)

    response = client.get(f"/api/v1/crawl-jobs/{session.job.id}/review-queue?page=1&limit=50")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["fields_to_review"][0]["field_name"] == "email"
    assert payload["items"][0]["fields_to_review"][0]["suggested_value"] == "info@example.edu"
