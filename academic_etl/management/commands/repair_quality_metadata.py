import time

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Repair legacy AI quality metadata after the active pipeline worker releases its lock."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, required=True)

    def handle(self, *args, **options):
        from academic_etl.models import PipelineRun
        from academic_etl.services.pipeline_execution import LOCK_POLL_SECONDS, PipelineHostLock
        from academic_etl.services.quality_enrichment import repair_legacy_quality_metadata

        run_id = options["run_id"]
        if not PipelineRun.objects.filter(pk=run_id).exists():
            raise CommandError(f"Pipeline run #{run_id} does not exist.")

        lock = PipelineHostLock()
        try:
            while not lock.acquire():
                time.sleep(LOCK_POLL_SECONDS)
            run = PipelineRun.objects.get(pk=run_id)
            stats = repair_legacy_quality_metadata(run)
        finally:
            lock.release()

        self.stdout.write(self.style.SUCCESS(
            f"Run #{run_id}: cleared {stats['campuses_cleared']} campus counts, "
            f"relabeled {stats['errors_relabelled']} values, "
            f"removed {stats['evidence_removed']} evidence rows."
        ))
