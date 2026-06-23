from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Execute one cooperative ETL data reset job."

    def add_arguments(self, parser):
        parser.add_argument("--job-id", type=int, required=True)

    def handle(self, *args, **options):
        from academic_etl.models import DataResetJob
        from academic_etl.services.data_reset import run_data_reset

        job_id = options["job_id"]
        if not DataResetJob.objects.filter(pk=job_id).exists():
            raise CommandError(f"Data reset job #{job_id} does not exist.")
        run_data_reset(job_id)
