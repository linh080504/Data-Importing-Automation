"""Fetch each staged university's majors via Gemini (Google Search grounding) and
store them as ExtractedProgram rows (1-to-many). Run AFTER the universities of a
run have been staged (e.g. by build_country_gemini).

Majors are grounded in each university's official website, named in English, and
carry a source URL — exported by the "Majors CSV (simple 3-col)" download
(University Name | Major Name | Source URL).

Examples:
    python manage.py enrich_majors_gemini --run-id 17
    python manage.py enrich_majors_gemini --run-id 17 --limit 10 --no-cache
"""

from django.core.management.base import BaseCommand, CommandError

from academic_etl.models import PipelineRun
from academic_etl.services.gemini_enrich import is_configured
from academic_etl.services.pipeline import enrich_run_majors_from_gemini
from academic_etl.services.validation import validate_run


class Command(BaseCommand):
    help = "Stage each university's majors (1-to-many) via Gemini grounded answers."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, required=True)
        parser.add_argument("--limit", type=int, default=0,
                            help="Max universities to process (0 = all)")
        parser.add_argument("--no-cache", action="store_true",
                            help="Ignore cached Gemini answers and re-query")

    def handle(self, *args, **options):
        if not is_configured():
            raise CommandError("No Gemini API key. Add GEMINI_API_KEY / GEMINI_API_KEYS to .env.")
        run = PipelineRun.objects.filter(pk=options["run_id"]).first()
        if not run:
            raise CommandError(f"Run #{options['run_id']} not found.")
        if not run.universities.exists():
            raise CommandError("No staged universities — run university enrichment first.")

        self.stdout.write(f"Run #{run.pk}: fetching majors for {run.universities.count()} universities...")
        stats = enrich_run_majors_from_gemini(
            run, limit=options["limit"], use_cache=not options["no_cache"],
        )
        validate_run(run)
        self.stdout.write(self.style.SUCCESS(
            f"Done. {stats['programs']} majors across {stats['with_majors']} universities "
            f"({stats['errors']} errors). Download 'Majors CSV (simple 3-col)' at "
            f"http://127.0.0.1:8000/etl/runs/{run.pk}/"
        ))
