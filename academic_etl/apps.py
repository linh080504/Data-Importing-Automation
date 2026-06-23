from django.apps import AppConfig


class AcademicEtlConfig(AppConfig):
    name = "academic_etl"

    def ready(self):
        from . import signals  # noqa: F401
