"""Manage scheduled crawl jobs per country.

Usage:
    python manage.py schedule_crawls --list
    python manage.py schedule_crawls --country "India" --frequency monthly
    python manage.py schedule_crawls --country "Vietnam" --frequency weekly --strategy hybrid
    python manage.py schedule_crawls --disable --country "India"
    python manage.py schedule_crawls --enable --country "India"
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from academic_etl.models import CrawlSchedule
from academic_etl.services.country_registry import resolve_country


class Command(BaseCommand):
    help = "Create, update, or list scheduled crawl jobs per country."

    def add_arguments(self, parser):
        parser.add_argument("--list", action="store_true", help="List all schedules")
        parser.add_argument("--country", type=str, default="", help="Country name")
        parser.add_argument(
            "--frequency", type=str, default="monthly",
            choices=["weekly", "biweekly", "monthly", "quarterly"],
        )
        parser.add_argument(
            "--strategy", type=str, default="hybrid",
            choices=["hybrid", "crawl", "gemini", "fanar"],
        )
        parser.add_argument("--limit", type=int, default=200, help="Discovery limit")
        parser.add_argument("--disable", action="store_true", help="Disable schedule for country")
        parser.add_argument("--enable", action="store_true", help="Enable schedule for country")

    def handle(self, *args, **options):
        if options["list"]:
            self._list_schedules()
            return

        country = options["country"]
        if not country:
            self.stderr.write(self.style.ERROR("--country is required (or use --list)"))
            return

        name, code = resolve_country(country)
        if not code:
            self.stderr.write(self.style.ERROR(f"Cannot resolve country: {country}"))
            return

        if options["disable"]:
            updated = CrawlSchedule.objects.filter(country_code=code).update(is_active=False)
            self.stdout.write(f"Disabled {updated} schedule(s) for {name}")
            return

        if options["enable"]:
            updated = CrawlSchedule.objects.filter(country_code=code).update(is_active=True)
            self.stdout.write(f"Enabled {updated} schedule(s) for {name}")
            return

        schedule, created = CrawlSchedule.objects.update_or_create(
            country_code=code,
            defaults={
                "country_name": name,
                "frequency": options["frequency"],
                "strategy": options["strategy"],
                "discover_limit": options["limit"],
                "is_active": True,
            },
        )
        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(
            f"{action} schedule: {name} ({code}) — {schedule.frequency} / {schedule.strategy}"
        ))

    def _list_schedules(self):
        schedules = CrawlSchedule.objects.order_by("country_name")
        if not schedules.exists():
            self.stdout.write("No schedules configured. Use --country to create one.")
            return

        self.stdout.write(f"{'Country':<25} {'Code':<5} {'Freq':<10} {'Strategy':<10} {'Active':<8} {'Last Run':<20} {'Next Run':<20}")
        self.stdout.write("-" * 100)
        for s in schedules:
            last = s.last_run_at.strftime("%Y-%m-%d %H:%M") if s.last_run_at else "never"
            nxt = s.next_run_at.strftime("%Y-%m-%d %H:%M") if s.next_run_at else "pending"
            active = "YES" if s.is_active else "NO"
            self.stdout.write(
                f"{s.country_name:<25} {s.country_code:<5} {s.frequency:<10} {s.strategy:<10} {active:<8} {last:<20} {nxt:<20}"
            )
