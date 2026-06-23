"""Seed a pipeline run straight from a University_Import_Clean-style CSV
(handles the misaligned headers; full fields are staged with evidence).

Example:
    python manage.py seed_from_csv --csv "sample_data/University_Import_Clean-7.csv" --country "India"
    python manage.py seed_from_csv --csv "global_universities.csv"
"""

from django.core.management.base import BaseCommand, CommandError

from academic_etl.models import PipelineRun
from academic_etl.services.discovery import resolve_country, run_discovery


class Command(BaseCommand):
    help = "Create a run and stage universities from a CSV seed file."

    def add_arguments(self, parser):
        parser.add_argument("--csv", required=True)
        parser.add_argument("--country", default="", help="Optional country filter")
        parser.add_argument("--country-code", default="")
        parser.add_argument("--limit", type=int, default=0, help="0 = all rows")

    def handle(self, *args, **options):
        name, code = resolve_country(options["country"], options["country_code"])
        run = PipelineRun.objects.create(
            country_name=name, country_code=code,
            crawl_mode="csv_seed", seed_provider="csv",
        )
        try:
            run_discovery(run, limit=options["limit"], csv_path=options["csv"])
        except FileNotFoundError as exc:
            run.status = PipelineRun.Status.FAILED
            run.error_message = str(exc)
            run.save()
            raise CommandError(str(exc)) from exc

        run.status = PipelineRun.Status.REVIEW
        run.save(update_fields=["status", "updated_at"])
        self.stdout.write(self.style.SUCCESS(
            f"Run #{run.pk}: {run.seeds.count()} seeds, "
            f"{run.universities.count()} universities staged from CSV. "
            f"Next: python manage.py validate_country_run --run-id {run.pk}"
        ))
