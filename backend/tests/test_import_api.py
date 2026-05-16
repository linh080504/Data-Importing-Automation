from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.import_api import get_db as original_get_db
from app.api.import_api import router


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


class FakeImportLogModel:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


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
        self.added = []
        self.committed = False
        self.refreshed = []

    def query(self, model):
        if model is FakeCrawlJobModel:
            return FakeQuery([self.job] if self.job is not None else [])
        if model is FakeCleanTemplateModel:
            return FakeQuery([self.template] if self.template is not None else [])
        if model is FakeImportLogModel:
            return FakeQuery(self.added)
        return FakeQuery(list(self.clean_records))

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.committed = True

    def refresh(self, item):
        self.refreshed.append(item)



def build_client(session: FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def override_get_db():
        yield session

    app.dependency_overrides[original_get_db] = override_get_db
    return TestClient(app)



def test_import_crawl_job_returns_counts_for_ready_job(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.import_api.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.import_api.CleanTemplate", FakeCleanTemplateModel)
    monkeypatch.setattr("app.api.import_api.CleanRecord", FakeCleanRecordModel)
    monkeypatch.setattr("app.api.import_api.ImportLog", FakeImportLogModel)

    response = client.post(f"/api/v1/crawl-jobs/{session.job.id}/import")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": session.job.id,
        "status": "COMPLETED",
        "message": "Import completed successfully",
        "inserted_records": 2,
        "updated_records": 0,
        "duplicate_records": 0,
        "total_records": 2,
        "imported_records": 2,
    }
    assert session.committed is True
    assert len(session.added) == 1
    assert session.added[0].target_system == "BeyondDegree"
    assert session.added[0].failed_records == 0
    assert session.added[0].error_summary == {"duplicates": 0, "total_records": 2}


def test_import_crawl_job_persists_import_log_for_ready_job(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.import_api.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.import_api.CleanTemplate", FakeCleanTemplateModel)
    monkeypatch.setattr("app.api.import_api.CleanRecord", FakeCleanRecordModel)
    monkeypatch.setattr("app.api.import_api.ImportLog", FakeImportLogModel)

    response = client.post(f"/api/v1/crawl-jobs/{session.job.id}/import")

    assert response.status_code == 200
    assert len(session.added) == 1
    assert session.added[0].target_system == "BeyondDegree"
    assert session.added[0].total_records == 2
    assert session.added[0].imported_records == 2
    assert session.added[0].failed_records == 0
    assert session.added[0].error_summary == {"duplicates": 0, "total_records": 2}
    assert session.refreshed == [session.added[0]]



def test_import_crawl_job_returns_404_when_job_missing(monkeypatch) -> None:
    session = FakeSession()
    session.job = None
    client = build_client(session)

    monkeypatch.setattr("app.api.import_api.CrawlJob", FakeCrawlJobModel)

    response = client.post(f"/api/v1/crawl-jobs/{uuid4()}/import")

    assert response.status_code == 404
    assert response.json()["detail"] == "Crawl job not found"



def test_import_crawl_job_returns_404_when_template_missing(monkeypatch) -> None:
    session = FakeSession()
    session.template = None
    client = build_client(session)

    monkeypatch.setattr("app.api.import_api.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.import_api.CleanTemplate", FakeCleanTemplateModel)

    response = client.post(f"/api/v1/crawl-jobs/{session.job.id}/import")

    assert response.status_code == 404
    assert response.json()["detail"] == "Clean template not found"



def test_import_crawl_job_returns_400_when_readiness_blockers_exist(monkeypatch) -> None:
    session = FakeSession()
    session.clean_records = [
        SimpleNamespace(
            job_id=session.job.id,
            unique_key="row-1",
            clean_payload={"name": "", "website": "https://example.edu", "slug": "example-university"},
        )
    ]
    client = build_client(session)

    monkeypatch.setattr("app.api.import_api.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.import_api.CleanTemplate", FakeCleanTemplateModel)
    monkeypatch.setattr("app.api.import_api.CleanRecord", FakeCleanRecordModel)
    monkeypatch.setattr("app.api.import_api.ImportLog", FakeImportLogModel)

    response = client.post(f"/api/v1/crawl-jobs/{session.job.id}/import")

    assert response.status_code == 400
    assert response.json()["detail"] == "Import readiness blockers must be resolved before importing"
