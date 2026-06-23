"""Fetch current exchange rates and store them in the ExchangeRate model.

Usage:
    python manage.py refresh_exchange_rates
    python manage.py refresh_exchange_rates --currencies VND,INR,GBP
"""

from django.core.management.base import BaseCommand

from academic_etl.services.financial import fetch_exchange_rates


class Command(BaseCommand):
    help = "Fetch and cache current exchange rates from frankfurter.app."

    def add_arguments(self, parser):
        parser.add_argument(
            "--currencies", type=str, default="",
            help="Comma-separated currency codes to fetch (default: all)",
        )

    def handle(self, *args, **options):
        currencies = None
        if options["currencies"]:
            currencies = [c.strip().upper() for c in options["currencies"].split(",") if c.strip()]

        rates = fetch_exchange_rates(currencies)
        self.stdout.write(self.style.SUCCESS(f"Fetched {len(rates)} exchange rates."))
        for code in sorted(rates)[:10]:
            self.stdout.write(f"  1 USD = {rates[code]} {code}")
        if len(rates) > 10:
            self.stdout.write(f"  ... and {len(rates) - 10} more")
