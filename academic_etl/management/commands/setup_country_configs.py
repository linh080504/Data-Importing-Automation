"""Bootstrap CountryConfig rows from the built-in defaults in country_registry.

Safe to re-run: uses update_or_create so existing rows get updated without
duplicates. New countries added to the registry defaults will be created;
manually-added DB rows are preserved.

Usage:
    python manage.py setup_country_configs
    python manage.py setup_country_configs --only VN,IN,US
"""

from django.core.management.base import BaseCommand

from academic_etl.models import CountryConfig
from academic_etl.services.country_registry import _DEFAULTS, clear_cache


class Command(BaseCommand):
    help = "Create or update CountryConfig rows from built-in defaults."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only", type=str, default="",
            help="Comma-separated country codes to seed (default: all)",
        )

    def handle(self, *args, **options):
        only = [c.strip().upper() for c in options["only"].split(",") if c.strip()] if options["only"] else None
        created = updated = 0

        for code, cfg in _DEFAULTS.items():
            if only and code not in only:
                continue

            _, was_created = CountryConfig.objects.update_or_create(
                country_code=code,
                defaults={
                    "country_name": cfg["country_name"],
                    "currency_code": cfg["currency_code"],
                    "numeric_code": cfg.get("numeric_code", ""),
                    "denomination_config": cfg.get("denomination_config", {}),
                    "primary_languages": cfg.get("primary_languages", []),
                    "url_language_markers": cfg.get("url_language_markers", []),
                    "degree_level_map": cfg.get("degree_level_map", {}),
                    "preferred_providers": cfg.get("preferred_providers", []),
                    "max_institutions": 200,
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        clear_cache()
        self.stdout.write(self.style.SUCCESS(
            f"Done: {created} created, {updated} updated ({created + updated} total countries)."
        ))
