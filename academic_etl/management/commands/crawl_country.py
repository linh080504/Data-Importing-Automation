"""Discover (if needed) and crawl higher-education institutions for a country.

Examples:
    python manage.py crawl_country --country "India" --limit 20
    python manage.py crawl_country --country-code IN --institution-type university --limit 50
    python manage.py crawl_country --run-id 3 --limit 5          # crawl an existing discovery run
    python manage.py crawl_country --country "India" --provider csv --csv sample_data/University_Import_Clean-7.csv --limit 3
"""

from django.core.management.base import BaseCommand, CommandError

from academic_etl.models import InstitutionSeed, PipelineRun
from academic_etl.services.discovery import resolve_country, run_discovery
from academic_etl.services.pipeline import crawl_run


class Command(BaseCommand):
    help = "Crawl official sites of valid higher-education institutions in a country."

    def add_arguments(self, parser):
        parser.add_argument("--country", default="")
        parser.add_argument("--country-code", default="")
        parser.add_argument("--run-id", type=int, default=None,
                            help="Continue an existing run instead of discovering a new one")
        parser.add_argument("--limit", type=int, default=20, help="Max institutions to crawl")
        parser.add_argument("--discover-limit", type=int, default=100,
                            help="Max institutions to discover when starting a fresh run")
        parser.add_argument("--institution-type", default="",
                            help="Restrict crawl to one type, e.g. university")
        parser.add_argument("--provider", default="hipolabs",
                            choices=["hipolabs", "csv", "wikidata", "wikipedia"])
        parser.add_argument("--csv", default="")
        parser.add_argument("--max-pages", type=int, default=None, help="Max pages per site")
        parser.add_argument("--dynamic", action="store_true",
                            help="Enable Scrapling DynamicFetcher fallback for JS-rendered sites "
                                 "(requires `scrapling install` browsers)")

    def handle(self, *args, **options):
        if options["run_id"]:
            try:
                run = PipelineRun.objects.get(pk=options["run_id"])
            except PipelineRun.DoesNotExist:
                raise CommandError(f"PipelineRun #{options['run_id']} not found.")
            run.crawl_mode = "full"
            run.save(update_fields=["crawl_mode", "updated_at"])
        else:
            name, code = resolve_country(options["country"], options["country_code"])
            if not name:
                raise CommandError("Provide --country, --country-code or --run-id.")
            run = PipelineRun.objects.create(
                country_name=name, country_code=code,
                crawl_mode="full", seed_provider=options["provider"],
            )
            self.stdout.write(f"Created PipelineRun #{run.pk} for {name}; discovering seeds...")
            run_discovery(run, limit=options["discover_limit"], csv_path=options["csv"])

        seeds = run.seeds.filter(status=InstitutionSeed.Status.VALID).exclude(website="")
        if options["institution_type"]:
            seeds = seeds.filter(institution_type=options["institution_type"])
            excluded = run.seeds.filter(status=InstitutionSeed.Status.VALID)\
                .exclude(institution_type=options["institution_type"])\
                .update(status=InstitutionSeed.Status.SKIPPED)
            self.stdout.write(f"Type filter {options['institution_type']!r}: {excluded} valid seeds skipped.")

        self.stdout.write(
            f"Run #{run.pk}: {seeds.count()} crawlable seeds "
            f"(valid higher-education with website); crawling up to {options['limit']}..."
        )

        crawler_kwargs = {}
        if options["max_pages"] or options["dynamic"]:
            from academic_etl.services.crawler import SiteCrawler
            crawler_kwargs["crawler"] = SiteCrawler(
                max_pages=options["max_pages"] or None,
                use_dynamic_fallback=True if options["dynamic"] else None,
            )
            if options["dynamic"]:
                from academic_etl.services.scrapling_fetch import dynamic_available
                if dynamic_available():
                    self.stdout.write("Scrapling DynamicFetcher fallback ENABLED for JS-rendered sites.")
                else:
                    self.stdout.write(self.style.WARNING(
                        "--dynamic requested but Scrapling browsers are unavailable; "
                        "run `scrapling install`. Falling back to static crawl."
                    ))

        stats = crawl_run(run, limit=options["limit"], **crawler_kwargs)
        self.stdout.write(self.style.SUCCESS(
            f"Run #{run.pk} crawl done: {stats}. "
            f"Universities staged: {run.universities.count()}, programs: {run.programs.count()}. "
            f"Next: python manage.py validate_country_run --run-id {run.pk}"
        ))
