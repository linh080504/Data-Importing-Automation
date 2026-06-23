"""Check all active CrawlSchedule entries and run any that are due.

Designed to be called by a cron job:
    0 */6 * * * cd /path/to/beyond_degree && python manage.py run_scheduled_crawls

The command itself checks which countries are due based on frequency + last_run_at.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from academic_etl.models import CrawlSchedule, PipelineRun

logger = logging.getLogger(__name__)

FREQUENCY_DAYS = {
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
    "quarterly": 90,
}

MAX_CONSECUTIVE_ERRORS = 5


class Command(BaseCommand):
    help = "Run any scheduled crawls that are due."

    def add_arguments(self, parser):
        parser.add_argument("--report", action="store_true", help="Show status of all schedules without running")
        parser.add_argument("--force", type=str, default="", help="Force-run a specific country code even if not due")
        parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing")

    def handle(self, *args, **options):
        if options["report"]:
            self._report()
            return

        now = timezone.now()
        force_code = options["force"].strip().upper()

        schedules = CrawlSchedule.objects.filter(is_active=True)
        if force_code:
            schedules = schedules.filter(country_code=force_code)

        ran = 0
        for schedule in schedules:
            if schedule.error_count >= MAX_CONSECUTIVE_ERRORS:
                logger.warning(
                    "Skipping %s: %d consecutive errors (auto-disabled at %d)",
                    schedule.country_name, schedule.error_count, MAX_CONSECUTIVE_ERRORS,
                )
                schedule.is_active = False
                schedule.save(update_fields=["is_active"])
                continue

            if not force_code and not self._is_due(schedule, now):
                continue

            if options["dry_run"]:
                self.stdout.write(f"Would run: {schedule.country_name} ({schedule.strategy})")
                continue

            self.stdout.write(f"Running: {schedule.country_name} ({schedule.strategy})...")
            try:
                self._run_pipeline(schedule)
                schedule.error_count = 0
                ran += 1
            except Exception as exc:
                logger.exception("Scheduled crawl failed for %s", schedule.country_name)
                schedule.error_count += 1
                schedule.save(update_fields=["error_count"])
                self.stderr.write(self.style.ERROR(f"  FAILED: {exc}"))

        self.stdout.write(self.style.SUCCESS(f"Completed: {ran} scheduled crawl(s) executed."))

    def _is_due(self, schedule: CrawlSchedule, now) -> bool:
        if schedule.next_run_at and now >= schedule.next_run_at:
            return True
        if schedule.last_run_at is None:
            return True
        days = FREQUENCY_DAYS.get(schedule.frequency, 30)
        return now >= schedule.last_run_at + timedelta(days=days)

    def _run_pipeline(self, schedule: CrawlSchedule):
        from django.core.management import call_command

        strategy_map = {
            "hybrid": "build_country_hybrid",
            "crawl": "build_country_catalog",
            "gemini": "build_country_gemini",
            "fanar": "build_country_fanar",
        }
        cmd = strategy_map.get(schedule.strategy, "build_country_hybrid")

        try:
            call_command(
                cmd,
                country=schedule.country_name,
                max=schedule.discover_limit,
            )
        except Exception:
            # Try the catalog command as fallback if fanar command doesn't exist yet
            if schedule.strategy == "fanar":
                call_command(
                    "build_country_catalog",
                    country=schedule.country_name,
                )
            else:
                raise

        now = timezone.now()
        schedule.last_run_at = now
        days = FREQUENCY_DAYS.get(schedule.frequency, 30)
        schedule.next_run_at = now + timedelta(days=days)

        # Link to the most recent PipelineRun for this country
        latest_run = (
            PipelineRun.objects
            .filter(country_code=schedule.country_code)
            .order_by("-created_at")
            .first()
        )
        if latest_run:
            schedule.last_run = latest_run

        schedule.save()

    def _report(self):
        schedules = CrawlSchedule.objects.order_by("country_name")
        if not schedules.exists():
            self.stdout.write("No schedules configured.")
            return

        now = timezone.now()
        self.stdout.write(f"\n{'Country':<25} {'Status':<10} {'Errors':<8} {'Due?':<6} {'Last Run':<20}")
        self.stdout.write("-" * 75)
        for s in schedules:
            status = "ACTIVE" if s.is_active else "PAUSED"
            due = "YES" if self._is_due(s, now) else "no"
            last = s.last_run_at.strftime("%Y-%m-%d %H:%M") if s.last_run_at else "never"
            self.stdout.write(f"{s.country_name:<25} {status:<10} {s.error_count:<8} {due:<6} {last:<20}")
