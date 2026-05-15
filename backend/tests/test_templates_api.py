from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.templates import get_db as original_get_db
from app.api.templates import router
from app.services.template_parser import TemplateParseError


class FilterField:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)


class CreatedAtField:
    def desc(self):
        return self


class FakeCrawlJobModel:
    clean_template_id = FilterField("clean_template_id")


class FakeCleanTemplateCreate:
    def __init__(self, *, template_name, file_name, column_count, columns, sample_row):
        self.id = str(uuid4())
        self.template_name = template_name
        self.file_name = file_name
        self.column_count = column_count
        self.columns = columns
        self.sample_row = sample_row


class FakeCleanTemplateModel:
    created_at = CreatedAtField()
    template_name = FilterField("template_name")
    id = FilterField("id")

    def __call__(self, **kwargs):
        return FakeCleanTemplateCreate(**kwargs)


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def order_by(self, *_args, **_kwargs):
        return self

    def filter(self, condition):
        op, field_name, value = condition
        if op == "eq":
            self.items = [item for item in self.items if str(getattr(item, field_name)) == str(value)]
        return self

    def all(self):
        return self.items

    def one_or_none(self):
        return self.items[0] if self.items else None


class FakeSession:
    def __init__(self):
        self.templates = [
            SimpleNamespace(
                id=str(uuid4()),
                template_name="University_Import_Clean-7",
                file_name="University_Import_Clean-7.csv",
                column_count=24,
                columns=[{"name": "name", "order": 1}],
                sample_row={"name": "Example University"},
            ),
            SimpleNamespace(
                id=str(uuid4()),
                template_name="College_Import_Clean-2",
                file_name="College_Import_Clean-2.csv",
                column_count=18,
                columns=[{"name": "name", "order": 1}],
                sample_row={"name": "Example College"},
            ),
        ]
        self.jobs = []
        self.added = []

    def query(self, model):
        model_name = getattr(model, "__name__", None)
        if model_name == "CrawlJob" or model is FakeCrawlJobModel:
            return FakeQuery(list(self.jobs))
        return FakeQuery(list(self.templates))

    def add(self, template):
        self.templates.append(template)
        self.added.append(template)

    def delete(self, template):
        self.templates = [item for item in self.templates if item.id != template.id]

    def commit(self):
        return None

    def refresh(self, _template):
        return None


def build_client(session: FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def override_get_db():
        yield session

    app.dependency_overrides[original_get_db] = override_get_db
    return TestClient(app)


def test_list_templates_returns_template_catalog(monkeypatch) -> None:
    client = build_client(FakeSession())
    monkeypatch.setattr("app.api.templates.CleanTemplate", FakeCleanTemplateModel())

    response = client.get("/api/v1/templates")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["templates"]) == 2
    assert payload["templates"][0]["template_name"] == "University_Import_Clean-7"
    assert payload["templates"][0]["file_name"] == "University_Import_Clean-7.csv"
    assert payload["templates"][0]["column_count"] == 24


def test_upload_template_creates_template_from_csv(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)

    monkeypatch.setattr("app.api.templates.CleanTemplate", FakeCleanTemplateModel())
    monkeypatch.setattr(
        "app.api.templates.parse_template_csv",
        lambda _content: SimpleNamespace(
            columns=[{"name": "name", "order": 1}, {"name": "website", "order": 2}],
            sample_row={"name": "Example University", "website": "https://example.edu"},
        ),
    )

    response = client.post(
        "/api/v1/templates/upload",
        data={"template_name": "University_Import_Clean-8"},
        files={"file": ("template.csv", b"name,website\nExample University,https://example.edu\n", "text/csv")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["template_name"] == "University_Import_Clean-8"
    assert payload["file_name"] == "template.csv"
    assert payload["column_count"] == 2
    assert payload["columns"] == [{"name": "name", "order": 1}, {"name": "website", "order": 2}]
    assert payload["sample_row"] == {"name": "Example University", "website": "https://example.edu"}


def test_upload_template_rejects_non_csv_file(monkeypatch) -> None:
    client = build_client(FakeSession())
    monkeypatch.setattr("app.api.templates.CleanTemplate", FakeCleanTemplateModel())

    response = client.post(
        "/api/v1/templates/upload",
        data={"template_name": "University_Import_Clean-8"},
        files={"file": ("template.xlsx", b"binary", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only CSV template files are supported"


def test_upload_template_rejects_duplicate_name(monkeypatch) -> None:
    client = build_client(FakeSession())
    monkeypatch.setattr("app.api.templates.CleanTemplate", FakeCleanTemplateModel())
    monkeypatch.setattr(
        "app.api.templates.parse_template_csv",
        lambda _content: SimpleNamespace(columns=[{"name": "name", "order": 1}], sample_row={"name": "Example University"}),
    )

    response = client.post(
        "/api/v1/templates/upload",
        data={"template_name": "University_Import_Clean-7"},
        files={"file": ("template.csv", b"name\nExample University\n", "text/csv")},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Template name already exists"


def test_upload_template_returns_parse_error_message(monkeypatch) -> None:
    client = build_client(FakeSession())
    monkeypatch.setattr("app.api.templates.CleanTemplate", FakeCleanTemplateModel())

    def fail_parse(_content: bytes):
        raise TemplateParseError("Template file must include a header row")

    monkeypatch.setattr("app.api.templates.parse_template_csv", fail_parse)

    response = client.post(
        "/api/v1/templates/upload",
        data={"template_name": "University_Import_Clean-8"},
        files={"file": ("template.csv", b"", "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Template file must include a header row"


def test_delete_template_removes_template(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)
    monkeypatch.setattr("app.api.templates.CleanTemplate", FakeCleanTemplateModel())
    monkeypatch.setattr("app.api.templates.CrawlJob", FakeCrawlJobModel)

    template_id = session.templates[0].id
    response = client.delete(f"/api/v1/templates/{template_id}")

    assert response.status_code == 200
    assert response.json() == {"id": template_id, "message": "Template deleted"}
    assert all(template.id != template_id for template in session.templates)


def test_delete_template_rejects_template_in_use(monkeypatch) -> None:
    session = FakeSession()
    client = build_client(session)
    monkeypatch.setattr("app.api.templates.CleanTemplate", FakeCleanTemplateModel())
    monkeypatch.setattr("app.api.templates.CrawlJob", FakeCrawlJobModel)

    template_id = session.templates[0].id
    session.jobs.append(SimpleNamespace(id=str(uuid4()), clean_template_id=template_id))

    response = client.delete(f"/api/v1/templates/{template_id}")

    assert response.status_code == 409
    assert response.json()["detail"] == "Template is currently used by an existing crawl job"
    assert any(template.id == template_id for template in session.templates)



def test_delete_template_returns_not_found(monkeypatch) -> None:
    client = build_client(FakeSession())
    monkeypatch.setattr("app.api.templates.CleanTemplate", FakeCleanTemplateModel())
    monkeypatch.setattr("app.api.templates.CrawlJob", FakeCrawlJobModel)

    response = client.delete(f"/api/v1/templates/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Template not found"
