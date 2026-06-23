"""Run one unified ETL pipeline in a process separate from the web server."""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Execute a unified ETL run by id. Intended for the detached web worker."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, required=True)
        parser.add_argument("--worker-token", default="")

    def handle(self, *args, **options):
        from academic_etl.models import PipelineRun
        from academic_etl.views import run_unified_pipeline

        run_id = options["run_id"]
        if not PipelineRun.objects.filter(pk=run_id).exists():
            raise CommandError(f"Pipeline run #{run_id} does not exist.")
        run_unified_pipeline(run_id, worker_token=options["worker_token"])
