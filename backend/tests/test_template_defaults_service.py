from types import SimpleNamespace

from app.services.template_defaults import defaults_for_job


def test_defaults_for_job_uses_iso_numeric_location_code_for_vietnam() -> None:
    defaults = defaults_for_job(SimpleNamespace(country="Vietnam", discovery_input={}))

    assert defaults["country"] == "Vietnam"
    assert defaults["location"] == 704


def test_defaults_for_job_allows_explicit_location_code_override() -> None:
    defaults = defaults_for_job(
        SimpleNamespace(country="Vietnam", discovery_input={"location_code": "999"})
    )

    assert defaults["location"] == 999
