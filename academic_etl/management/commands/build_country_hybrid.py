"""Quota-saving hybrid builder: fill what's FREE first (Wikipedia + official-site
crawl), then call Gemini ONLY for institutions still missing a required field, and
only to fill the empty fields (never overwriting the free data).

Flow:
    Wikipedia list discovery -> Wikipedia article enrich (name/website/description/
    students) -> official-site crawl (footer contacts/campus life) -> Gemini
    grounded gap-fill (skips institutions already complete) -> validate.

The free Gemini quota is counted per request (≈1 request fills all fields for one
institution), so the only real saving is skipping institutions entirely — which
this does via ``skip_complete``.

Requires GEMINI_API_KEY / GEMINI_API_KEYS in the environment or a .env file.

Examples:
    python manage.py build_country_hybrid --country "Vietnam"
    python manage.py build_country_hybrid --country "Vietnam" --no-crawl
    python manage.py build_country_hybrid --country "Vietnam" --crawl-limit 30 --dynamic
"""

from django.core.management.base import BaseCommand, CommandError

from academic_etl.models import InstitutionSeed, PipelineRun
from academic_etl.services.discovery import resolve_country, run_discovery
from academic_etl.services.gemini_enrich import is_configured
from academic_etl.services.pipeline import (
    crawl_run,
    enrich_run_from_gemini,
    enrich_run_from_wikipedia,
)
from academic_etl.services.validation import validate_run


class Command(BaseCommand):
    help = "Hybrid build: Wikipedia + crawl (free) then Gemini only for the gaps."

    def add_arguments(self, parser):
        parser.add_argument("--country", default="")
        parser.add_argument("--country-code", default="")
        parser.add_argument("--max", type=int, default=0,
                            help="Max institutions to discover (0 = all listed)")
        parser.add_argument("--crawl-limit", type=int, default=40,
                            help="Max official sites to crawl")
        parser.add_argument("--max-pages", type=int, default=8, help="Max pages per official site")
        parser.add_argument("--dynamic", action="store_true",
                            help="Enable Scrapling dynamic fallback for JS-rendered sites")
        parser.add_argument("--no-crawl", action="store_true",
                            help="Skip official-site crawling (Wikipedia + Gemini only)")
        parser.add_argument("--no-cache", action="store_true",
                            help="Ignore cached Gemini answers and re-query")

    def handle(self, *args, **options):
        if not is_configured():
            raise CommandError(
                "No Gemini API key. Add GEMINI_API_KEY / GEMINI_API_KEYS to a .env file."
            )
        name, code = resolve_country(options["country"], options["country_code"])
        if not name:
            raise CommandError("Provide --country or a known --country-code.")

        run = PipelineRun.objects.create(
            country_name=name, country_code=code,
            crawl_mode="full", seed_provider="wikipedia", crawl_scope="gemini_grounding",
        )
        self.stdout.write(f"Run #{run.pk}: discovering {name} from Wikipedia...")
        run_discovery(run, limit=options["max"])
        valid = run.seeds.filter(status=InstitutionSeed.Status.VALID).count()
        self.stdout.write(f"  {run.seeds.count()} seeds ({valid} valid higher-ed).")

        self.stdout.write("Enriching from English Wikipedia (free)...")
        wiki = enrich_run_from_wikipedia(run)
        self.stdout.write(f"  staged {wiki['staged']} from Wikipedia.")

        if not options["no_crawl"]:
            from academic_etl.services.crawler import SiteCrawler
            crawler = SiteCrawler(
                max_pages=options["max_pages"] or None,
                use_dynamic_fallback=True if options["dynamic"] else None,
            )
            self.stdout.write(f"Crawling up to {options['crawl_limit']} official sites (free)...")
            crawl_run(run, limit=options["crawl_limit"], crawler=crawler)

        self.stdout.write("Gemini gap-fill (only institutions still missing required fields)...")
        stats = enrich_run_from_gemini(
            run, use_cache=not options["no_cache"], overwrite=False, skip_complete=True,
        )
        self.stdout.write(
            f"  Gemini: {stats['skipped_complete']} skipped (already complete), "
            f"called {stats['attempted']} (staged {stats['staged']}, "
            f"{stats['from_cache']} cache, {stats['errors']} errors)."
        )

        vstats = validate_run(run)
        self.stdout.write(self.style.SUCCESS(
            f"Run #{run.pk} done. Universities: {run.universities.count()}. "
            f"Validation: {vstats['universities']}. "
            f"Review + export at http://127.0.0.1:8000/etl/runs/{run.pk}/"
        ))
