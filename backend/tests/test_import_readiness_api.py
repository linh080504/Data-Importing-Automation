from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.import_readiness import get_db as original_get_db
from app.api.import_readiness import router


class FilterField:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)


class FakeCrawlJobModel:
    id = FilterField("id")


class FakeCleanTemplateModel:
    id = FilterField("id")


class FakeCleanRecordModel:
    job_id = FilterField("job_id")


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

    def all(self):
        return self.items


class FakeSession:
    def __init__(self):
        self.job = SimpleNamespace(
            id=str(uuid4()),
            clean_template_id=str(uuid4()),
            critical_fields=["name", "website"],
        )
        self.template = SimpleNamespace(
            id=self.job.clean_template_id,
            columns=[
                {"name": "name", "order": 1},
                {"name": "website", "order": 2},
                {"name": "slug", "order": 3},
            ],
        )
        self.clean_records = [
            SimpleNamespace(
                job_id=self.job.id,
                unique_key="row-1",
                clean_payload={"name": "Example University", "website": "https://example.edu", "slug": "example-university"},
            ),
            SimpleNamespace(
                job_id=self.job.id,
                unique_key="row-2",
                clean_payload={"name": "Sample Institute", "website": "https://sample.edu", "slug": "sample-institute"},
            ),
        ]

    def query(self, model):
        if model is FakeCrawlJobModel:
            return FakeQuery([self.job] if self.job is not None else [])
        if model is FakeCleanTemplateModel:
            return FakeQuery([self.template] if self.template is not None else [])
        return FakeQuery(list(self.clean_records))



def build_client(session: FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def override_get_db():
        yield session

    app.dependency_overrides[original_get_db] = override_get_db
    return TestClient(app)



def test_import_readiness_returns_ready_for_valid_job(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.import_readiness.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.import_readiness.CleanTemplate", FakeCleanTemplateModel)
    monkeypatch.setattr("app.api.import_readiness.CleanRecord", FakeCleanRecordModel)

    response = client.get(f"/api/v1/crawl-jobs/{session.job.id}/import-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_ready"] is True
    assert payload["blockers"] == []



def test_import_readiness_returns_blockers_for_missing_required_and_schema_mismatch(monkeypatch) -> None:
    session = FakeSession()
    session.clean_records = [
        SimpleNamespace(
            job_id=session.job.id,
            unique_key="row-1",
            clean_payload={"name": "Example University", "website": "", "extra_field": "unexpected"},
        )
    ]
    client = build_client(session)

    monkeypatch.setattr("app.api.import_readiness.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.import_readiness.CleanTemplate", FakeCleanTemplateModel)
    monkeypatch.setattr("app.api.import_readiness.CleanRecord", FakeCleanRecordModel)

    response = client.get(f"/api/v1/crawl-jobs/{session.job.id}/import-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_ready"] is False
    blockers = {item["key"]: item["count"] for item in payload["blockers"]}
    assert blockers["required_critical_fields"] == 1
    assert "schema_match" not in blockers



def test_import_readiness_returns_404_when_job_missing(monkeypatch) -> None:
    session = FakeSession()
    session.job = None
    client = build_client(session)

    monkeypatch.setattr("app.api.import_readiness.CrawlJob", FakeCrawlJobModel)

    response = client.get(f"/api/v1/crawl-jobs/{uuid4()}/import-readiness")

    assert response.status_code == 404
    assert response.json()["detail"] == "Crawl job not found"
