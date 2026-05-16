from types import SimpleNamespace

from app.services.required_fields import required_fields_for_job


def test_required_fields_default_to_name_when_template_supports_it() -> None:
    job = SimpleNamespace(discovery_input=None)
    columns = [{"name": "id", "order": 1}, {"name": "name", "order": 2}, {"name": "website", "order": 3}]

    assert required_fields_for_job(job, columns) == ["name"]


def test_required_fields_do_not_treat_focus_fields_as_required() -> None:
    job = SimpleNamespace(critical_fields=["name", "website", "financials"], discovery_input=None)
    columns = [{"name": "name", "order": 1}, {"name": "website", "order": 2}, {"name": "financials", "order": 3}]

    assert required_fields_for_job(job, columns) == ["name"]


def test_required_fields_can_be_configured_explicitly() -> None:
    job = SimpleNamespace(discovery_input={"required_fields": ["name", "website", "not_in_template"]})
    columns = [{"name": "name", "order": 1}, {"name": "website", "order": 2}]

    assert required_fields_for_job(job, columns) == ["name", "website"]
