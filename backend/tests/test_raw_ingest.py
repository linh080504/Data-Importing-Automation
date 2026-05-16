from types import SimpleNamespace
from uuid import uuid4

from app.services.raw_ingest import compute_record_hash, upsert_raw_record


class FilterField:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)


class FakeRawRecordModel:
    job_id = FilterField("job_id")
    source_id = FilterField("source_id")
    unique_key = FilterField("unique_key")

    def __init__(self, *, job_id: str, source_id: str, unique_key: str, record_hash: str, raw_payload: dict):
        self.id = str(uuid4())
        self.job_id = job_id
        self.source_id = source_id
        self.unique_key = unique_key
        self.record_hash = record_hash
        self.raw_payload = raw_payload


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
    def __init__(self, records=None):
        self.records = list(records or [])
        self.added = []

    def query(self, model):
        if model is FakeRawRecordModel:
            return FakeQuery(list(self.records))
        return FakeQuery([])

    def add(self, obj):
        if not getattr(obj, "id", None):
            obj.id = str(uuid4())
        if obj not in self.records:
            self.records.append(obj)
        self.added.append(obj)

    def commit(self):
        return None

    def refresh(self, _obj):
        return None



def test_compute_record_hash_is_stable_for_key_order() -> None:
    payload_a = {"name": "Uni", "location": "VN", "meta": {"x": 1, "y": 2}}
    payload_b = {"location": "VN", "meta": {"y": 2, "x": 1}, "name": "Uni"}

    assert compute_record_hash(payload_a) == compute_record_hash(payload_b)



def test_upsert_raw_record_creates_new_record_with_job_scope(monkeypatch) -> None:
    session = FakeSession()
    monkeypatch.setattr("app.services.raw_ingest.RawRecord", FakeRawRecordModel)

    result = upsert_raw_record(
        session,
        job_id="job_1",
        source_id="src_1",
        unique_key="uni_1",
        raw_payload={"name": "Example University"},
        record_hash="hash_1",
    )

    assert result.action == "INSERTED"
    assert result.changed is True
    assert len(session.records) == 1
    assert session.records[0].job_id == "job_1"


def test_upsert_raw_record_preserves_long_source_url_key(monkeypatch) -> None:
    session = FakeSession()
    monkeypatch.setattr("app.services.raw_ingest.RawRecord", FakeRawRecordModel)
    unique_key = "https://www.unirank.org/vn/uni/ho-chi-minh-city-university-of-foreign-languages-and-information-technology/"

    result = upsert_raw_record(
        session,
        job_id="job_1",
        source_id="src_1",
        unique_key=unique_key,
        raw_payload={"name": "Ho Chi Minh City University of Foreign Languages and Information Technology"},
    )

    assert result.action == "INSERTED"
    assert session.records[0].unique_key == unique_key



def test_upsert_raw_record_updates_existing_record_within_same_job(monkeypatch) -> None:
    existing = SimpleNamespace(
        id=str(uuid4()),
        job_id="job_1",
        source_id="src_1",
        unique_key="uni_1",
        record_hash="old_hash",
        raw_payload={"name": "Old"},
    )
    session = FakeSession(records=[existing])
    monkeypatch.setattr("app.services.raw_ingest.RawRecord", FakeRawRecordModel)

    result = upsert_raw_record(
        session,
        job_id="job_1",
        source_id="src_1",
        unique_key="uni_1",
        raw_payload={"name": "New"},
        record_hash="new_hash",
    )

    assert result.action == "UPDATED"
    assert result.changed is True
    assert existing.record_hash == "new_hash"
    assert existing.raw_payload == {"name": "New"}



def test_upsert_raw_record_allows_same_unique_key_in_different_jobs(monkeypatch) -> None:
    existing = SimpleNamespace(
        id=str(uuid4()),
        job_id="job_1",
        source_id="src_1",
        unique_key="uni_1",
        record_hash="hash_1",
        raw_payload={"name": "First Job"},
    )
    session = FakeSession(records=[existing])
    monkeypatch.setattr("app.services.raw_ingest.RawRecord", FakeRawRecordModel)

    result = upsert_raw_record(
        session,
        job_id="job_2",
        source_id="src_1",
        unique_key="uni_1",
        raw_payload={"name": "Second Job"},
        record_hash="hash_2",
    )

    assert result.action == "INSERTED"
    assert result.changed is True
    assert len(session.records) == 2
    assert {record.job_id for record in session.records} == {"job_1", "job_2"}
