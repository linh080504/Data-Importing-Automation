from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.compare import router
from app.api.compare import get_db as original_get_db


class FilterField:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)


class FakeCrawlJobModel:
    id = FilterField("id")


class FakeRawRecordModel:
    job_id = FilterField("job_id")


class FakeCleanRecordModel:
    job_id = FilterField("job_id")


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *conditions):
        for condition in conditions:
            op, field_name, value = condition
            if op == "eq":
                self.items = [item for item in self.items if str(getattr(item, field_name)) == str(value)]
        return self

    def all(self):
        return self.items

    def one_or_none(self):
        return self.items[0] if self.items else None


class FakeSession:
    def __init__(self):
        self.job = SimpleNamespace(id=str(uuid4()))
        self.raw_records = [
            SimpleNamespace(
                id="raw_123",
                job_id=str(self.job.id),
                unique_key="uni_1",
                raw_payload={
                    "name": "Example University",
                    "email": "bad-email",
                    "website": "example.edu",
                },
            ),
            SimpleNamespace(
                id="raw_other",
                job_id="other-job",
                unique_key="uni_2",
                raw_payload={
                    "name": "Other University",
                },
            ),
        ]
        self.clean_records = [
            SimpleNamespace(
                job_id=str(self.job.id),
                raw_record_id="raw_123",
                unique_key="uni_1",
                clean_payload={
                    "name": "Example University",
                    "email": "info@example.edu",
                    "website": "https://example.edu",
                },
                quality_score=91,
                status="APPROVED",
            ),
            SimpleNamespace(
                job_id="other-job",
                raw_record_id="raw_other",
                unique_key="uni_2",
                clean_payload={
                    "name": "Other University",
                },
                quality_score=55,
                status="NEEDS_REVIEW",
            ),
        ]

    def query(self, model):
        if model is FakeCrawlJobModel:
            return FakeQuery([self.job] if self.job is not None else [])
        if model is FakeRawRecordModel:
            return FakeQuery(list(self.raw_records))
        if model is FakeCleanRecordModel:
            return FakeQuery(list(self.clean_records))
        return FakeQuery([])


def build_client(session: FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def override_get_db():
        yield session

    app.dependency_overrides[original_get_db] = override_get_db
    return TestClient(app)


def test_compare_returns_raw_and_clean_values(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.compare.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.compare.RawRecord", FakeRawRecordModel)
    monkeypatch.setattr("app.api.compare.CleanRecord", FakeCleanRecordModel)

    response = client.get(f"/api/v1/crawl-jobs/{session.job.id}/compare")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["raw_record_id"] == "raw_123"
    assert payload["items"][0]["unique_key"] == "uni_1"
    assert payload["items"][0]["unique_key"] == "uni_1"
    assert payload["items"][0]["status"] == "APPROVED"
    assert payload["items"][0]["quality_score"] == 91

    fields = {field["field_name"]: field for field in payload["items"][0]["fields"]}
    assert fields["email"]["raw_value"] == "bad-email"
    assert fields["email"]["clean_value"] == "info@example.edu"
    assert fields["website"]["raw_value"] == "example.edu"
    assert fields["website"]["clean_value"] == "https://example.edu"


def test_compare_returns_empty_when_job_missing(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.compare.CrawlJob", FakeCrawlJobModel)
    session.job = None

    response = client.get("/api/v1/crawl-jobs/missing/compare")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 0
    assert payload["items"] == []
