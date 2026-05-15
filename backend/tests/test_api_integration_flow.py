from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db as original_get_db


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
    template_name = FilterField("template_name")


class FakeDataSourceModel:
    id = FilterField("id")
    source_name = FilterField("source_name")


class FakeCrawlJobModel:
    id = FilterField("id")
    updated_at = OrderField("updated_at")

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        if "id" not in self.__dict__:
            self.id = str(uuid4())
        if "updated_at" not in self.__dict__:
            self.updated_at = FakeDateTime("2026-05-11T10:00:00Z")

    def __getattribute__(self, name):
        if name in {"id", "updated_at"}:
            data = object.__getattribute__(self, "__dict__")
            if name in data:
                return data[name]
        return object.__getattribute__(self, name)


class FakeAIExtractionLogModel:
    id = FilterField("id")
    processed_at = OrderField("processed_at")


class FakeCleanRecordModel:
    job_id = FilterField("job_id")
    raw_record_id = FilterField("raw_record_id")


class FakeRawRecordModel:
    job_id = FilterField("job_id")


class FakeReviewActionModel:
    def __init__(self, *, clean_record_id, reviewer_id, old_value, new_value, action, note):
        self.id = str(uuid4())
        self.clean_record_id = clean_record_id
        self.reviewer_id = reviewer_id
        self.old_value = old_value
        self.new_value = new_value
        self.action = action
        self.note = note


class FakeDateTime:
    def __init__(self, value: str):
        self.value = value

    def isoformat(self):
        return self.value


class FakeQuery:
    def __init__(self, items):
        self.items = list(items)

    def filter(self, *conditions):
        for condition in conditions:
            op, field_name, value = condition
            if op == "eq":
                self.items = [item for item in self.items if str(getattr(item, field_name)) == str(value)]
            elif op == "in":
                allowed = {str(v) for v in value}
                self.items = [item for item in self.items if str(getattr(item, field_name)) in allowed]
        return self

    def order_by(self, _clause):
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
        self.template = SimpleNamespace(
            id=str(uuid4()),
            template_name="University_Import_Clean-7",
            columns=[
                {"name": "name", "order": 1},
                {"name": "email", "order": 2},
                {"name": "website", "order": 3},
            ],
        )
        self.sources = [
            SimpleNamespace(id=str(uuid4()), source_name="Government Registry"),
        ]
        self.jobs = []
        self.logs = []
        self.raw_records = []
        self.clean_records = []
        self.review_actions = []

    def query(self, model):
        if model is FakeCleanTemplateModel:
            return FakeQuery([self.template] if self.template is not None else [])
        if model is FakeDataSourceModel:
            return FakeQuery(list(self.sources))
        if model is FakeCrawlJobModel:
            return FakeQuery(list(self.jobs))
        if model is FakeAIExtractionLogModel:
            return FakeQuery(list(self.logs))
        if model is FakeCleanRecordModel:
            return FakeQuery(list(self.clean_records))
        if model is FakeRawRecordModel:
            return FakeQuery(list(self.raw_records))
        return FakeQuery(list(self.review_actions))

    def add(self, obj):
        if not getattr(obj, "id", None):
            obj.id = str(uuid4())

        if hasattr(obj, "country") and hasattr(obj, "source_ids"):
            if not getattr(obj, "updated_at", None):
                obj.updated_at = FakeDateTime("2026-05-11T10:00:00Z")
            self.jobs.append(obj)
            self._seed_records_for_job(obj)
            return

        if hasattr(obj, "action") and hasattr(obj, "clean_record_id"):
            self.review_actions.append(obj)
            return

        if obj not in self.clean_records and hasattr(obj, "clean_payload") and hasattr(obj, "raw_record_id"):
            self.clean_records.append(obj)

    def commit(self):
        return None

    def refresh(self, _obj):
        return None

    def _seed_records_for_job(self, job):
        raw_record_id = f"raw_{job.id}"
        self.raw_records.append(
            SimpleNamespace(
                id=raw_record_id,
                job_id=str(job.id),
                unique_key="uni_1",
                raw_payload={
                    "name": "Example University",
                    "email": "bad-email",
                    "website": "example.edu",
                },
            )
        )
        self.logs.append(
            SimpleNamespace(
                id=f"log_{job.id}",
                raw_record_id=raw_record_id,
                processed_at=1,
                overall_confidence=78,
                ai_1_payload={
                    "critical_fields": {
                        "email": {"value": "bad-email"},
                        "website": {"value": "example.edu"},
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
                            },
                            "website": {
                                "is_correct": False,
                                "corrected_value": "https://example.edu",
                                "confidence": 80,
                                "reason": "Missing scheme",
                            },
                        }
                    }
                },
            )
        )
        self.clean_records.append(
            SimpleNamespace(
                id=f"clean_{job.id}",
                job_id=str(job.id),
                raw_record_id=raw_record_id,
                unique_key="uni_1",
                clean_payload={
                    "name": "Example University",
                    "email": "bad-email",
                    "website": "example.edu",
                },
                quality_score=78,
                status="NEEDS_REVIEW",
            )
        )


def build_client(session: FakeSession) -> TestClient:
    def override_get_db():
        yield session

    app.dependency_overrides[original_get_db] = override_get_db
    return TestClient(app)


def test_full_api_flow_from_job_creation_through_export(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.crawl_jobs.CleanTemplate", FakeCleanTemplateModel)
    monkeypatch.setattr("app.api.crawl_jobs.DataSource", FakeDataSourceModel)
    monkeypatch.setattr("app.api.crawl_jobs.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.crawl_jobs.CleanRecord", FakeCleanRecordModel)

    monkeypatch.setattr("app.api.review.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.review.AIExtractionLog", FakeAIExtractionLogModel)

    monkeypatch.setattr("app.api.review_actions.AIExtractionLog", FakeAIExtractionLogModel)
    monkeypatch.setattr("app.api.review_actions.CleanRecord", FakeCleanRecordModel)
    monkeypatch.setattr("app.api.review_actions.ReviewAction", FakeReviewActionModel)

    monkeypatch.setattr("app.api.compare.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.compare.RawRecord", FakeRawRecordModel)
    monkeypatch.setattr("app.api.compare.CleanRecord", FakeCleanRecordModel)

    monkeypatch.setattr("app.api.export.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.export.CleanTemplate", FakeCleanTemplateModel)
    monkeypatch.setattr("app.api.export.CleanRecord", FakeCleanRecordModel)

    create_response = client.post(
        "/api/v1/crawl-jobs",
        json={
            "country": "Vietnam",
            "source_ids": [session.sources[0].id],
            "critical_fields": ["name", "email", "website"],
            "clean_template_id": session.template.id,
            "ai_assist": True,
        },
    )

    assert create_response.status_code == 201
    created_job_id = create_response.json()["job_id"]

    detail_response = client.get(f"/api/v1/crawl-jobs/{created_job_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["job_id"] == created_job_id

    review_response = client.get(f"/api/v1/crawl-jobs/{created_job_id}/review-queue?page=1&limit=50")
    assert review_response.status_code == 200
    review_payload = review_response.json()
    assert review_payload["total"] == 1
    assert review_payload["items"][0]["fields_to_review"][0]["field_name"] == "email"

    record_id = review_payload["items"][0]["record_id"]
    review_action_response = client.post(
        "/api/v1/review-actions",
        json={
            "record_id": record_id,
            "field_name": "email",
            "action": "EDIT",
            "new_value": "info@example.edu",
            "note": "Corrected in review",
        },
    )
    assert review_action_response.status_code == 200
    assert session.clean_records[0].clean_payload["email"] == "info@example.edu"
    assert session.clean_records[0].status == "REVIEWED"

    compare_response = client.get(f"/api/v1/crawl-jobs/{created_job_id}/compare")
    assert compare_response.status_code == 200
    compare_payload = compare_response.json()
    assert compare_payload["total"] == 1
    fields = {field["field_name"]: field for field in compare_payload["items"][0]["fields"]}
    assert fields["email"]["raw_value"] == "bad-email"
    assert fields["email"]["clean_value"] == "info@example.edu"

    export_response = client.post(
        f"/api/v1/crawl-jobs/{created_job_id}/export",
        json={"format": "csv", "include_metadata": False},
    )
    assert export_response.status_code == 200
    assert export_response.json() == {
        "download_url": f"/exports/{created_job_id}_clean.csv",
        "schema_used": "University_Import_Clean-7",
        "total_exported": 1,
    }


def test_full_api_flow_returns_empty_review_and_compare_for_missing_job(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.review.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.review.AIExtractionLog", FakeAIExtractionLogModel)
    monkeypatch.setattr("app.api.compare.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.compare.RawRecord", FakeRawRecordModel)
    monkeypatch.setattr("app.api.compare.CleanRecord", FakeCleanRecordModel)

    review_response = client.get("/api/v1/crawl-jobs/missing/review-queue?page=1&limit=50")
    compare_response = client.get("/api/v1/crawl-jobs/missing/compare")

    assert review_response.status_code == 200
    assert review_response.json() == {"total": 0, "page": 1, "limit": 50, "items": []}
    assert compare_response.status_code == 200
    assert compare_response.json() == {"total": 0, "items": []}
