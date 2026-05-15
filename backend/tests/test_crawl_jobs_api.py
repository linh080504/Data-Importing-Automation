from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.crawl_jobs as crawl_jobs_module
from app.api.crawl_jobs import get_db as original_get_db
from app.api.crawl_jobs import router


class TestClientNoBackground(TestClient):
    def post(self, url, *args, **kwargs):
        json_payload = kwargs.get("json")
        if url == "/api/v1/crawl-jobs" and isinstance(json_payload, dict):
            json_payload = dict(json_payload)
            json_payload["crawl_mode"] = json_payload.get("crawl_mode", "trusted_sources")
            kwargs["json"] = json_payload
        return super().post(url, *args, **kwargs)


class ImmediateBackgroundTasks:
    def add_task(self, func, *args, **kwargs):
        return None


crawl_jobs_module.BackgroundTasks = ImmediateBackgroundTasks
crawl_jobs_module._run_job_background = lambda _job_id: None


class FilterField:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    def in_(self, values):
        return ("in", self.name, list(values))


class OrderField:
    def __init__(self, name: str):
        self.name = name

    def desc(self):
        return ("desc", self.name)


class FakeCleanTemplateModel:
    id = FilterField("id")


class FakeDataSourceModel:
    id = FilterField("id")


class FakeCrawlJobModel:
    id = FilterField("id")
    updated_at = OrderField("updated_at")


class FakeCleanRecordModel:
    job_id = FilterField("job_id")


class FakeCleanTemplateDetailModel:
    id = FilterField("id")
    template_name = FilterField("template_name")


class FakeDataSourceNamedModel:
    id = FilterField("id")
    source_name = FilterField("source_name")


class FakeCleanTemplateNamedModel:
    id = FilterField("id")
    template_name = FilterField("template_name")


class FakeRecord:
    def __init__(self, job_id: str, status: str, quality_score: int | None):
        self.job_id = job_id
        self.status = status
        self.quality_score = quality_score


class FakeTemplate:
    def __init__(self, id: str, template_name: str):
        self.id = id
        self.template_name = template_name


class FakeSource:
    def __init__(self, id: str, source_name: str):
        self.id = id
        self.source_name = source_name


class FakeJob:
    def __init__(self, *, id: str, country: str, status: str, source_ids: list[str], clean_template_id: str, progress: dict, updated_at, discovery_input=None, crawl_mode="trusted_sources"):
        self.id = id
        self.country = country
        self.status = status
        self.source_ids = source_ids
        self.clean_template_id = clean_template_id
        self.progress = progress
        self.updated_at = updated_at
        self.discovery_input = discovery_input
        self.crawl_mode = crawl_mode
        self.critical_fields = ["name", "location", "website"]


class FakeDateTime:
    def __init__(self, value: str):
        self.value = value

    def isoformat(self):
        return self.value


class FakeQuery:
    def __init__(self, items):
        self.items = list(items)

    def filter(self, condition):
        op, field_name, value = condition
        if op == "eq":
            self.items = [item for item in self.items if str(getattr(item, field_name)) == str(value)]
        elif op == "in":
            self.items = [item for item in self.items if str(getattr(item, field_name)) in {str(v) for v in value}]
        return self

    def order_by(self, _clause):
        if self.items and hasattr(self.items[0], "updated_at"):
            self.items = sorted(self.items, key=lambda item: item.updated_at.isoformat(), reverse=True)
        return self

    def all(self):
        return self.items

    def one_or_none(self):
        return self.items[0] if self.items else None


class FakeListSession:
    def __init__(self):
        self.template = FakeTemplate(str(uuid4()), "University_Import_Clean-7")
        self.sources = [
            FakeSource(str(uuid4()), "Government Registry"),
            FakeSource(str(uuid4()), "Business Directory"),
        ]
        self.jobs = [
            FakeJob(
                id=str(uuid4()),
                country="USA",
                status="READY_TO_EXPORT",
                source_ids=[self.sources[1].id],
                clean_template_id=self.template.id,
                progress={"total_records": 12, "crawled": 12, "extracted": 12, "needs_review": 0, "cleaned": 12},
                updated_at=FakeDateTime("2026-05-10T09:45:00Z"),
            ),
            FakeJob(
                id=str(uuid4()),
                country="Vietnam",
                status="NEEDS_REVIEW",
                source_ids=[self.sources[0].id],
                clean_template_id=self.template.id,
                progress={"total_records": 20, "crawled": 20, "extracted": 20, "needs_review": 4, "cleaned": 16},
                updated_at=FakeDateTime("2026-05-10T11:20:00Z"),
            ),
        ]
        self.clean_records = [
            FakeRecord(self.jobs[0].id, "READY_TO_EXPORT", 93),
            FakeRecord(self.jobs[1].id, "NEEDS_REVIEW", 70),
            FakeRecord(self.jobs[1].id, "READY_TO_EXPORT", 78),
        ]

    def query(self, model):
        if model in {FakeCleanTemplateModel, FakeCleanTemplateDetailModel, FakeCleanTemplateNamedModel}:
            return FakeQuery([self.template])
        if model in {FakeDataSourceModel, FakeDataSourceNamedModel}:
            return FakeQuery(list(self.sources))
        if model is FakeCleanRecordModel:
            return FakeQuery(list(self.clean_records))
        return FakeQuery(list(self.jobs))

    def add(self, obj):
        if not getattr(obj, "id", None):
            obj.id = str(uuid4())
        self.jobs.append(obj)

    def commit(self):
        return None

    def refresh(self, _obj):
        return None


class FakeSession:
    def __init__(self):
        self.template = SimpleNamespace(id=str(uuid4()))
        self.sources = [
            SimpleNamespace(id=str(uuid4())),
            SimpleNamespace(id=str(uuid4())),
        ]
        self.jobs = []

    def query(self, model):
        if model is FakeCleanTemplateModel:
            return FakeQuery([self.template])
        if model is FakeDataSourceModel:
            return FakeQuery(list(self.sources))
        return FakeQuery(list(self.jobs))

    def add(self, obj):
        if not getattr(obj, "id", None):
            obj.id = str(uuid4())
        self.jobs.append(obj)

    def commit(self):
        return None

    def refresh(self, _obj):
        return None


def build_client(session) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def override_get_db():
        yield session

    app.dependency_overrides[original_get_db] = override_get_db
    return TestClientNoBackground(app)


def test_create_crawl_job_returns_created_response(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.crawl_jobs.CleanTemplate", FakeCleanTemplateModel)
    monkeypatch.setattr("app.api.crawl_jobs.DataSource", FakeDataSourceModel)

    response = client.post(
        "/api/v1/crawl-jobs",
        json={
            "country": "Vietnam",
            "source_ids": [source.id for source in session.sources],
            "critical_fields": ["name", "location", "website"],
            "clean_template_id": session.template.id,
            "ai_assist": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "CRAWLING"


def test_create_supplemental_crawl_job_resolves_plan(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.crawl_jobs.CleanTemplate", FakeCleanTemplateModel)
    monkeypatch.setattr("app.api.crawl_jobs.DataSource", FakeDataSourceModel)
    monkeypatch.setattr("app.api.crawl_jobs.has_supplemental_coverage_plan", lambda country: country == "Vietnam")
    monkeypatch.setattr(
        "app.api.crawl_jobs.build_supplemental_discovery_input",
        lambda country: {
            "selected_source_ids": [],
            "supplemental_plan": {
                "country": country,
                "sources": [{"name": "Supplemental Vietnam Coverage"}],
            },
        },
    )

    response = client.post(
        "/api/v1/crawl-jobs",
        json={
            "country": "Vietnam",
            "crawl_mode": "supplemental_discovery",
            "source_ids": [],
            "discovery_input": {},
            "critical_fields": ["name", "location", "website"],
            "clean_template_id": session.template.id,
            "ai_assist": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["crawl_mode"] == "supplemental_discovery"
    assert payload["discovery_input"]["supplemental_plan"]["sources"][0]["name"] == "Supplemental Vietnam Coverage"


def test_create_supplemental_crawl_job_requires_plan(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.crawl_jobs.CleanTemplate", FakeCleanTemplateModel)
    monkeypatch.setattr("app.api.crawl_jobs.DataSource", FakeDataSourceModel)
    monkeypatch.setattr("app.api.crawl_jobs.has_supplemental_coverage_plan", lambda country: False)

    response = client.post(
        "/api/v1/crawl-jobs",
        json={
            "country": "Vietnam",
            "crawl_mode": "supplemental_discovery",
            "source_ids": [],
            "discovery_input": {},
            "critical_fields": ["name", "location", "website"],
            "clean_template_id": session.template.id,
            "ai_assist": True,
        },
    )

    assert response.status_code == 400
    assert "No supplemental coverage plan" in response.json()["detail"]


def test_create_crawl_job_rejects_invalid_source_ids(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.crawl_jobs.CleanTemplate", FakeCleanTemplateModel)
    monkeypatch.setattr("app.api.crawl_jobs.DataSource", FakeDataSourceModel)

    response = client.post(
        "/api/v1/crawl-jobs",
        json={
            "country": "Vietnam",
            "source_ids": [str(uuid4())],
            "critical_fields": ["name", "location", "website"],
            "clean_template_id": session.template.id,
            "ai_assist": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "One or more source_ids are invalid"


def test_create_crawl_job_resolves_country_plan_without_source_ids(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.crawl_jobs.CleanTemplate", FakeCleanTemplateModel)
    monkeypatch.setattr("app.api.crawl_jobs.DataSource", FakeDataSourceModel)

    response = client.post(
        "/api/v1/crawl-jobs",
        json={
            "country": "Vietnam",
            "source_ids": [],
            "critical_fields": ["name", "location", "website"],
            "clean_template_id": session.template.id,
            "ai_assist": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["crawl_mode"] == "trusted_sources"
    assert payload["discovery_input"]["source_plan"]["country"] == "Vietnam"
    assert len(payload["discovery_input"]["source_plan"]["sources"]) > 0


def test_list_crawl_jobs_returns_summary_items(monkeypatch) -> None:
    session = FakeListSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.crawl_jobs.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.crawl_jobs.CleanRecord", FakeCleanRecordModel)
    monkeypatch.setattr("app.api.crawl_jobs.CleanTemplate", FakeCleanTemplateNamedModel)
    monkeypatch.setattr("app.api.crawl_jobs.DataSource", FakeDataSourceNamedModel)

    response = client.get("/api/v1/crawl-jobs")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 2
    assert payload["items"][0]["country"] == "Vietnam"
    assert payload["items"][0]["source_names"] == ["Government Registry"]
    assert payload["items"][0]["template_name"] == "University_Import_Clean-7"
    assert payload["items"][0]["needs_review_count"] == 1
    assert payload["items"][0]["quality_score"] == 74


def test_get_crawl_job_returns_detail(monkeypatch) -> None:
    session = FakeListSession()
    job = session.jobs[1]
    client = build_client(session)

    monkeypatch.setattr("app.api.crawl_jobs.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.crawl_jobs.CleanRecord", FakeCleanRecordModel)
    monkeypatch.setattr("app.api.crawl_jobs.CleanTemplate", FakeCleanTemplateDetailModel)
    monkeypatch.setattr("app.api.crawl_jobs.DataSource", FakeDataSourceNamedModel)

    response = client.get(f"/api/v1/crawl-jobs/{job.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == job.id
    assert payload["country"] == "Vietnam"
    assert payload["status"] == "NEEDS_REVIEW"
    assert payload["source_names"] == ["Government Registry"]
    assert payload["template_name"] == "University_Import_Clean-7"
    assert payload["progress"]["total_records"] == 20
    assert payload["clean_records"] == 2
    assert payload["needs_review_count"] == 1
    assert payload["quality_score"] == 74
    assert payload["updated_at"] == "2026-05-10T11:20:00Z"
