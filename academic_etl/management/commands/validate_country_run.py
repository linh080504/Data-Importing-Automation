"""Validate + score all staged records of a pipeline run.

Example:
    python manage.py validate_country_run --run-id 1
"""

from django.core.management.base import BaseCommand, CommandError

from academic_etl.models import PipelineRun
from academic_etl.services.validation import validate_run


class Command(BaseCommand):
    help = "Run validation rules over staged universities/programs of a run."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, required=True)

    def handle(self, *args, **options):
        try:
            run = PipelineRun.objects.get(pk=options["run_id"])
        except PipelineRun.DoesNotExist:
            raise CommandError(f"PipelineRun #{options['run_id']} not found.")
        stats = validate_run(run)
        self.stdout.write(self.style.SUCCESS(
            f"Run #{run.pk} validated. Universities: {stats['universities']}. "
            f"Programs: {stats['programs']}. Issues: {run.issues.count()}. "
            f"Review UI: http://127.0.0.1:8000/etl/runs/{run.pk}/"
        ))
