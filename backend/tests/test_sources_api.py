from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.sources import router
from app.api.sources import get_db as original_get_db


class FakeQuery:
    def __init__(self, session, items):
        self.session = session
        self.items = items

    def filter(self, predicate):
        value = predicate.right.value
        self.items = [item for item in self.items if item.country == value or str(item.id) == value]
        return self

    def order_by(self, *_args, **_kwargs):
        self.items = sorted(self.items, key=lambda item: item.source_name)
        return self

    def all(self):
        return self.items

    def one_or_none(self):
        return self.items[0] if self.items else None


class FakeSession:
    def __init__(self):
        self.sources = [
            SimpleNamespace(
                id=str(uuid4()),
                country="Vietnam",
                source_name="Government Registry",
                supported_fields=["name", "tax_code"],
                config={"base_url": "https://example.gov.vn"},
                critical_fields=["name", "tax_code"],
            ),
            SimpleNamespace(
                id=str(uuid4()),
                country="Thailand",
                source_name="Business Directory",
                supported_fields=["name", "phone"],
                config=None,
                critical_fields=None,
            ),
        ]

    def query(self, _model):
        return FakeQuery(self, list(self.sources))

    def add(self, source):
        if not getattr(source, "id", None):
            source.id = str(uuid4())
        self.sources.append(source)

    def commit(self):
        return None

    def refresh(self, _source):
        return None


def build_client(session: FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def override_get_db():
        yield session

    app.dependency_overrides[original_get_db] = override_get_db
    return TestClient(app)


def test_list_sources_filters_by_country() -> None:
    client = build_client(FakeSession())

    response = client.get("/api/v1/sources", params={"country": "Vietnam"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["sources"]) == 1
    assert payload["sources"][0]["name"] == "Government Registry"


def test_create_source_returns_created_source() -> None:
    client = build_client(FakeSession())

    response = client.post(
        "/api/v1/sources",
        json={
            "country": "Indonesia",
            "source_name": "Campus Portal",
            "supported_fields": ["name", "website"],
            "config": {"base_url": "https://portal.example.id"},
            "critical_fields": ["name", "website"],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["country"] == "Indonesia"
    assert payload["supported_fields"] == ["name", "website"]


def test_update_source_returns_updated_source() -> None:
    session = FakeSession()
    client = build_client(session)
    source_id = session.sources[0].id

    response = client.put(
        f"/api/v1/sources/{source_id}",
        json={
            "source_name": "National Registry",
            "supported_fields": ["name", "website"],
            "config": {"base_url": "https://registry.example.vn"},
            "critical_fields": ["name"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == source_id
    assert payload["source_name"] == "National Registry"
    assert payload["supported_fields"] == ["name", "website"]
    assert payload["config"] == {"base_url": "https://registry.example.vn"}
    assert payload["critical_fields"] == ["name"]


def test_update_source_returns_404_when_missing() -> None:
    client = build_client(FakeSession())

    response = client.put(f"/api/v1/sources/{uuid4()}", json={"source_name": "Updated"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Source not found"
