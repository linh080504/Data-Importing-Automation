"""Import approved staged records into the universities app.

Examples:
    python manage.py import_country_run --run-id 1 --approved-only --dry-run
    python manage.py import_country_run --run-id 1 --approved-only
    python manage.py import_country_run --run-id 1 --confidence-threshold 0.8 --dry-run
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from academic_etl.models import PipelineRun
from academic_etl.services.importer import import_run


class Command(BaseCommand):
    help = "Import approved/high-confidence staged records into the target database."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, required=True)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--approved-only", action="store_true")
        parser.add_argument("--confidence-threshold", type=float,
                            default=settings.ETL_IMPORT_CONFIDENCE_THRESHOLD)

    def handle(self, *args, **options):
        try:
            run = PipelineRun.objects.get(pk=options["run_id"])
        except PipelineRun.DoesNotExist:
            raise CommandError(f"PipelineRun #{options['run_id']} not found.")

        job = import_run(
            run,
            dry_run=options["dry_run"],
            approved_only=options["approved_only"],
            threshold=options["confidence_threshold"],
        )
        mode = "DRY-RUN" if job.dry_run else "LIVE"
        style = self.style.SUCCESS if job.status == "completed" else self.style.ERROR
        self.stdout.write(style(
            f"[{mode}] ImportJob #{job.pk} {job.status}: processed={job.total_processed} "
            f"created={job.total_created} updated={job.total_updated} skipped={job.total_skipped}. "
            f"Logs: http://127.0.0.1:8000/etl/import-jobs/{job.pk}/"
        ))
        if job.error_message:
            self.stdout.write(self.style.ERROR(job.error_message))
