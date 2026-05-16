from types import SimpleNamespace

import httpx
import pytest

from app.schemas.ai_output import AIExtractorOutput, AIJudgeOutput
from app.services.direct_run import DirectRunError, _merge_prepared_sources, _resolved_plan_sources, fetch_source_rows, prepare_source_rows, run_crawl_job_direct
from app.services.gemini_client import GeminiRateLimitError


class FilterField:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    def in_(self, values):
        return ("in", self.name, list(values))


class FakeDataSourceModel:
    id = FilterField("id")


class FakeRawRecordModel:
    id = FilterField("id")


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

    def all(self):
        return self.items

    def one_or_none(self):
        return self.items[0] if self.items else None


class FakeSession:
    def __init__(self, *, sources=None):
        self.sources = list(sources or [])
        self.raw_records = []
        self.clean_records = []
        self.commits = 0

    def query(self, model):
        if model is FakeDataSourceModel:
            return FakeQuery(self.sources)
        if model is FakeRawRecordModel:
            return FakeQuery(self.raw_records)
        return FakeQuery([])

    def add(self, obj):
        if hasattr(obj, "raw_payload") and obj not in self.raw_records:
            self.raw_records.append(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        return None

    def refresh(self, _obj):
        return None


@pytest.fixture
def job():
    return SimpleNamespace(
        id="job_1",
        country="Vietnam",
        source_ids=["src_1"],
        critical_fields=["name", "website", "email"],
        ai_assist=True,
        status="QUEUED",
        progress={
            "total_records": 0,
            "crawled": 0,
            "extracted": 0,
            "needs_review": 0,
            "cleaned": 0,
        },
    )


def test_fetch_source_rows_supports_items_path(monkeypatch) -> None:
    source = SimpleNamespace(config={"source_type": "json_api", "url": "https://example.edu/api", "items_path": "payload.rows"})

    monkeypatch.setattr(
        "app.services.direct_run.httpx.request",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"payload": {"rows": [{"id": 1, "name": "Example"}]}}
        ),
    )

    rows = fetch_source_rows(source)

    assert rows == [{"id": 1, "name": "Example"}]


def test_fetch_source_rows_requires_url() -> None:
    with pytest.raises(DirectRunError):
        fetch_source_rows(SimpleNamespace(config={"source_type": "json_api"}))


def test_fetch_source_rows_applies_field_map(monkeypatch) -> None:
    source = SimpleNamespace(
        config={
            "source_type": "json_api",
            "url": "https://example.edu/api",
            "items_path": "data",
            "field_map": {
                "name": "agency_name",
                "website": "website_url",
                "email": ["public_email", "contact_email"],
            },
        }
    )

    monkeypatch.setattr(
        "app.services.direct_run.httpx.request",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "data": [
                    {
                        "id": 1,
                        "agency_name": "Example Agency",
                        "website_url": "https://agency.gov",
                        "contact_email": "contact@agency.gov",
                    }
                ]
            },
        ),
    )

    rows = fetch_source_rows(source)

    assert rows == [
        {
            "id": 1,
            "agency_name": "Example Agency",
            "website_url": "https://agency.gov",
            "contact_email": "contact@agency.gov",
            "name": "Example Agency",
            "website": "https://agency.gov",
            "email": "contact@agency.gov",
        }
    ]


def test_prepare_source_rows_keeps_raw_payload_but_normalizes_ai_values(monkeypatch) -> None:
    source = SimpleNamespace(
        config={
            "source_type": "json_api",
            "url": "https://example.edu/api",
            "items_path": "data",
            "unique_key_field": "agency_id",
            "text_field": "summary",
            "field_map": {"name": "agency_name"},
        }
    )

    monkeypatch.setattr(
        "app.services.direct_run.httpx.request",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "data": [
                    {
                        "agency_id": "ag_1",
                        "agency_name": "Example Agency",
                        "summary": "Example Agency official summary",
                    }
                ]
            },
        ),
    )

    prepared = prepare_source_rows(source)

    assert prepared.source_type == "json_api"
    assert prepared.rows[0].unique_key == "ag_1"
    assert prepared.rows[0].raw_payload == {
        "agency_id": "ag_1",
        "agency_name": "Example Agency",
        "summary": "Example Agency official summary",
    }
    assert prepared.rows[0].normalized["name"] == "Example Agency"
    assert prepared.rows[0].raw_text == "Example Agency official summary"


def test_fetch_source_rows_rejects_invalid_field_map() -> None:
    with pytest.raises(DirectRunError):
        fetch_source_rows(
            SimpleNamespace(
                config={
                    "source_type": "json_api",
                    "url": "https://example.edu/api",
                    "field_map": ["not", "an", "object"],
                }
            )
        )


def test_fetch_source_rows_rejects_unsupported_source_type() -> None:
    with pytest.raises(DirectRunError):
        fetch_source_rows(SimpleNamespace(config={"source_type": "html_page", "url": "https://example.edu"}))


def test_fetch_source_rows_maps_upstream_http_errors(monkeypatch) -> None:
    request = httpx.Request("GET", "https://example.edu/api")
    response = httpx.Response(503, request=request)
    source = SimpleNamespace(config={"source_type": "json_api", "url": "https://example.edu/api"})

    def raise_http_status(*args, **kwargs):
        raise httpx.HTTPStatusError("boom", request=request, response=response)

    monkeypatch.setattr("app.services.direct_run.httpx.request", raise_http_status)

    with pytest.raises(DirectRunError) as exc_info:
        fetch_source_rows(source)

    assert "HTTP 503" in str(exc_info.value)


def test_fetch_source_rows_rejects_non_json_response(monkeypatch) -> None:
    source = SimpleNamespace(config={"source_type": "json_api", "url": "https://example.edu/api"})

    monkeypatch.setattr(
        "app.services.direct_run.httpx.request",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: (_ for _ in ()).throw(ValueError("not json")),
        ),
    )

    with pytest.raises(DirectRunError) as exc_info:
        fetch_source_rows(source)

    assert "not valid JSON" in str(exc_info.value)


def test_merge_prepared_sources_prefers_primary_and_fills_missing_values() -> None:
    merged = _merge_prepared_sources(
        [
            (
                SimpleNamespace(id="src_primary"),
                SimpleNamespace(
                    source_type="json_api",
                    rows=[
                        SimpleNamespace(
                            normalized={"name": "Primary University", "website": None, "email": "info@primary.edu"},
                            raw_payload={"name": "Primary University", "website": None, "email": "info@primary.edu"},
                            raw_text="Primary row",
                            unique_key="uni_1",
                        )
                    ],
                ),
            ),
            (
                SimpleNamespace(id="src_secondary"),
                SimpleNamespace(
                    source_type="json_api",
                    rows=[
                        SimpleNamespace(
                            normalized={"name": "Secondary University", "website": "https://secondary.edu", "email": "contact@secondary.edu"},
                            raw_payload={"name": "Secondary University", "website": "https://secondary.edu", "email": "contact@secondary.edu"},
                            raw_text="Secondary row",
                            unique_key="uni_1",
                        )
                    ],
                ),
            ),
        ]
    )

    assert len(merged) == 1
    assert merged[0].source_id == "src_primary"
    assert merged[0].normalized["name"] == "Primary University"
    assert merged[0].normalized["website"] == "https://secondary.edu"
    assert merged[0].normalized["email"] == "info@primary.edu"
    assert merged[0].raw_payload["sources"] == {
        "src_primary": {"name": "Primary University", "website": None, "email": "info@primary.edu"},
        "src_secondary": {"name": "Secondary University", "website": "https://secondary.edu", "email": "contact@secondary.edu"},
    }
    assert merged[0].raw_payload["_merge"]["field_sources"] == {
        "name": "src_primary",
        "website": "src_secondary",
        "email": "src_primary",
    }
    assert merged[0].raw_payload["_merge"]["conflicts"]["name"][0]["source_id"] == "src_secondary"
    assert merged[0].raw_payload["_merge"]["conflicts"]["email"][0]["source_id"] == "src_secondary"
    assert merged[0].raw_text == "Primary row\n\nSecondary row"


def test_merge_prepared_sources_matches_source_specific_keys_by_name() -> None:
    merged = _merge_prepared_sources(
        [
            (
                SimpleNamespace(id="src_wikipedia"),
                SimpleNamespace(
                    source_type="discovery_bundle",
                    rows=[
                        SimpleNamespace(
                            normalized={
                                "name": "Vietnam National University, Hanoi",
                                "country": "Vietnam",
                                "source_url": "https://en.wikipedia.org/wiki/Vietnam_National_University,_Hanoi",
                            },
                            raw_payload={
                                "name": "Vietnam National University, Hanoi",
                                "country": "Vietnam",
                                "source_url": "https://en.wikipedia.org/wiki/Vietnam_National_University,_Hanoi",
                            },
                            raw_text="Wikipedia row",
                            unique_key="https://en.wikipedia.org/wiki/Vietnam_National_University,_Hanoi",
                        )
                    ],
                ),
            ),
            (
                SimpleNamespace(id="src_wikidata"),
                SimpleNamespace(
                    source_type="discovery_bundle",
                    rows=[
                        SimpleNamespace(
                            normalized={
                                "name": "Vietnam National University, Hanoi",
                                "country": "Vietnam",
                                "website": "https://www.vnu.edu.vn",
                                "description": "public university system in Vietnam",
                                "source_url": "https://www.wikidata.org/wiki/Q3918",
                            },
                            raw_payload={
                                "name": "Vietnam National University, Hanoi",
                                "country": "Vietnam",
                                "website": "https://www.vnu.edu.vn",
                                "description": "public university system in Vietnam",
                                "source_url": "https://www.wikidata.org/wiki/Q3918",
                            },
                            raw_text="Wikidata row",
                            unique_key="Q3918",
                        )
                    ],
                ),
            ),
        ]
    )

    assert len(merged) == 1
    assert merged[0].unique_key == "https://en.wikipedia.org/wiki/Vietnam_National_University,_Hanoi"
    assert merged[0].normalized["website"] == "https://www.vnu.edu.vn"
    assert merged[0].normalized["description"] == "public university system in Vietnam"
    assert merged[0].raw_payload["_merge"]["field_sources"]["website"] == "src_wikidata"


def test_merge_prepared_sources_matches_diacritic_name_variants() -> None:
    merged = _merge_prepared_sources(
        [
            (
                SimpleNamespace(id="src_unirank"),
                SimpleNamespace(
                    source_type="discovery_bundle",
                    rows=[
                        SimpleNamespace(
                            normalized={"name": "Ton Duc Thang University", "country": "Vietnam"},
                            raw_payload={"name": "Ton Duc Thang University", "country": "Vietnam"},
                            raw_text="uniRank row",
                            unique_key="https://www.unirank.org/vn/uni/ton-duc-thang-university/",
                        )
                    ],
                ),
            ),
            (
                SimpleNamespace(id="src_wikipedia"),
                SimpleNamespace(
                    source_type="discovery_bundle",
                    rows=[
                        SimpleNamespace(
                            normalized={
                                "name": "Tôn Đức Thắng University",
                                "country": "Viet Nam",
                                "description": "public university in Ho Chi Minh City, Vietnam",
                                "website": "https://tdtu.edu.vn/",
                            },
                            raw_payload={
                                "name": "Tôn Đức Thắng University",
                                "country": "Viet Nam",
                                "description": "public university in Ho Chi Minh City, Vietnam",
                                "website": "https://tdtu.edu.vn/",
                            },
                            raw_text="Wikipedia row",
                            unique_key="https://en.wikipedia.org/wiki/Tôn_Đức_Thắng_University",
                        )
                    ],
                ),
            ),
        ]
    )

    assert len(merged) == 1
    assert merged[0].normalized["website"] == "https://tdtu.edu.vn/"
    assert merged[0].raw_payload["_merge"]["field_sources"]["website"] == "src_wikipedia"


def test_prompt_discovery_rate_limit_falls_back_to_trusted_sources(monkeypatch, job) -> None:
    session = FakeSession()
    job.source_ids = []
    job.crawl_mode = "prompt_discovery"
    job.discovery_input = {"prompt_text": "Find universities in Vietnam"}
    monkeypatch.setattr("app.services.direct_run.RawRecord", FakeRawRecordModel)
    monkeypatch.setattr("app.services.direct_run.get_settings", lambda: SimpleNamespace(has_gemini_api_key=lambda: True), raising=False)
    monkeypatch.setattr("app.services.direct_run.build_gemini_client", lambda: (_ for _ in ()).throw(GeminiRateLimitError("All configured Gemini API keys are rate-limited")))
    monkeypatch.setattr(
        "app.services.direct_run._resolved_catalog_sources",
        lambda db, current_job: [
            (
                SimpleNamespace(id="catalog_src_1"),
                SimpleNamespace(
                    source_type="discovery_bundle",
                    rows=[
                        SimpleNamespace(
                            normalized={
                                "name": "Fallback University",
                                "website": "https://fallback.example.edu",
                                "email": "info@fallback.example.edu",
                            },
                            raw_payload={
                                "name": "Fallback University",
                                "website": "https://fallback.example.edu",
                                "email": "info@fallback.example.edu",
                            },
                            raw_text="Fallback University https://fallback.example.edu info@fallback.example.edu",
                            unique_key="fallback_1",
                        )
                    ],
                ),
            )
        ],
    )
    monkeypatch.setattr(
        "app.services.direct_run.upsert_raw_record",
        lambda db, **kwargs: (
            db.raw_records.append(SimpleNamespace(id="raw_1", job_id=kwargs["job_id"], unique_key=kwargs["unique_key"], raw_payload=kwargs["raw_payload"])),
            SimpleNamespace(raw_record_id="raw_1", action="INSERTED", changed=True)
        )[1],
    )
    monkeypatch.setattr(
        "app.services.direct_run.extract_critical_fields",
        lambda request, client: AIExtractorOutput.model_validate(
            {
                "critical_fields": {
                    "name": {"value": "Fallback University", "confidence": 0.98, "source_excerpt": "Fallback University"},
                    "website": {"value": "https://fallback.example.edu", "confidence": 0.95, "source_excerpt": "https://fallback.example.edu"},
                    "email": {"value": "info@fallback.example.edu", "confidence": 0.94, "source_excerpt": "info@fallback.example.edu"},
                },
                "extraction_notes": [],
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.judge_extraction",
        lambda request, client: AIJudgeOutput.model_validate(
            {
                "fields_validation": {
                    "name": {"is_correct": True, "corrected_value": None, "confidence": 98, "reason": "Matches source"},
                    "website": {"is_correct": True, "corrected_value": None, "confidence": 96, "reason": "Matches source"},
                    "email": {"is_correct": True, "corrected_value": None, "confidence": 95, "reason": "Matches source"},
                },
                "overall_confidence": 96,
                "status": "APPROVED",
                "summary": "Valid",
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.log_ai_extraction",
        lambda db, **kwargs: SimpleNamespace(
            overall_confidence=96,
            ai_1_payload=kwargs["extractor_output"].model_dump(mode="json"),
            ai_2_validation={
                "judge_output": kwargs["judge_output"].model_dump(mode="json"),
                "scoring": {"decision": kwargs["scoring"].decision},
            },
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.generate_clean_record",
        lambda db, *, raw_record, ai_log: SimpleNamespace(
            clean_record=SimpleNamespace(status="APPROVED"),
            created=True,
        ),
    )

    result = run_crawl_job_direct(session, job=job)

    assert result.total_records == 1
    assert result.crawled == 1
    assert result.extracted == 1
    assert result.needs_review == 0
    assert result.cleaned == 1
    assert result.status == "READY_TO_EXPORT"


def test_prompt_discovery_rate_limit_surfaces_clear_error_without_fallback(monkeypatch, job) -> None:
    session = FakeSession()
    job.source_ids = []
    job.crawl_mode = "prompt_discovery"
    job.discovery_input = {"prompt_text": "Find universities in Vietnam"}
    monkeypatch.setattr("app.services.direct_run.get_settings", lambda: SimpleNamespace(has_gemini_api_key=lambda: True), raising=False)
    monkeypatch.setattr("app.services.direct_run.build_gemini_client", lambda: (_ for _ in ()).throw(GeminiRateLimitError("All configured Gemini API keys are rate-limited")))
    monkeypatch.setattr("app.services.direct_run._resolved_catalog_sources", lambda db, current_job: [])

    with pytest.raises(DirectRunError) as exc_info:
        run_crawl_job_direct(session, job=job)

    assert "rate-limited" in str(exc_info.value)


def test_resolved_plan_sources_skips_failed_source(monkeypatch) -> None:
    session = FakeSession()
    entries = [{"name": "Good source"}, {"name": "Blocked source"}]

    monkeypatch.setattr(
        "app.services.direct_run._persisted_source_for_plan_entry",
        lambda db, entry, *, country: SimpleNamespace(id=entry["name"], source_name=entry["name"], config={}),
    )

    def fake_fetch_bundle(source, *, country, focus_fields=None):
        if source.source_name == "Blocked source":
            raise httpx.HTTPStatusError(
                "403 Forbidden",
                request=httpx.Request("GET", "https://example.edu/blocked"),
                response=httpx.Response(403),
            )
        return SimpleNamespace(
            source_id="good_source",
            source_name="Good source",
            rows=[
                SimpleNamespace(
                    normalized={"name": "Good University"},
                    raw_payload={"name": "Good University"},
                    raw_text="Good University",
                    unique_key="good_1",
                )
            ],
        )

    monkeypatch.setattr("app.services.direct_run.fetch_discovery_bundle_from_source", fake_fetch_bundle)

    resolved = _resolved_plan_sources(session, entries, country="Vietnam")

    assert len(resolved) == 1
    assert resolved[0][0].source_name == "Good source"
    assert len(resolved[0][1].rows) == 1


def test_resolved_plan_sources_fails_when_all_sources_fail(monkeypatch) -> None:
    session = FakeSession()
    entries = [{"name": "Blocked source"}]

    monkeypatch.setattr(
        "app.services.direct_run._persisted_source_for_plan_entry",
        lambda db, entry, *, country: SimpleNamespace(id=entry["name"], source_name=entry["name"], config={}),
    )
    monkeypatch.setattr(
        "app.services.direct_run.fetch_discovery_bundle_from_source",
        lambda source, *, country, focus_fields=None: (_ for _ in ()).throw(RuntimeError("403 Forbidden")),
    )

    with pytest.raises(DirectRunError) as exc_info:
        _resolved_plan_sources(session, entries, country="Vietnam")

    assert "All configured sources failed" in str(exc_info.value)
    assert "Blocked source" in str(exc_info.value)


def test_supplemental_discovery_resolves_supplemental_plan(monkeypatch, job) -> None:
    session = FakeSession()
    monkeypatch.setattr("app.services.direct_run.RawRecord", FakeRawRecordModel)
    job.source_ids = []
    job.crawl_mode = "supplemental_discovery"
    job.discovery_input = {
        "supplemental_plan": {
            "country": "Vietnam",
            "sources": [
                {
                    "name": "Supplemental Vietnam Coverage",
                    "config": {"source_type": "official_catalog_html"},
                }
            ],
        }
    }
    monkeypatch.setattr(
        "app.services.direct_run._resolved_supplemental_sources",
        lambda db, current_job: [
            (
                SimpleNamespace(id="supplemental_src_1"),
                SimpleNamespace(
                    source_type="discovery_bundle",
                    rows=[
                        SimpleNamespace(
                            normalized={"name": "Supplemental University"},
                            raw_payload={"name": "Supplemental University"},
                            raw_text="Supplemental University",
                            unique_key="supp_1",
                        )
                    ],
                ),
            )
        ],
    )
    monkeypatch.setattr(
        "app.services.direct_run.upsert_raw_record",
        lambda db, **kwargs: (
            db.raw_records.append(SimpleNamespace(id="raw_1", job_id=kwargs["job_id"], unique_key=kwargs["unique_key"], raw_payload=kwargs["raw_payload"])),
            SimpleNamespace(raw_record_id="raw_1", action="INSERTED", changed=True)
        )[1],
    )
    monkeypatch.setattr(
        "app.services.direct_run.extract_critical_fields",
        lambda request, client: AIExtractorOutput.model_validate(
            {
                "critical_fields": {
                    "name": {"value": "Supplemental University", "confidence": 0.98, "source_excerpt": "Supplemental University"},
                    "website": {"value": None, "confidence": 0.0, "source_excerpt": None},
                    "email": {"value": None, "confidence": 0.0, "source_excerpt": None},
                },
                "extraction_notes": [],
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.judge_extraction",
        lambda request, client: AIJudgeOutput.model_validate(
            {
                "fields_validation": {
                    "name": {"is_correct": True, "corrected_value": None, "confidence": 95, "reason": "Matches source"},
                    "website": {"is_correct": False, "corrected_value": None, "confidence": 40, "reason": "Missing"},
                    "email": {"is_correct": False, "corrected_value": None, "confidence": 40, "reason": "Missing"},
                },
                "overall_confidence": 55,
                "status": "NEEDS_REVIEW",
                "summary": "Supplemental coverage needs review",
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.log_ai_extraction",
        lambda db, **kwargs: SimpleNamespace(
            overall_confidence=55,
            ai_1_payload=kwargs["extractor_output"].model_dump(mode="json"),
            ai_2_validation={
                "judge_output": kwargs["judge_output"].model_dump(mode="json"),
                "scoring": {"decision": kwargs["scoring"].decision},
            },
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.generate_clean_record",
        lambda db, *, raw_record, ai_log: SimpleNamespace(
            clean_record=SimpleNamespace(status="NEEDS_REVIEW"),
            created=True,
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.get_settings",
        lambda: SimpleNamespace(has_gemini_api_key=lambda: True),
        raising=False,
    )

    result = run_crawl_job_direct(session, job=job)

    assert result.total_records == 1
    assert result.needs_review == 1
    assert result.status == "NEEDS_REVIEW"


def test_run_crawl_job_direct_processes_rows(monkeypatch, job) -> None:
    session = FakeSession(
        sources=[
            SimpleNamespace(
                id="src_1",
                config={"source_type": "json_api", "url": "https://example.edu/api", "items_path": "data", "unique_key_field": "id", "text_field": "content"},
            )
        ]
    )
    monkeypatch.setattr("app.services.direct_run.DataSource", FakeDataSourceModel)
    monkeypatch.setattr("app.services.direct_run.RawRecord", FakeRawRecordModel)
    monkeypatch.setattr(
        "app.services.direct_run.prepare_source_rows",
        lambda source, **kwargs: SimpleNamespace(
            source_type="json_api",
            rows=[
                SimpleNamespace(
                    normalized={
                        "id": "uni_1",
                        "name": "Example University",
                        "website": "https://example.edu",
                        "email": "info@example.edu",
                        "content": "Example University https://example.edu info@example.edu",
                    },
                    raw_payload={
                        "id": "uni_1",
                        "name": "Example University",
                        "website": "https://example.edu",
                        "email": "info@example.edu",
                        "content": "Example University https://example.edu info@example.edu",
                    },
                    raw_text="Example University https://example.edu info@example.edu",
                    unique_key="uni_1",
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.upsert_raw_record",
        lambda db, **kwargs: (
            db.raw_records.append(SimpleNamespace(id="raw_1", job_id=kwargs["job_id"], unique_key=kwargs["unique_key"], raw_payload=kwargs["raw_payload"])),
            SimpleNamespace(raw_record_id="raw_1", action="INSERTED", changed=True)
        )[1],
    )
    monkeypatch.setattr(
        "app.services.direct_run.extract_critical_fields",
        lambda request, client: AIExtractorOutput.model_validate(
            {
                "critical_fields": {
                    "name": {"value": "Example University", "confidence": 0.98, "source_excerpt": "Example University"},
                    "website": {"value": "https://example.edu", "confidence": 0.95, "source_excerpt": "https://example.edu"},
                    "email": {"value": "info@example.edu", "confidence": 0.94, "source_excerpt": "info@example.edu"},
                },
                "extraction_notes": [],
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.judge_extraction",
        lambda request, client: AIJudgeOutput.model_validate(
            {
                "fields_validation": {
                    "name": {"is_correct": True, "corrected_value": None, "confidence": 98, "reason": "Matches source"},
                    "website": {"is_correct": True, "corrected_value": None, "confidence": 96, "reason": "Matches source"},
                    "email": {"is_correct": True, "corrected_value": None, "confidence": 95, "reason": "Matches source"},
                },
                "overall_confidence": 96,
                "status": "APPROVED",
                "summary": "Valid",
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.log_ai_extraction",
        lambda db, **kwargs: SimpleNamespace(
            overall_confidence=96,
            ai_1_payload=kwargs["extractor_output"].model_dump(mode="json"),
            ai_2_validation={
                "judge_output": kwargs["judge_output"].model_dump(mode="json"),
                "scoring": {"decision": kwargs["scoring"].decision},
            },
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.generate_clean_record",
        lambda db, *, raw_record, ai_log: SimpleNamespace(
            clean_record=SimpleNamespace(status="APPROVED"),
            created=True,
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.get_settings",
        lambda: SimpleNamespace(has_gemini_api_key=lambda: True),
        raising=False,
    )

    result = run_crawl_job_direct(session, job=job)

    assert result.total_records == 1
    assert result.crawled == 1
    assert result.extracted == 1
    assert result.needs_review == 0
    assert result.cleaned == 1
    assert result.status == "READY_TO_EXPORT"
    assert job.status == "READY_TO_EXPORT"
    assert job.progress["total_records"] == 1


def test_run_crawl_job_direct_skips_failed_row_and_continues(monkeypatch, job) -> None:
    session = FakeSession(
        sources=[
            SimpleNamespace(
                id="src_1",
                config={"source_type": "json_api", "url": "https://example.edu/api", "items_path": "data", "unique_key_field": "id"},
            )
        ]
    )
    job.ai_assist = False
    monkeypatch.setattr("app.services.direct_run.DataSource", FakeDataSourceModel)
    monkeypatch.setattr("app.services.direct_run.RawRecord", FakeRawRecordModel)
    monkeypatch.setattr(
        "app.services.direct_run.prepare_source_rows",
        lambda source, **kwargs: SimpleNamespace(
            source_type="json_api",
            rows=[
                SimpleNamespace(
                    normalized={"id": "bad", "name": "Bad University", "website": "https://bad.example.edu", "email": "bad@example.edu"},
                    raw_payload={"id": "bad", "name": "Bad University", "website": "https://bad.example.edu", "email": "bad@example.edu"},
                    raw_text="Bad University https://bad.example.edu bad@example.edu",
                    unique_key="bad",
                ),
                SimpleNamespace(
                    normalized={"id": "good", "name": "Good University", "website": "https://good.example.edu", "email": "good@example.edu"},
                    raw_payload={"id": "good", "name": "Good University", "website": "https://good.example.edu", "email": "good@example.edu"},
                    raw_text="Good University https://good.example.edu good@example.edu",
                    unique_key="good",
                ),
            ],
        ),
    )

    def fake_upsert(db, **kwargs):
        if kwargs["unique_key"] == "bad":
            raise RuntimeError("row-level ingest failure")
        raw_id = f"raw_{len(db.raw_records) + 1}"
        db.raw_records.append(
            SimpleNamespace(
                id=raw_id,
                job_id=kwargs["job_id"],
                unique_key=kwargs["unique_key"],
                raw_payload=kwargs["raw_payload"],
            )
        )
        return SimpleNamespace(raw_record_id=raw_id, action="INSERTED", changed=True)

    monkeypatch.setattr("app.services.direct_run.upsert_raw_record", fake_upsert)
    monkeypatch.setattr(
        "app.services.direct_run.log_ai_extraction",
        lambda db, **kwargs: SimpleNamespace(
            overall_confidence=96,
            ai_1_payload=kwargs["extractor_output"].model_dump(mode="json"),
            ai_2_validation={
                "judge_output": kwargs["judge_output"].model_dump(mode="json"),
                "scoring": {"decision": kwargs["scoring"].decision},
            },
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.generate_clean_record",
        lambda db, *, raw_record, ai_log: SimpleNamespace(
            clean_record=SimpleNamespace(status="APPROVED"),
            created=True,
        ),
    )

    result = run_crawl_job_direct(session, job=job)

    assert result.total_records == 2
    assert result.processed == 2
    assert result.extracted == 1
    assert result.skipped == 1
    assert result.rejected == 1
    assert result.cleaned == 1
    assert result.status == "NEEDS_REVIEW"


def test_run_crawl_job_direct_reprocesses_unchanged_raw_without_clean_record(monkeypatch, job) -> None:
    session = FakeSession(
        sources=[
            SimpleNamespace(
                id="src_1",
                config={"source_type": "json_api", "url": "https://example.edu/api", "items_path": "data", "unique_key_field": "id"},
            )
        ]
    )
    existing_raw = SimpleNamespace(
        id="raw_1",
        job_id=job.id,
        unique_key="uni_1",
        raw_payload={
            "id": "uni_1",
            "name": "Example University",
            "website": "https://example.edu",
        },
    )
    session.raw_records.append(existing_raw)
    monkeypatch.setattr("app.services.direct_run.DataSource", FakeDataSourceModel)
    monkeypatch.setattr("app.services.direct_run.RawRecord", FakeRawRecordModel)
    monkeypatch.setattr(
        "app.services.direct_run.prepare_source_rows",
        lambda source, **kwargs: SimpleNamespace(
            source_type="json_api",
            rows=[
                SimpleNamespace(
                    normalized={"id": "uni_1", "name": "Example University", "website": "https://example.edu"},
                    raw_payload={"id": "uni_1", "name": "Example University", "website": "https://example.edu"},
                    raw_text="Example University https://example.edu",
                    unique_key="uni_1",
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.upsert_raw_record",
        lambda db, **kwargs: SimpleNamespace(raw_record_id="raw_1", action="NO_CHANGE", changed=False),
    )
    monkeypatch.setattr(
        "app.services.direct_run.generate_clean_record",
        lambda db, *, raw_record, ai_log: SimpleNamespace(
            clean_record=SimpleNamespace(status="APPROVED"),
            created=True,
        ),
    )

    result = run_crawl_job_direct(session, job=job)

    assert result.processed == 1
    assert result.clean_candidates == 1
    assert result.skipped == 0
    assert result.status == "READY_TO_EXPORT"


def test_run_crawl_job_direct_reprocesses_unchanged_raw_when_clean_payload_is_blank(monkeypatch, job) -> None:
    session = FakeSession(
        sources=[
            SimpleNamespace(
                id="src_1",
                config={"source_type": "json_api", "url": "https://example.edu/api", "items_path": "data", "unique_key_field": "id"},
            )
        ]
    )
    session.raw_records.append(
        SimpleNamespace(
            id="raw_1",
            job_id=job.id,
            unique_key="uni_1",
            raw_payload={
                "id": "uni_1",
                "name": "Example University",
                "source_url": "https://en.wikipedia.org/wiki/Example_University",
                "website": "https://example.edu",
            },
        )
    )
    session.clean_records.append(
        SimpleNamespace(
            job_id=job.id,
            unique_key="uni_1",
            clean_payload={"name": "Example University", "source_url": None, "website": None},
            status="NEEDS_REVIEW",
        )
    )
    monkeypatch.setattr("app.services.direct_run.DataSource", FakeDataSourceModel)
    monkeypatch.setattr("app.services.direct_run.RawRecord", FakeRawRecordModel)
    monkeypatch.setattr(
        "app.services.direct_run.prepare_source_rows",
        lambda source, **kwargs: SimpleNamespace(
            source_type="json_api",
            rows=[
                SimpleNamespace(
                    normalized={
                        "id": "uni_1",
                        "name": "Example University",
                        "source_url": "https://en.wikipedia.org/wiki/Example_University",
                        "website": "https://example.edu",
                    },
                    raw_payload={
                        "id": "uni_1",
                        "name": "Example University",
                        "source_url": "https://en.wikipedia.org/wiki/Example_University",
                        "website": "https://example.edu",
                    },
                    raw_text="Example University https://example.edu",
                    unique_key="uni_1",
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.upsert_raw_record",
        lambda db, **kwargs: SimpleNamespace(raw_record_id="raw_1", action="NO_CHANGE", changed=False),
    )
    monkeypatch.setattr(
        "app.services.direct_run.generate_clean_record",
        lambda db, *, raw_record, ai_log: SimpleNamespace(
            clean_record=SimpleNamespace(status="APPROVED"),
            created=False,
        ),
    )

    result = run_crawl_job_direct(session, job=job)

    assert result.processed == 1
    assert result.skipped == 0


def test_run_crawl_job_direct_marks_review_needed(monkeypatch, job) -> None:
    session = FakeSession(
        sources=[SimpleNamespace(id="src_1", config={"source_type": "json_api", "url": "https://example.edu/api"})]
    )
    monkeypatch.setattr("app.services.direct_run.DataSource", FakeDataSourceModel)
    monkeypatch.setattr("app.services.direct_run.RawRecord", FakeRawRecordModel)
    monkeypatch.setattr(
        "app.services.direct_run.prepare_source_rows",
        lambda source, **kwargs: SimpleNamespace(
            source_type="json_api",
            rows=[
                SimpleNamespace(
                    normalized={"id": "uni_1", "name": "Example"},
                    raw_payload={"id": "uni_1", "name": "Example"},
                    raw_text='{"id": "uni_1", "name": "Example"}',
                    unique_key="uni_1",
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.upsert_raw_record",
        lambda db, **kwargs: (
            db.raw_records.append(SimpleNamespace(id="raw_1", job_id=kwargs["job_id"], unique_key=kwargs["unique_key"], raw_payload=kwargs["raw_payload"])),
            SimpleNamespace(raw_record_id="raw_1", action="INSERTED", changed=True)
        )[1],
    )
    monkeypatch.setattr(
        "app.services.direct_run.extract_critical_fields",
        lambda request, client: AIExtractorOutput.model_validate(
            {
                "critical_fields": {
                    "name": {"value": "Example", "confidence": 0.9, "source_excerpt": "Example"},
                    "website": {"value": None, "confidence": 0.0, "source_excerpt": None},
                    "email": {"value": None, "confidence": 0.0, "source_excerpt": None},
                },
                "extraction_notes": [],
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.judge_extraction",
        lambda request, client: AIJudgeOutput.model_validate(
            {
                "fields_validation": {
                    "name": {"is_correct": True, "corrected_value": None, "confidence": 90, "reason": "Matches source"},
                    "website": {"is_correct": False, "corrected_value": None, "confidence": 40, "reason": "Required field is missing"},
                    "email": {"is_correct": False, "corrected_value": None, "confidence": 40, "reason": "Required field is missing"},
                },
                "overall_confidence": 55,
                "status": "NEEDS_REVIEW",
                "summary": "Missing fields",
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.log_ai_extraction",
        lambda db, **kwargs: SimpleNamespace(
            overall_confidence=55,
            ai_1_payload=kwargs["extractor_output"].model_dump(mode="json"),
            ai_2_validation={
                "judge_output": kwargs["judge_output"].model_dump(mode="json"),
                "scoring": {"decision": kwargs["scoring"].decision},
            },
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.generate_clean_record",
        lambda db, *, raw_record, ai_log: SimpleNamespace(
            clean_record=SimpleNamespace(status="NEEDS_REVIEW"),
            created=True,
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.get_settings",
        lambda: SimpleNamespace(has_gemini_api_key=lambda: True),
        raising=False,
    )

    result = run_crawl_job_direct(session, job=job)

    assert result.needs_review == 1
    assert result.status == "NEEDS_REVIEW"
    assert job.progress["needs_review"] == 1


def test_source_based_run_does_not_call_ai_judge_when_focus_fields_are_missing(monkeypatch, job) -> None:
    session = FakeSession(
        sources=[SimpleNamespace(id="src_1", config={"source_type": "json_api", "url": "https://example.edu/api"})]
    )
    job.ai_assist = True
    job.critical_fields = ["name", "website", "email"]
    monkeypatch.setattr("app.services.direct_run.DataSource", FakeDataSourceModel)
    monkeypatch.setattr("app.services.direct_run.RawRecord", FakeRawRecordModel)
    monkeypatch.setattr(
        "app.services.direct_run.prepare_source_rows",
        lambda source, **kwargs: SimpleNamespace(
            source_type="json_api",
            rows=[
                SimpleNamespace(
                    normalized={"id": "uni_1", "name": "Example University", "source_url": "https://example.edu/profile"},
                    raw_payload={"id": "uni_1", "name": "Example University", "source_url": "https://example.edu/profile"},
                    raw_text="Example University",
                    unique_key="uni_1",
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.upsert_raw_record",
        lambda db, **kwargs: (
            db.raw_records.append(SimpleNamespace(id="raw_1", job_id=kwargs["job_id"], unique_key=kwargs["unique_key"], raw_payload=kwargs["raw_payload"])),
            SimpleNamespace(raw_record_id="raw_1", action="INSERTED", changed=True)
        )[1],
    )
    monkeypatch.setattr(
        "app.services.direct_run.build_gemini_client",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AI judge should not be called for rows missing required focus fields")),
    )
    monkeypatch.setattr(
        "app.services.direct_run.log_ai_extraction",
        lambda db, **kwargs: SimpleNamespace(
            overall_confidence=60,
            ai_1_payload=kwargs["extractor_output"].model_dump(mode="json"),
            ai_2_validation={
                "judge_output": kwargs["judge_output"].model_dump(mode="json"),
                "scoring": {"decision": kwargs["scoring"].decision},
            },
        ),
    )
    monkeypatch.setattr(
        "app.services.direct_run.generate_clean_record",
        lambda db, *, raw_record, ai_log: SimpleNamespace(
            clean_record=SimpleNamespace(status="NEEDS_REVIEW"),
            created=True,
        ),
    )

    result = run_crawl_job_direct(session, job=job)

    assert result.total_records == 1
    assert result.processed == 1
    assert result.needs_review == 1
