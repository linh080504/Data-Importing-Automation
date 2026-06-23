"""One-shot builder: Wikipedia discovery -> English Wikipedia enrichment ->
official-site crawl -> validation. Produces an English academic catalog for a
country in a single command.

Examples:
    python manage.py build_country_catalog --country "Vietnam"
    python manage.py build_country_catalog --country "Vietnam" --max 60 --crawl-limit 30 --dynamic
    python manage.py build_country_catalog --country "Vietnam" --no-crawl   # Wikipedia-only
"""

from django.core.management.base import BaseCommand, CommandError

from academic_etl.models import InstitutionSeed, PipelineRun
from academic_etl.services.discovery import resolve_country, run_discovery
from academic_etl.services.pipeline import crawl_run, enrich_run_from_wikipedia
from academic_etl.services.validation import validate_run


class Command(BaseCommand):
    help = "Build an English academic catalog for a country from Wikipedia + official sites."

    def add_arguments(self, parser):
        parser.add_argument("--country", default="")
        parser.add_argument("--country-code", default="")
        parser.add_argument("--max", type=int, default=0,
                            help="Max institutions to discover (0 = all listed)")
        parser.add_argument("--crawl-limit", type=int, default=40,
                            help="Max official sites to crawl for programs/admissions")
        parser.add_argument("--max-pages", type=int, default=8, help="Max pages per official site")
        parser.add_argument("--dynamic", action="store_true",
                            help="Enable Scrapling dynamic fallback for JS-rendered sites")
        parser.add_argument("--no-crawl", action="store_true",
                            help="Wikipedia-only (skip official-site crawling)")

    def handle(self, *args, **options):
        name, code = resolve_country(options["country"], options["country_code"])
        if not name:
            raise CommandError("Provide --country or a known --country-code.")

        run = PipelineRun.objects.create(
            country_name=name, country_code=code,
            crawl_mode="full", seed_provider="wikipedia",
        )
        self.stdout.write(f"Run #{run.pk}: discovering {name} institutions from Wikipedia...")
        run_discovery(run, limit=options["max"])
        valid = run.seeds.filter(status=InstitutionSeed.Status.VALID).count()
        self.stdout.write(f"  discovered {run.seeds.count()} seeds ({valid} valid higher-ed).")

        self.stdout.write("Enriching with English Wikipedia article data...")
        enrich = enrich_run_from_wikipedia(run)
        self.stdout.write(f"  staged {enrich['staged']} universities from Wikipedia.")

        if not options["no_crawl"]:
            crawler = None
            if options["max_pages"] or options["dynamic"]:
                from academic_etl.services.crawler import SiteCrawler
                crawler = SiteCrawler(
                    max_pages=options["max_pages"] or None,
                    use_dynamic_fallback=True if options["dynamic"] else None,
                )
            self.stdout.write(f"Crawling up to {options['crawl_limit']} official sites (English-first)...")
            crawl_run(run, limit=options["crawl_limit"], crawler=crawler)

        stats = validate_run(run)
        self.stdout.write(self.style.SUCCESS(
            f"Run #{run.pk} done. Universities: {run.universities.count()}, "
            f"programs: {run.programs.count()}. Validation: {stats['universities']}. "
            f"Review + export at http://127.0.0.1:8000/etl/runs/{run.pk}/ "
            f"(Approve all valid, then download the English CSVs)."
        ))
