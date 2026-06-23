"""One-shot builder using Fanar API as the primary enrichment source.

Flow: Wikipedia list discovery -> Fanar Chat Completions enrich university fields
+ majors/programs with specializations -> validate.

Fanar offers 50 req/min (vs Gemini ~20/day free tier), making it suitable for
countries with hundreds of institutions.

Requires FANAR_API_KEY in the environment or .env file.

Examples:
    python manage.py build_country_fanar --country "Vietnam"
    python manage.py build_country_fanar --country "India" --max 200
    python manage.py build_country_fanar --country "Japan" --with-majors
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from academic_etl.models import (
    DegreeLevel,
    ExtractedProgram,
    ExtractedSpecialization,
    ExtractedUniversity,
    FieldEvidence,
    InstitutionSeed,
    PipelineRun,
)
from academic_etl.services.country_registry import resolve_country
from academic_etl.services.discovery import run_discovery
from academic_etl.services.fanar_enrich import (
    FANAR_FIELDS,
    enrich_institution_fanar,
    enrich_majors_fanar,
    fanar_is_configured,
)
from academic_etl.services.normalize import make_slug, normalize_url
from academic_etl.services.validation import validate_run

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Build a country catalog: Wikipedia roster + Fanar API enrichment."

    def add_arguments(self, parser):
        parser.add_argument("--country", default="")
        parser.add_argument("--country-code", default="")
        parser.add_argument("--max", type=int, default=0, help="Max institutions to discover")
        parser.add_argument("--with-majors", action="store_true", help="Also enrich majors/programs")
        parser.add_argument("--no-cache", action="store_true", help="Ignore cached Fanar answers")

    def handle(self, *args, **options):
        if not fanar_is_configured():
            raise CommandError(
                "FANAR_API_KEY is not set. Add it to .env (FANAR_API_KEY=your_key)."
            )

        name, code = resolve_country(options["country"], options["country_code"])
        if not name:
            raise CommandError("Provide --country or a known --country-code.")

        run = PipelineRun.objects.create(
            country_name=name, country_code=code,
            crawl_mode="full", seed_provider="wikipedia",
            crawl_scope="fanar_enrichment",
        )
        self.stdout.write(f"Run #{run.pk}: discovering {name} institutions from Wikipedia...")
        run_discovery(run, limit=options["max"])
        valid_seeds = run.seeds.filter(status=InstitutionSeed.Status.VALID)
        total_valid = valid_seeds.count()
        self.stdout.write(f"  discovered {run.seeds.count()} seeds ({total_valid} valid higher-ed).")

        self.stdout.write("Enriching with Fanar API...")
        enriched = 0
        errors = 0

        for i, seed in enumerate(valid_seeds.iterator(), 1):
            self.stdout.write(f"  [{i}/{total_valid}] {seed.name}...", ending="")

            result = enrich_institution_fanar(
                name=seed.name,
                country=name,
                country_code=code,
                city=seed.city,
                wikipedia_url=seed.wikipedia_url,
            )

            if not result:
                self.stdout.write(" SKIP (no data)")
                errors += 1
                continue

            # Create or update ExtractedUniversity
            uni, _ = ExtractedUniversity.objects.update_or_create(
                pipeline_run=run, seed=seed,
                defaults={
                    "name": result.get("name") or seed.name,
                    "website": normalize_url(result.get("website", "")),
                    "description": result.get("description", ""),
                    "campus_student_life": result.get("campus_student_life", ""),
                    "number_of_students": result.get("number_of_students"),
                    "financials": result.get("financials", ""),
                    "global_rank": result.get("global_rank", ""),
                    "student_to_faculty_ratio": result.get("student_to_faculty_ratio", ""),
                    "international_student_ratio": result.get("international_student_ratio", ""),
                    "student_loan_available": result.get("student_loan_available"),
                    "housing_availability": result.get("housing_availability"),
                    "admissions_contact": result.get("admissions_contact", ""),
                    "admissions_phone": result.get("admissions_phone", ""),
                    "admissions_page_link": result.get("admissions_page_link", ""),
                    "contact_person": result.get("contact_person", ""),
                    "immigration_support": result.get("immigration_support"),
                    "university_campuses": result.get("university_campuses"),
                    "country": name,
                    "country_code": code,
                    "city": seed.city,
                    "region": seed.region,
                    "institution_type": seed.institution_type,
                    "slug": make_slug(result.get("name") or seed.name, seed.city),
                    "confidence_score": 0.80,
                },
            )

            # Create FieldEvidence for each extracted field
            now = timezone.now()
            for field in FANAR_FIELDS:
                val = result.get(field)
                if val is not None and val != "":
                    FieldEvidence.objects.create(
                        entity_type="university",
                        entity_id=uni.pk,
                        field_name=field,
                        extracted_value=str(val),
                        normalized_value=str(val),
                        source_url=f"fanar-api:{seed.name}",
                        page_type="fanar_enrichment",
                        confidence_score=0.80,
                        extractor_name="fanar_chat_completion",
                        extraction_method="fanar_enrichment",
                        crawled_at=now,
                    )

            enriched += 1
            self.stdout.write(" OK")

            # Optionally enrich majors
            if options["with_majors"]:
                self._enrich_majors(run, uni, name, code)

        seed_status = InstitutionSeed.Status.CRAWLED
        valid_seeds.update(status=seed_status)

        self.stdout.write(f"\nEnriched {enriched}/{total_valid} institutions ({errors} errors).")
        self.stdout.write("Validating...")
        validate_run(run)

        run.status = PipelineRun.Status.REVIEW
        run.total_crawled_institutions = enriched
        run.save(update_fields=["status", "total_crawled_institutions"])
        self.stdout.write(self.style.SUCCESS(
            f"Done. Run #{run.pk} ready for review at /etl/runs/{run.pk}/"
        ))

    def _enrich_majors(self, run, uni, country_name, country_code):
        majors = enrich_majors_fanar(
            name=uni.name, country=country_name, country_code=country_code,
        )
        for major in majors:
            prog_name = major.get("program_name", "").strip()
            if not prog_name:
                continue

            degree = major.get("degree_level", "unknown").lower()
            if degree not in {d.value for d in DegreeLevel}:
                degree = "unknown"

            prog, _ = ExtractedProgram.objects.get_or_create(
                pipeline_run=run,
                extracted_university=uni,
                program_name=prog_name,
                degree_level=degree,
                defaults={
                    "faculty_or_school": major.get("faculty_or_school", ""),
                    "field_of_study": major.get("field_of_study", ""),
                    "duration": major.get("duration", ""),
                    "tuition_fee": major.get("tuition_fee", ""),
                    "program_url": major.get("program_url", ""),
                    "country": country_name,
                    "country_code": country_code,
                    "university_slug": uni.slug,
                    "is_higher_education_program": True,
                    "confidence_score": 0.75,
                },
            )

            # Create specializations (3rd level)
            for spec_name in major.get("specializations", []):
                spec_name = spec_name.strip()
                if spec_name:
                    ExtractedSpecialization.objects.get_or_create(
                        pipeline_run=run,
                        extracted_program=prog,
                        specialization_name=spec_name,
                        defaults={
                            "source_url": f"fanar-api:{uni.name}",
                            "confidence_score": 0.70,
                        },
                    )
