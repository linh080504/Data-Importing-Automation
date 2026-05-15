import httpx

from app.services.direct_run import _request_source_payload


class CaptureTransport(httpx.BaseTransport):
    def __init__(self) -> None:
        self.request_url = ""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.request_url = str(request.url)
        return httpx.Response(200, json=[])


def test_request_source_payload_preserves_query_string_without_config_params(monkeypatch) -> None:
    transport = CaptureTransport()

    def fake_request(method: str, url: str, **kwargs):
        with httpx.Client(transport=transport) as client:
            return client.request(method, url, **kwargs)

    monkeypatch.setattr("app.services.direct_run.httpx.request", fake_request)

    _request_source_payload(
        {
            "method": "GET",
            "url": "http://universities.hipolabs.com/search?country=Vietnam",
        }
    )

    assert transport.request_url == "http://universities.hipolabs.com/search?country=Vietnam"
