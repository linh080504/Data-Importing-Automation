"""One-shot builder using Gemini grounded enrichment as the primary field source.

Flow: Wikipedia list discovery (broad, real roster) -> Gemini answers grounded in
Google Search fill name/website/description/campus_student_life/number_of_students
with source URLs -> validate. No fragile per-site HTML scraping for these fields.

Requires GEMINI_API_KEY in the environment or a .env file at the project root.

Examples:
    python manage.py build_country_gemini --country "Vietnam"
    python manage.py build_country_gemini --country "Vietnam" --max 50 --concurrency 4
    python manage.py build_country_gemini --country "Vietnam" --no-cache   # ignore cached answers
"""

from django.core.management.base import BaseCommand, CommandError

from academic_etl.models import InstitutionSeed, PipelineRun
from academic_etl.services.discovery import resolve_country, run_discovery
from academic_etl.services.gemini_enrich import is_configured
from academic_etl.services.pipeline import enrich_run_from_gemini
from academic_etl.services.validation import validate_run


class Command(BaseCommand):
    help = "Build a country catalog: Wikipedia roster + Gemini grounded field enrichment."

    def add_arguments(self, parser):
        parser.add_argument("--country", default="")
        parser.add_argument("--country-code", default="")
        parser.add_argument("--max", type=int, default=0,
                            help="Max institutions to discover (0 = all listed)")
        parser.add_argument("--concurrency", type=int, default=0,
                            help="Parallel Gemini API calls (default: settings.GEMINI_CONCURRENCY)")
        parser.add_argument("--no-cache", action="store_true",
                            help="Ignore cached Gemini answers and re-query")
        parser.add_argument("--fill-empty-only", action="store_true",
                            help="Only fill empty fields (don't overwrite existing staged values)")

    def handle(self, *args, **options):
        if not is_configured():
            raise CommandError(
                "GEMINI_API_KEY is not set. Add it to a .env file at the project "
                "root (GEMINI_API_KEY=your_key) or export it in the environment."
            )

        name, code = resolve_country(options["country"], options["country_code"])
        if not name:
            raise CommandError("Provide --country or a known --country-code.")

        run = PipelineRun.objects.create(
            country_name=name, country_code=code,
            crawl_mode="full", seed_provider="wikipedia",
            crawl_scope="gemini_grounding",
        )
        self.stdout.write(f"Run #{run.pk}: discovering {name} institutions from Wikipedia...")
        run_discovery(run, limit=options["max"])
        valid = run.seeds.filter(status=InstitutionSeed.Status.VALID).count()
        self.stdout.write(f"  discovered {run.seeds.count()} seeds ({valid} valid higher-ed).")

        self.stdout.write("Enriching with Gemini (Google Search grounding)...")
        stats = enrich_run_from_gemini(
            run,
            concurrency=options["concurrency"],
            use_cache=not options["no_cache"],
            overwrite=not options["fill_empty_only"],
        )
        self.stdout.write(
            f"  Gemini: staged {stats['staged']}/{stats['attempted']} "
            f"({stats['from_cache']} from cache, {stats['errors']} errors)."
        )

        vstats = validate_run(run)
        self.stdout.write(self.style.SUCCESS(
            f"Run #{run.pk} done. Universities: {run.universities.count()}. "
            f"Validation: {vstats['universities']}. "
            f"Review + export at http://127.0.0.1:8000/etl/runs/{run.pk}/ "
            f"(Approve all valid, then download the Universities CSV)."
        ))
