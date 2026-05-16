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
        self.raw_records = [
            SimpleNamespace(
                id="raw_123",
                job_id=self.job.id,
                unique_key="vietnam-national-university-hanoi",
                raw_payload={
                    "name": "Vietnam National University, Hanoi",
                    "description": "National research university in Hanoi.",
                    "website": "https://www.vnu.edu.vn",
                    "source_url": "https://en.wikipedia.org/wiki/Vietnam_National_University,_Hanoi",
                    "_merge": {"source_names": {"src_wikipedia": "Wikipedia universities by country index"}},
                },
            )
        ]
        self.logs = [
            SimpleNamespace(
                id=str(uuid4()),
                raw_record_id="raw_123",
                overall_confidence=78,
                processed_at=1,
                ai_1_payload={
                    "critical_fields": {
                        "email": {
                            "value": "bad-email",
                            "confidence": 0.62,
                            "source_excerpt": "Contact bad-email",
                            "evidence_url": "https://example.edu/contact",
                            "evidence_source": "official_site",
                            "evidence_required": True,
                        }
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
    assert payload["items"][0]["display_name"] == "Vietnam National University, Hanoi"
    assert payload["items"][0]["unique_key"] == "vietnam-national-university-hanoi"
    assert payload["items"][0]["source_url"] == "https://en.wikipedia.org/wiki/Vietnam_National_University,_Hanoi"
    assert payload["items"][0]["source_name"] == "Wikipedia universities by country index"
    crawled_fields = {field["field_name"]: field for field in payload["items"][0]["crawled_fields"]}
    assert crawled_fields["name"]["value"] == "Vietnam National University, Hanoi"
    assert crawled_fields["description"]["value"] == "National research university in Hanoi."
    assert crawled_fields["website"]["value"] == "https://www.vnu.edu.vn"
    assert crawled_fields["website"]["status"] == "captured"
    assert crawled_fields["email"]["value"] == "bad-email"
    assert crawled_fields["email"]["status"] == "needs_review"
    assert crawled_fields["email"]["reason"] == "Invalid format"
    assert payload["items"][0]["fields_to_review"][0]["field_name"] == "email"
    assert payload["items"][0]["fields_to_review"][0]["suggested_value"] == "info@example.edu"
    assert payload["items"][0]["fields_to_review"][0]["source_excerpt"] == "Contact bad-email"
    assert payload["items"][0]["fields_to_review"][0]["evidence_url"] == "https://example.edu/contact"
    assert payload["items"][0]["fields_to_review"][0]["evidence_source"] == "official_site"
    assert payload["items"][0]["fields_to_review"][0]["evidence_required"] is True


def test_review_queue_total_counts_all_review_items_when_paginated(monkeypatch) -> None:
    session = FakeSession()
    session.raw_records.append(
        SimpleNamespace(
            id="raw_456",
            job_id=session.job.id,
            unique_key="can-tho-university",
            raw_payload={"name": "Can Tho University", "source_url": "https://en.wikipedia.org/wiki/Can_Tho_University"},
        )
    )
    session.logs.append(
        SimpleNamespace(
            id=str(uuid4()),
            raw_record_id="raw_456",
            overall_confidence=66,
            processed_at=2,
            ai_1_payload={"critical_fields": {"website": {"value": None, "confidence": 0.0}}},
            ai_2_validation={
                "judge_output": {
                    "fields_validation": {
                        "website": {
                            "is_correct": False,
                            "corrected_value": None,
                            "confidence": 0,
                            "reason": "Required field is missing",
                        }
                    }
                }
            },
        )
    )
    client = build_client(session)

    monkeypatch.setattr("app.api.review.CrawlJob", FakeCrawlJobModel)
    monkeypatch.setattr("app.api.review.RawRecord", FakeRawRecordModel)
    monkeypatch.setattr("app.api.review.AIExtractionLog", FakeAIExtractionLogModel)

    response = client.get(f"/api/v1/crawl-jobs/{session.job.id}/review-queue?page=1&limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 1
