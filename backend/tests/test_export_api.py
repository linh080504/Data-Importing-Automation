from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.export import router
from app.api.export import get_db as original_get_db


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
        self.job = SimpleNamespace(id=str(uuid4()), clean_template_id=str(uuid4()))
        self.template = SimpleNamespace(
            id=self.job.clean_template_id,
            template_name="University_Import_Clean-7",
            columns=[
                {"name": "name", "order": 1},
                {"name": "website", "order": 2},
            ],
        )
        self.clean_records = [
            SimpleNamespace(job_id=str(self.job.id), clean_payload={"name": "Example University", "website": "https://example.edu"}),
            SimpleNamespace(job_id="other-job", clean_payload={"name": "Other University", "website": "https://other.edu"}),
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



def test_export_crawl_job_returns_csv_metadata_for_requested_job(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    captured = {}

    def fake_export_clean_records_to_csv(clean_records, *, template_columns):
        captured["count"] = len(clean_records)
        captured["columns"] = template_columns
        return b"name,website\r\nExample University,https://example.edu\r\n"

    monkeypatch.setattr("app.api.export.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.export.CleanTemplate", FakeCleanTemplateModel)
    monkeypatch.setattr("app.api.export.CleanRecord", FakeCleanRecordModel)
    monkeypatch.setattr("app.api.export.export_clean_records_to_csv", fake_export_clean_records_to_csv)

    response = client.post(
        f"/api/v1/crawl-jobs/{session.job.id}/export",
        json={"format": "csv", "include_metadata": False},
    )

    assert response.status_code == 200
    assert captured["count"] == 1
    payload = response.json()
    assert payload == {
        "download_url": f"/exports/{session.job.id}_clean.csv",
        "schema_used": "University_Import_Clean-7",
        "total_exported": 1,
    }



def test_export_crawl_job_returns_404_when_job_missing(monkeypatch) -> None:
    session = FakeSession()
    session.job = None
    client = build_client(session)

    monkeypatch.setattr("app.api.export.CrawlJob", FakeCrawlJobModel)

    response = client.post(
        "/api/v1/crawl-jobs/missing/export",
        json={"format": "csv", "include_metadata": False},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Crawl job not found"



def test_export_crawl_job_returns_404_when_template_missing(monkeypatch) -> None:
    session = FakeSession()
    session.template = None
    client = build_client(session)

    monkeypatch.setattr("app.api.export.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.export.CleanTemplate", FakeCleanTemplateModel)

    response = client.post(
        f"/api/v1/crawl-jobs/{session.job.id}/export",
        json={"format": "csv", "include_metadata": False},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Clean template not found"



def test_export_crawl_job_returns_xlsx_metadata_for_requested_job(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    captured = {}

    def fake_export_clean_records_to_xlsx(clean_records, *, template_columns):
        captured["count"] = len(clean_records)
        captured["columns"] = template_columns
        return b"xlsx-bytes"

    monkeypatch.setattr("app.api.export.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.export.CleanTemplate", FakeCleanTemplateModel)
    monkeypatch.setattr("app.api.export.CleanRecord", FakeCleanRecordModel)
    monkeypatch.setattr("app.api.export.export_clean_records_to_xlsx", fake_export_clean_records_to_xlsx)

    response = client.post(
        f"/api/v1/crawl-jobs/{session.job.id}/export",
        json={"format": "xlsx", "include_metadata": False},
    )

    assert response.status_code == 200
    assert captured["count"] == 1
    payload = response.json()
    assert payload == {
        "download_url": f"/exports/{session.job.id}_clean.xlsx",
        "schema_used": "University_Import_Clean-7",
        "total_exported": 1,
    }



def test_export_crawl_job_accepts_include_metadata_flag(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    captured = {}

    def fake_export_clean_records_to_csv(clean_records, *, template_columns):
        captured["count"] = len(clean_records)
        captured["columns"] = template_columns
        return b"name,website\r\nExample University,https://example.edu\r\n"

    monkeypatch.setattr("app.api.export.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.export.CleanTemplate", FakeCleanTemplateModel)
    monkeypatch.setattr("app.api.export.CleanRecord", FakeCleanRecordModel)
    monkeypatch.setattr("app.api.export.export_clean_records_to_csv", fake_export_clean_records_to_csv)

    response = client.post(
        f"/api/v1/crawl-jobs/{session.job.id}/export",
        json={"format": "csv", "include_metadata": True},
    )

    assert response.status_code == 200
    assert captured["count"] == 1
    payload = response.json()
    assert payload == {
        "download_url": f"/exports/{session.job.id}_clean.csv",
        "schema_used": "University_Import_Clean-7",
        "total_exported": 1,
    }
