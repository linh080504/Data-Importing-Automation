from contextlib import contextmanager
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.internal import router
from app.api.internal import get_db as original_get_db


class FakeSession:
    pass


@contextmanager
def override_settings(secret: str | None, enabled: bool = True, header_name: str = "X-N8N-Secret"):
    from app.api import internal

    original = internal.get_settings
    internal.get_settings = lambda: SimpleNamespace(
        internal_webhook_enabled=enabled,
        n8n_webhook_secret=secret,
        n8n_callback_header=header_name,
        n8n_allowed_content_type="application/json",
    )
    try:
        yield
    finally:
        internal.get_settings = original


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def override_get_db():
        yield FakeSession()

    app.dependency_overrides[original_get_db] = override_get_db
    return TestClient(app)


BASE_PAYLOAD = {
    "job_id": "job_1",
    "source_id": "src_1",
    "unique_key": "uni_1",
    "record_hash": "hash_1",
    "raw_payload": {"name": "Example"},
    "critical_fields_extracted": {"name": "Example"},
    "overall_confidence": 92,
    "status": "APPROVED",
}


def test_internal_webhook_rejects_when_secret_missing() -> None:
    client = build_client()

    with override_settings(secret=None):
        response = client.post("/api/v1/internal/webhook/n8n/upsert-record", json=BASE_PAYLOAD)

    assert response.status_code == 503
    assert response.json()["detail"] == "Internal webhook secret is not configured"


def test_internal_webhook_rejects_when_header_missing() -> None:
    client = build_client()

    with override_settings(secret="topsecret"):
        response = client.post("/api/v1/internal/webhook/n8n/upsert-record", json=BASE_PAYLOAD)

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing webhook secret"


def test_internal_webhook_rejects_when_content_type_invalid() -> None:
    client = build_client()

    with override_settings(secret="topsecret"):
        response = client.post(
            "/api/v1/internal/webhook/n8n/upsert-record",
            headers={"X-N8N-Secret": "topsecret", "Content-Type": "text/plain"},
            content="not-json",
        )

    assert response.status_code == 422


def test_internal_webhook_returns_process_hint_for_changed_record(monkeypatch) -> None:
    client = build_client()

    def fake_upsert_raw_record(db, *, job_id, source_id, unique_key, raw_payload, record_hash):
        assert job_id == "job_1"
        assert source_id == "src_1"
        assert unique_key == "uni_1"
        assert raw_payload == {"name": "Example"}
        assert record_hash == "hash_1"
        return SimpleNamespace(raw_record_id="raw_123", action="INSERTED", changed=True)

    monkeypatch.setattr("app.api.internal.upsert_raw_record", fake_upsert_raw_record)

    with override_settings(secret="topsecret"):
        response = client.post(
            "/api/v1/internal/webhook/n8n/upsert-record",
            headers={"X-N8N-Secret": "topsecret"},
            json=BASE_PAYLOAD,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "UPSERT_APPROVED"
    assert payload["ingest_action"] == "INSERTED"
    assert payload["raw_record_id"] == "raw_123"
    assert payload["changed"] is True
    assert payload["should_process_ai"] is True


def test_internal_webhook_skips_ai_when_record_unchanged(monkeypatch) -> None:
    client = build_client()

    def fake_upsert_raw_record(db, *, job_id, source_id, unique_key, raw_payload, record_hash):
        return SimpleNamespace(raw_record_id="raw_123", action="NO_CHANGE", changed=False)

    monkeypatch.setattr("app.api.internal.upsert_raw_record", fake_upsert_raw_record)

    with override_settings(secret="topsecret"):
        response = client.post(
            "/api/v1/internal/webhook/n8n/upsert-record",
            headers={"X-N8N-Secret": "topsecret"},
            json=BASE_PAYLOAD,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "SKIP_AI_NO_CHANGE"
    assert payload["ingest_action"] == "NO_CHANGE"
    assert payload["changed"] is False
    assert payload["should_process_ai"] is False


def test_internal_webhook_rejects_when_secret_invalid() -> None:
    client = build_client()

    with override_settings(secret="topsecret"):
        response = client.post(
            "/api/v1/internal/webhook/n8n/upsert-record",
            headers={"X-N8N-Secret": "wrongsecret"},
            json=BASE_PAYLOAD,
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid webhook secret"



def test_internal_webhook_error_responses_do_not_echo_secret_values() -> None:
    client = build_client()

    configured_secret = "topsecret"
    provided_secret = "wrongsecret"

    with override_settings(secret=configured_secret):
        response = client.post(
            "/api/v1/internal/webhook/n8n/upsert-record",
            headers={"X-N8N-Secret": provided_secret},
            json=BASE_PAYLOAD,
        )

    payload = response.json()
    assert response.status_code == 401
    assert configured_secret not in str(payload)
    assert provided_secret not in str(payload)



def test_internal_webhook_success_response_does_not_echo_auth_header(monkeypatch) -> None:
    client = build_client()

    def fake_upsert_raw_record(db, *, job_id, source_id, unique_key, raw_payload, record_hash):
        return SimpleNamespace(raw_record_id="raw_123", action="INSERTED", changed=True)

    monkeypatch.setattr("app.api.internal.upsert_raw_record", fake_upsert_raw_record)

    with override_settings(secret="topsecret"):
        response = client.post(
            "/api/v1/internal/webhook/n8n/upsert-record",
            headers={"X-N8N-Secret": "topsecret"},
            json=BASE_PAYLOAD,
        )

    payload = response.json()
    assert response.status_code == 200
    assert "topsecret" not in str(payload)
    assert "X-N8N-Secret" not in str(payload)
