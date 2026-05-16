from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.fields import router
from app.api.fields import get_db as original_get_db


class FakeTemplate:
    def __init__(self) -> None:
        self.id = str(uuid4())
        self.columns = [
            {"name": "id", "order": 1},
            {"name": "name", "order": 2},
            {"name": "location", "order": 3},
            {"name": "website", "order": 4},
            {"name": "slug", "order": 5},
            {"name": "description", "order": 6},
        ]


class FakeQuery:
    def __init__(self, template: FakeTemplate | None) -> None:
        self.template = template

    def filter(self, *_args, **_kwargs):
        return self

    def one_or_none(self):
        return self.template


class FakeSession:
    def __init__(self, template: FakeTemplate | None) -> None:
        self.template = template

    def query(self, _model):
        return FakeQuery(self.template)


def build_app(template: FakeTemplate | None) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def override_get_db():
        yield FakeSession(template)

    app.dependency_overrides[original_get_db] = override_get_db
    return TestClient(app)


def test_suggest_fields_returns_ranked_fields() -> None:
    template = FakeTemplate()
    client = build_app(template)

    response = client.get(f"/api/v1/fields/suggest/{template.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["template_id"] == template.id
    assert payload["template_columns"] == ["id", "name", "location", "website", "slug", "description"]
    assert "name" in payload["suggested_critical_fields"]
    assert payload["min_fields"] == 3
    assert payload["max_fields"] == 6


def test_suggest_fields_returns_404_for_missing_template() -> None:
    client = build_app(None)

    response = client.get(f"/api/v1/fields/suggest/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Template not found"
