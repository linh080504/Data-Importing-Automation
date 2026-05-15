from types import SimpleNamespace
from uuid import uuid4

from app.services.cleaner import build_clean_payload, derive_clean_record_status, generate_clean_record


class FilterField:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)


class FakeCleanRecordModel:
    job_id = FilterField("job_id")
    unique_key = FilterField("unique_key")

    def __init__(self, *, job_id: str, raw_record_id: str, unique_key: str, clean_payload: dict):
        self.id = str(uuid4())
        self.job_id = job_id
        self.raw_record_id = raw_record_id
        self.unique_key = unique_key
        self.clean_payload = clean_payload
        self.quality_score = None
        self.status = "NEEDS_REVIEW"


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *conditions):
        for condition in conditions:
            op, field_name, value = condition
            if op == "eq":
                self.items = [item for item in self.items if str(getattr(item, field_name)) == str(value)]
        return self

    def one_or_none(self):
        return self.items[0] if self.items else None


class FakeSession:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []

    def query(self, model):
        if model is FakeCleanRecordModel:
            return FakeQuery([self.existing] if self.existing is not None else [])
        return FakeQuery([])

    def add(self, obj):
        if not getattr(obj, "id", None):
            obj.id = str(uuid4())
        self.added.append(obj)

    def commit(self):
        return None

    def refresh(self, _obj):
        return None


def _raw_record() -> SimpleNamespace:
    return SimpleNamespace(id="raw_123", job_id="job_1", unique_key="uni_1")


def _ai_log(decision: str = "AUTO_APPROVE") -> SimpleNamespace:
    return SimpleNamespace(
        overall_confidence=91,
        ai_1_payload={
            "critical_fields": {
                "name": {"value": "Example University", "confidence": 0.95},
                "website": {"value": "https://example.edu", "confidence": 0.88},
                "email": {"value": "bad-email", "confidence": 0.51},
            }
        },
        ai_2_validation={
            "judge_output": {
                "fields_validation": {
                    "name": {"is_correct": True, "corrected_value": None, "confidence": 96},
                    "website": {
                        "is_correct": True,
                        "corrected_value": "https://www.example.edu",
                        "confidence": 92,
                    },
                    "email": {
                        "is_correct": False,
                        "corrected_value": "info@example.edu",
                        "confidence": 82,
                    },
                }
            },
            "scoring": {"decision": decision},
        },
    )


def test_build_clean_payload_prefers_judge_corrections() -> None:
    payload = build_clean_payload(_ai_log())

    assert payload == {
        "name": "Example University",
        "website": "https://www.example.edu",
        "email": "info@example.edu",
    }


def test_derive_clean_record_status_maps_scoring_decision() -> None:
    assert derive_clean_record_status(_ai_log("AUTO_APPROVE")) == "APPROVED"
    assert derive_clean_record_status(_ai_log("NEEDS_REVIEW")) == "NEEDS_REVIEW"
    assert derive_clean_record_status(_ai_log("REJECT")) == "REJECTED"


def test_generate_clean_record_creates_new_record(monkeypatch) -> None:
    session = FakeSession()
    monkeypatch.setattr("app.services.cleaner.CleanRecord", FakeCleanRecordModel)

    result = generate_clean_record(session, raw_record=_raw_record(), ai_log=_ai_log())

    assert result.created is True
    assert result.clean_record.job_id == "job_1"
    assert result.clean_record.raw_record_id == "raw_123"
    assert result.clean_record.unique_key == "uni_1"
    assert result.clean_record.clean_payload["email"] == "info@example.edu"
    assert result.clean_record.quality_score == 91
    assert result.clean_record.status == "APPROVED"
    assert len(session.added) == 1


def test_generate_clean_record_updates_existing_record(monkeypatch) -> None:
    existing = SimpleNamespace(
        id=str(uuid4()),
        job_id="job_1",
        raw_record_id="raw_old",
        unique_key="uni_1",
        clean_payload={"name": "Old Name"},
        quality_score=40,
        status="NEEDS_REVIEW",
    )
    session = FakeSession(existing=existing)
    monkeypatch.setattr("app.services.cleaner.CleanRecord", FakeCleanRecordModel)

    result = generate_clean_record(session, raw_record=_raw_record(), ai_log=_ai_log("NEEDS_REVIEW"))

    assert result.created is False
    assert result.clean_record is existing
    assert existing.raw_record_id == "raw_123"
    assert existing.clean_payload["website"] == "https://www.example.edu"
    assert existing.quality_score == 91
    assert existing.status == "NEEDS_REVIEW"



def test_build_clean_payload_keeps_extracted_value_when_judge_correction_missing() -> None:
    payload = build_clean_payload(
        SimpleNamespace(
            ai_1_payload={
                "critical_fields": {
                    "name": {"value": "Example University"},
                    "website": {"value": "https://example.edu"},
                }
            },
            ai_2_validation={
                "judge_output": {
                    "fields_validation": {
                        "name": {"is_correct": True},
                    }
                }
            },
        )
    )

    assert payload == {
        "name": "Example University",
        "website": "https://example.edu",
    }



def test_build_clean_payload_ignores_non_dict_validation_entries() -> None:
    payload = build_clean_payload(
        SimpleNamespace(
            ai_1_payload={
                "critical_fields": {
                    "name": {"value": "Example University"},
                }
            },
            ai_2_validation={
                "judge_output": {
                    "fields_validation": {
                        "name": "invalid-shape",
                    }
                }
            },
        )
    )

    assert payload == {"name": "Example University"}
