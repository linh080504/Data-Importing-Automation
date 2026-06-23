"""Discover higher-education institutions for a country (no crawling).

Examples:
    python manage.py discover_country_institutions --country "India" --limit 100
    python manage.py discover_country_institutions --country-code IN --limit 50
    python manage.py discover_country_institutions --country "India" --provider csv --csv sample_data/University_Import_Clean-7.csv
    python manage.py discover_country_institutions --country "Vietnam" --provider wikidata --limit 200
"""

from django.core.management.base import BaseCommand, CommandError

from academic_etl.models import PipelineRun
from academic_etl.services.discovery import resolve_country, run_discovery


class Command(BaseCommand):
    help = "Discover higher-education institutions for a country and stage them as seeds."

    def add_arguments(self, parser):
        parser.add_argument("--country", default="", help='Country name, e.g. "India"')
        parser.add_argument("--country-code", default="", help="ISO alpha-2 code, e.g. IN")
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--provider", default="hipolabs",
                            choices=["hipolabs", "csv", "wikidata", "wikipedia"])
        parser.add_argument("--csv", default="", help="CSV path (required for --provider csv)")

    def handle(self, *args, **options):
        name, code = resolve_country(options["country"], options["country_code"])
        if not name:
            raise CommandError("Provide --country or a known --country-code.")
        if options["provider"] == "csv" and not options["csv"]:
            raise CommandError("--provider csv requires --csv <path>.")
        if options["provider"] == "wikidata" and not code:
            raise CommandError(
                "--provider wikidata needs an ISO alpha-2 country code; pass "
                "--country-code (e.g. VN) or a country name the resolver knows."
            )

        run = PipelineRun.objects.create(
            country_name=name, country_code=code,
            crawl_mode="discover_only", seed_provider=options["provider"],
        )
        self.stdout.write(f"Created PipelineRun #{run.pk} for {name} ({code or '??'})")
        try:
            seeds = run_discovery(run, limit=options["limit"], csv_path=options["csv"])
        except Exception as exc:
            run.status = PipelineRun.Status.FAILED
            run.error_message = str(exc)[:2000]
            run.save()
            raise CommandError(f"Discovery failed: {exc}") from exc

        valid = run.seeds.filter(status="valid").count()
        invalid = run.seeds.filter(status="invalid").count()
        review = run.seeds.filter(status="needs_review").count()
        self.stdout.write(self.style.SUCCESS(
            f"Run #{run.pk}: {len(seeds)} new seeds "
            f"({valid} valid, {invalid} invalid, {review} needs_review). "
            f"Next: python manage.py crawl_country --run-id {run.pk} --limit 5"
        ))
