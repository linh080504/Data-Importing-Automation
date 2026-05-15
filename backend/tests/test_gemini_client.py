import httpx
import pytest

from app.services.gemini_client import GeminiConfigurationError, GeminiRateLimitError, RotatingGeminiJSONClient


class FakeResponse:
    def __init__(self, *, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.request = httpx.Request("POST", "https://example.test")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=self.request, response=httpx.Response(self.status_code, request=self.request))

    def json(self) -> dict:
        return self._payload


def test_rotating_gemini_client_uses_next_key_on_429(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_post(url, *, params, json, timeout):
        del json, timeout
        model = url.split("/models/")[1].split(":generateContent")[0]
        calls.append((model, params["key"]))
        if params["key"] == "key-1":
            return FakeResponse(status_code=429)
        return FakeResponse(
            status_code=200,
            payload={"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]},
        )

    monkeypatch.setattr("app.services.gemini_client.httpx.post", fake_post)

    client = RotatingGeminiJSONClient(api_keys=["key-1", "key-2"], models=["gemini-2.0-flash"])

    assert client.generate_json(prompt="hello") == '{"ok": true}'
    assert calls == [("gemini-2.0-flash", "key-1"), ("gemini-2.0-flash", "key-2")]


def test_rotating_gemini_client_falls_back_to_next_model_on_404(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_post(url, *, params, json, timeout):
        del json, timeout
        model = url.split("/models/")[1].split(":generateContent")[0]
        calls.append((model, params["key"]))
        if model == "gemma-4-31b":
            return FakeResponse(status_code=404)
        return FakeResponse(
            status_code=200,
            payload={"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]},
        )

    monkeypatch.setattr("app.services.gemini_client.httpx.post", fake_post)

    client = RotatingGeminiJSONClient(api_keys=["key-1"], models=["gemma-4-31b", "gemini-2.0-flash"])

    assert client.generate_json(prompt="hello") == '{"ok": true}'
    assert calls == [("gemma-4-31b", "key-1"), ("gemini-2.0-flash", "key-1")]


def test_rotating_gemini_client_falls_back_to_next_model_when_all_keys_rate_limited(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_post(url, *, params, json, timeout):
        del json, timeout
        model = url.split("/models/")[1].split(":generateContent")[0]
        calls.append((model, params["key"]))
        if model == "gemma-4-31b":
            return FakeResponse(status_code=429)
        return FakeResponse(
            status_code=200,
            payload={"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]},
        )

    monkeypatch.setattr("app.services.gemini_client.httpx.post", fake_post)

    client = RotatingGeminiJSONClient(api_keys=["key-1", "key-2"], models=["gemma-4-31b", "gemini-2.0-flash"])

    assert client.generate_json(prompt="hello") == '{"ok": true}'
    assert calls == [
        ("gemma-4-31b", "key-1"),
        ("gemma-4-31b", "key-2"),
        ("gemini-2.0-flash", "key-1"),
    ]


def test_rotating_gemini_client_raises_rate_limit_error_when_all_models_and_keys_exhausted(monkeypatch) -> None:
    def fake_post(url, *, params, json, timeout):
        del url, params, json, timeout
        return FakeResponse(status_code=429)

    monkeypatch.setattr("app.services.gemini_client.httpx.post", fake_post)

    client = RotatingGeminiJSONClient(api_keys=["key-1", "key-2"], models=["gemma-4-31b", "gemini-2.0-flash"])

    with pytest.raises(GeminiRateLimitError) as exc_info:
        client.generate_json(prompt="hello")

    assert "rate-limited" in str(exc_info.value)


def test_rotating_gemini_client_does_not_rotate_non_429_non_model_error(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_post(url, *, params, json, timeout):
        del json, timeout
        model = url.split("/models/")[1].split(":generateContent")[0]
        calls.append((model, params["key"]))
        return FakeResponse(status_code=500)

    monkeypatch.setattr("app.services.gemini_client.httpx.post", fake_post)

    client = RotatingGeminiJSONClient(api_keys=["key-1", "key-2"], models=["gemma-4-31b", "gemini-2.0-flash"])

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        client.generate_json(prompt="hello")

    assert exc_info.value.response.status_code == 500
    assert calls == [("gemma-4-31b", "key-1")]


def test_rotating_gemini_client_requires_at_least_one_key() -> None:
    client = RotatingGeminiJSONClient(api_keys=[], models=["gemini-2.0-flash"])

    with pytest.raises(GeminiConfigurationError):
        client.generate_json(prompt="hello")


def test_rotating_gemini_client_requires_at_least_one_model() -> None:
    client = RotatingGeminiJSONClient(api_keys=["key-1"], models=[])

    with pytest.raises(GeminiConfigurationError):
        client.generate_json(prompt="hello")
