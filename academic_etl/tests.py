"""Smoke tests for the academic ETL pipeline. No network access required."""

import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.core.management import call_command
from django.db import OperationalError, connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from universities.models import Program, University

from . import views
from .models import (
    DataResetJob,
    DegreeLevel,
    ExtractedProgram,
    ExtractedUniversity,
    FieldEvidence,
    ImportJob,
    InstitutionSeed,
    PipelineRun,
    ReviewStatus,
    ValidationIssue,
    ValidationStatus,
)
from .services.classification import classify_institution
from .services.csv_seed import parse_csv_rows
from .services.extraction import classify_degree_level, extract_programs, extract_university_fields
from .services.importer import import_run
from .services.normalize import (
    fix_mojibake,
    normalize_bool,
    normalize_email,
    normalize_phone,
    normalize_url,
)
from .services.validation import validate_run

SAMPLE_CSV = Path(__file__).resolve().parent.parent / "sample_data" / "University_Import_Clean-7.csv"


class CsvSeedTests(TestCase):
    def test_misaligned_csv_is_realigned(self):
        if not SAMPLE_CSV.exists():
            self.skipTest("sample CSV not present")
        records = parse_csv_rows(str(SAMPLE_CSV))
        self.assertGreater(len(records), 100)
        aligned = [r for r in records if not r["suspicious"]]
        # the sample file's rows are all alignable despite the shifted header
        self.assertGreater(len(aligned) / len(records), 0.9)
        first = aligned[0]["fields"]
        self.assertEqual(first["name"], "VTM NSS College")
        self.assertEqual(first["country"], "India")
        self.assertEqual(first["country_code"], "IN")
        self.assertEqual(first["slug"], "vtm-nss-college-dhanuvachapuram")
        self.assertEqual(first["normalized"]["website"], "https://vtmnsscollege.ac.in")
        self.assertEqual(first["normalized"]["number_of_students"], 1783)

    def test_csv_numeric_country_code_uses_registry(self):
        from .services.csv_seed import load_mapping_config

        config = load_mapping_config()
        row = (
            '"Example Hochschule, Germany",276,Description,example-hochschule,0,'
            'https://example.de,,EUR 1k-2k ($1100-2200),0,Campus life,1000,'
            '20:1,5%,1,admissions@example.de,+493012345678,Registrar,'
            'https://example.de/admissions,1,2'
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "global.csv"
            path.write_text(",".join(config["canonical_fields"]) + "\n" + row, encoding="utf-8")
            records = parse_csv_rows(str(path), config=config)

        fields = records[0]["fields"]
        self.assertEqual(fields["name"], "Example Hochschule")
        self.assertEqual(fields["country"], "Germany")
        self.assertEqual(fields["country_code"], "DE")
        self.assertEqual(fields["location"], "Germany")

    def test_mojibake_repair(self):
        self.assertEqual(fix_mojibake("decades â€” shaping"), "decades — shaping")
        self.assertEqual(fix_mojibake("plain text"), "plain text")


class FinancialFormatTests(TestCase):
    def test_standardize_financials_outputs_sample_csv_format(self):
        from .services.financial import is_canonical_financials, standardize_financials

        india = standardize_financials("INR 1.5L-3L ($1800-3600)", country_code="IN")
        vietnam = standardize_financials("VND 20tr-40tr ($800-1600)", country_code="VN")

        self.assertEqual(india["formatted"], "INR 150k-300k ($1800-3600)")
        self.assertEqual(vietnam["formatted"], "VND 20m-40m ($800-1600)")
        self.assertTrue(is_canonical_financials(india["formatted"], "IN"))
        self.assertTrue(is_canonical_financials(vietnam["formatted"], "VN"))
        self.assertFalse(is_canonical_financials("INR 1.5L-3L ($1800-3600)", "IN"))
        self.assertFalse(is_canonical_financials("Tuition is INR 50k per year", "IN"))


class ClassificationTests(TestCase):
    def test_valid_types(self):
        cases = {
            "University of Kerala": ("university", InstitutionSeed.Status.VALID),
            "Indian Institute of Technology Madras": ("institute_of_technology", InstitutionSeed.Status.VALID),
            "Government Polytechnic Pune": ("polytechnic", InstitutionSeed.Status.VALID),
            "Harvard Business School": ("business_school", InstitutionSeed.Status.VALID),
            "VTM NSS College": ("college", InstitutionSeed.Status.NEEDS_REVIEW),
        }
        for name, (expected_type, expected_status) in cases.items():
            itype, status, _ = classify_institution(name)
            self.assertEqual(itype, expected_type, name)
            self.assertEqual(status, expected_status, name)

    def test_invalid_types_are_excluded(self):
        for name in ("St Mary High School", "ABC Language Center",
                     "XYZ Coaching Classes", "Code Bootcamp Delhi"):
            _, status, _ = classify_institution(name)
            self.assertEqual(status, InstitutionSeed.Status.INVALID, name)

    def test_uncertain_goes_to_needs_review(self):
        _, status, _ = classify_institution("Shanti Niketan")
        self.assertEqual(status, InstitutionSeed.Status.NEEDS_REVIEW)


class NormalizeTests(TestCase):
    def test_normalizers(self):
        self.assertEqual(normalize_url("vtmnsscollege.ac.in/"), "https://vtmnsscollege.ac.in")
        self.assertEqual(normalize_url("not a url"), "")
        self.assertEqual(normalize_email("Mail: Admissions@Uni.EDU now"), "admissions@uni.edu")
        self.assertEqual(normalize_phone("Call +91 471-223 2240"), "+914712232240")
        self.assertEqual(normalize_phone("+91 99380 47999"), "+919938047999")
        self.assertEqual(normalize_phone("Phone: 0091 99380 47999"), "+919938047999")
        self.assertEqual(normalize_phone("2023-2024"), "")
        self.assertEqual(normalize_phone("+91 2023-2024"), "")
        self.assertTrue(normalize_bool("1"))
        self.assertFalse(normalize_bool("0"))
        self.assertIsNone(normalize_bool(""))

    def test_fanar_output_normalization_keeps_numeric_fields_nullable(self):
        from .services.fanar_enrich import _normalize_contact_fields

        values = _normalize_contact_fields({
            "website": "example.edu",
            "admissions_page_link": "example.edu/admissions",
            "admissions_contact": "Mail: Admissions@Example.EDU",
            "admissions_phone": "Call +91 99380 47999",
            "number_of_students": "12,500 students",
            "university_campuses": None,
            "housing_availability": "yes",
            "student_loan_available": "",
            "immigration_support": False,
        })

        self.assertEqual(values["website"], "https://example.edu")
        self.assertEqual(values["admissions_page_link"], "https://example.edu/admissions")
        self.assertEqual(values["admissions_contact"], "admissions@example.edu")
        self.assertEqual(values["admissions_phone"], "+919938047999")
        self.assertEqual(values["number_of_students"], 12500)
        self.assertIsNone(values["university_campuses"])
        self.assertTrue(values["housing_availability"])
        self.assertIsNone(values["student_loan_available"])
        self.assertFalse(values["immigration_support"])


class QualityEnrichmentTests(TestCase):
    def setUp(self):
        self.run = PipelineRun.objects.create(country_name="India", country_code="IN")
        self.uni = ExtractedUniversity.objects.create(
            pipeline_run=self.run,
            name="Example University",
            website="https://example.edu",
            country="India",
            country_code="IN",
            sponsored=True,
        )

    @staticmethod
    def _campus_life():
        return (
            "The main campus has a central library and laboratories used by undergraduate students. "
            "University residence halls provide documented accommodation near the teaching buildings. "
            "Students participate in sports facilities, academic clubs, and annual cultural activities."
        )

    def test_grounded_values_are_validated_and_persisted_with_evidence(self):
        from academic_etl.services.quality_enrichment import apply_quality_result

        sources = [
            "https://example.edu/fees",
            "https://example.edu/campuses",
            "https://example.edu/contact",
            "https://example.edu/student-life",
            "https://www.topuniversities.com/example-university",
        ]
        result = {
            "sources": sources,
            "error": "",
            "fields": {
                "financials": {"status": "verified", "value": "INR 50k-200k ($600-2400)", "period": "annual", "source_url": sources[0], "confidence": 0.9},
                "university_campuses": {"status": "verified", "value": 3, "source_url": sources[1], "confidence": 0.9},
                "admissions_contact": {"status": "verified", "value": "admissions@example.edu", "source_url": sources[2], "confidence": 0.95},
                "global_rank": {"status": "verified", "value": "QS 801-1000", "source_url": sources[4], "confidence": 0.9},
                "campus_student_life": {"status": "verified", "value": self._campus_life(), "source_url": sources[3], "confidence": 0.85},
            },
        }

        changed = apply_quality_result(
            self.uni,
            {"financials", "university_campuses", "admissions_contact", "global_rank", "campus_student_life"},
            result,
        )

        self.uni.refresh_from_db()
        self.assertFalse(self.uni.sponsored)
        self.assertEqual(self.uni.university_campuses, 3)
        self.assertEqual(self.uni.admissions_contact, "admissions@example.edu")
        self.assertEqual(self.uni.global_rank, "QS 801-1000")
        self.assertEqual(self.uni.financials, "INR 50k-200k ($600-2400)")
        self.assertIn("campus_student_life", changed)
        self.assertEqual(
            FieldEvidence.objects.filter(
                entity_type="university",
                entity_id=self.uni.pk,
                extraction_method="gemini_grounded",
            ).count(),
            5,
        )

    def test_untrusted_sources_and_non_qs_rank_are_rejected(self):
        from academic_etl.services.quality_enrichment import apply_quality_result

        bad_source = "https://directory.example/contact"
        rank_source = "https://www.nirfindia.org/example"
        apply_quality_result(
            self.uni,
            {"admissions_contact", "university_campuses", "global_rank"},
            {
                "sources": [bad_source, rank_source],
                "error": "",
                "fields": {
                    "admissions_contact": {"status": "verified", "value": "info@example.edu", "source_url": bad_source, "confidence": 0.9},
                    "university_campuses": {"status": "verified", "value": 9, "source_url": bad_source, "confidence": 0.9},
                    "global_rank": {"status": "verified", "value": "NIRF 25", "source_url": rank_source, "confidence": 0.9},
                },
            },
        )

        self.uni.refresh_from_db()
        self.assertEqual(self.uni.admissions_contact, "")
        self.assertIsNone(self.uni.university_campuses)
        self.assertEqual(self.uni.global_rank, "")
        states = self.uni.normalized_json["_quality_resolution"]
        self.assertEqual(states["admissions_contact"]["status"], "unavailable")
        self.assertEqual(states["university_campuses"]["status"], "unavailable")
        self.assertEqual(states["global_rank"]["status"], "unavailable")

    def test_verified_absent_qs_rank_has_distinct_status(self):
        from academic_etl.services.quality_enrichment import apply_quality_result

        source = "https://www.topuniversities.com/universities/example-university"
        apply_quality_result(
            self.uni,
            {"global_rank"},
            {
                "sources": [source],
                "error": "",
                "fields": {
                    "global_rank": {"status": "verified_absent", "value": "", "source_url": source, "confidence": 0.8},
                },
            },
        )

        self.uni.refresh_from_db()
        state = self.uni.normalized_json["_quality_resolution"]["global_rank"]
        self.assertEqual(self.uni.global_rank, "")
        self.assertEqual(state["status"], "verified_absent")

    def test_campus_life_rejects_noise_and_non_english(self):
        from academic_etl.services.quality_enrichment import campus_life_is_usable

        self.assertTrue(campus_life_is_usable(self._campus_life()))
        self.assertFalse(campus_life_is_usable("Apply Now Exam Result Online Payment IQAC NIRF" * 8))
        self.assertFalse(campus_life_is_usable("विश्वविद्यालय परिसर छात्र गतिविधियों और पुस्तकालयों की जानकारी प्रदान करता है।" * 4))

    def test_quality_gate_requires_evidence_for_campus_default(self):
        from academic_etl.services.quality_enrichment import quality_fields_needed

        self.uni.university_campuses = 1
        self.uni.save(update_fields=["university_campuses"])

        self.assertIn("university_campuses", quality_fields_needed(self.uni))

    def test_quality_gate_keeps_valid_crawled_phone_without_api(self):
        from academic_etl.services.quality_enrichment import quality_fields_needed

        self.uni.admissions_phone = "+911126596631"
        self.uni.save(update_fields=["admissions_phone"])
        FieldEvidence.objects.create(
            entity_type="university",
            entity_id=self.uni.pk,
            field_name="admissions_phone",
            extracted_value=self.uni.admissions_phone,
            normalized_value=self.uni.admissions_phone,
            source_url="https://example.edu/contact",
            confidence_score=0.8,
            extraction_method="web_scrape",
        )

        self.assertNotIn("admissions_phone", quality_fields_needed(self.uni))

    def test_post_process_keeps_unknown_campus_null_and_forces_sponsored_false(self):
        ExtractedUniversity.objects.filter(pk=self.uni.pk).update(
            sponsored=True,
            university_campuses=None,
        )

        views._post_process_run(self.run)

        self.uni.refresh_from_db()
        self.assertFalse(self.uni.sponsored)
        self.assertIsNone(self.uni.university_campuses)

    def test_live_import_forces_existing_sponsored_to_false(self):
        self.uni.slug = "example-university"
        self.uni.review_status = ReviewStatus.APPROVED
        self.uni.validation_status = ValidationStatus.VALID
        self.uni.confidence_score = 1.0
        self.uni.save()
        live = University.objects.create(
            name=self.uni.name,
            slug=self.uni.slug,
            sponsored=True,
        )

        import_run(self.run, dry_run=False, approved_only=True)

        live.refresh_from_db()
        self.assertFalse(live.sponsored)

    def test_review_ui_hides_api_error_badge(self):
        self.uni.normalized_json = {
            "_quality_resolution": {
                "global_rank": {"status": "verified_absent", "provider": "fanar", "source_url": "https://www.topuniversities.com/example"},
                "university_campuses": {"status": "error", "reason": "source is not grounded"},
            }
        }
        self.uni.save(update_fields=["normalized_json"])

        response = self.client.get(
            reverse("academic_etl:universities_list", args=[self.run.pk])
        )

        self.assertContains(response, "Not ranked (QS/THE)")
        self.assertNotContains(response, "API error")
        self.assertContains(response, "provider=fanar")

    def test_review_ui_shows_ai_is_pending_before_quality_stage(self):
        self.run.status = PipelineRun.Status.CRAWLING
        self.run.execution_state = {
            "current_stage": "web_sources",
            "completed_stages": ["wikipedia"],
        }
        self.run.save(update_fields=["status", "execution_state"])

        response = self.client.get(
            reverse("academic_etl:universities_list", args=[self.run.pk])
        )

        self.assertContains(response, "Waiting for AI")
        self.assertContains(response, "Stage 4/6")
        self.assertNotContains(response, "Not checked")

    def test_review_ui_hides_unavailable_quality_badges(self):
        self.uni.normalized_json = {
            "_quality_resolution": {
                "financials": {"status": "unavailable", "reason": "no verified source"},
            }
        }
        self.uni.save(update_fields=["normalized_json"])

        response = self.client.get(
            reverse("academic_etl:universities_list", args=[self.run.pk])
        )

        self.assertNotContains(response, "Unknown")

    def test_review_ui_hides_source_free_legacy_fanar_campus_count(self):
        self.uni.university_campuses = 35
        self.uni.normalized_json = {
            "_quality_resolution": {
                "university_campuses": {
                    "status": "verified",
                    "provider": "fanar",
                    "source_url": "",
                }
            }
        }
        self.uni.save(update_fields=["university_campuses", "normalized_json"])

        response = self.client.get(
            reverse("academic_etl:universities_list", args=[self.run.pk])
        )

        self.assertNotContains(response, ">35<")

    @override_settings(GEMINI_CONCURRENCY=3)
    def test_batch_calls_once_per_university_and_continues_after_errors(self):
        for index in range(2):
            ExtractedUniversity.objects.create(
                pipeline_run=self.run,
                name=f"University {index}",
                website=f"https://university{index}.edu",
                country="India",
                country_code="IN",
            )
        progress = []
        with patch(
            "academic_etl.services.quality_enrichment.enrich_university_quality_hybrid",
            side_effect=lambda **kwargs: {
                "fanar_candidates": {},
                "gemini_result": {"fields": {}, "sources": [], "error": "quota unavailable"},
                "remaining": kwargs["needed"],
                "fanar_calls": len(kwargs["needed"]),
                "gemini_calls": 1,
                "fanar_errors": len(kwargs["needed"]),
            },
        ) as enrich:
            views._ai_fill_gaps(
                self.run,
                progress_callback=lambda **values: progress.append(values),
            )

        self.assertEqual(enrich.call_count, 3)
        self.assertEqual(progress[-1]["processed"], 3)
        for university in self.run.universities.all():
            self.assertIsNone(university.university_campuses)
            states = university.normalized_json["_quality_resolution"]
            self.assertTrue(all(state["status"] == "error" for field, state in states.items() if field != "sponsored"))

    @override_settings(GEMINI_API_KEY="test-key")
    def test_quality_cache_is_versioned_and_reused(self):
        from academic_etl.services.quality_enrichment import enrich_university_quality

        payload = {
            field: {"status": "unavailable", "value": "", "source_url": "", "confidence": 0}
            for field in ("financials", "university_campuses", "admissions_contact", "global_rank", "campus_student_life")
        }
        payload["sponsored"] = {"status": "verified", "value": False, "source_url": "", "confidence": 1}
        response = SimpleNamespace(text=json.dumps(payload), candidates=[])
        with TemporaryDirectory() as temp_dir, override_settings(GEMINI_CACHE_DIR=Path(temp_dir)):
            with patch("academic_etl.services.quality_enrichment._generate", return_value=(response, "test-model", "")) as generate:
                first = enrich_university_quality(
                    name=self.uni.name, country="India", country_code="IN", website=self.uni.website,
                )
                second = enrich_university_quality(
                    name=self.uni.name, country="India", country_code="IN", website=self.uni.website,
                )

        self.assertEqual(generate.call_count, 1)
        self.assertFalse(first["from_cache"])
        self.assertTrue(second["from_cache"])
        self.assertEqual(first["prompt_version"], "university-quality-v2")

    @override_settings(FANAR_API_KEY="test-key")
    def test_fanar_field_cache_is_versioned_and_reused(self):
        from academic_etl.services.quality_enrichment import enrich_quality_field_fanar

        response = json.dumps({
            "status": "verified",
            "value": "+91 11 2659 6631",
            "confidence": 0.8,
        })
        with TemporaryDirectory() as temp_dir, override_settings(FANAR_CACHE_DIR=Path(temp_dir)):
            with patch(
                "academic_etl.services.fanar_enrich._chat_completion",
                return_value=response,
            ) as chat:
                first = enrich_quality_field_fanar(
                    "admissions_phone",
                    name=self.uni.name,
                    country="India",
                    country_code="IN",
                    website=self.uni.website,
                )
                second = enrich_quality_field_fanar(
                    "admissions_phone",
                    name=self.uni.name,
                    country="India",
                    country_code="IN",
                    website=self.uni.website,
                )

        self.assertEqual(chat.call_count, 1)
        self.assertFalse(first["from_cache"])
        self.assertTrue(second["from_cache"])
        self.assertEqual(first["prompt_version"], "university-field-v2")

    def test_fanar_campus_count_is_derived_from_unique_names(self):
        from academic_etl.services.quality_enrichment import validate_fanar_candidate

        candidate = validate_fanar_candidate(
            "university_campuses",
            {
                "status": "verified",
                "campus_names": ["Main Campus", "City Campus", "main campus"],
                "source_url": "https://example.edu/campuses",
                "confidence": 0.8,
            },
            country_code="IN",
            website=self.uni.website,
        )

        self.assertEqual(candidate["campus_names"], ["Main Campus", "City Campus"])
        self.assertEqual(candidate["value"], 2)
        self.assertEqual(
            validate_fanar_candidate(
                "university_campuses",
                {"status": "verified", "value": 4, "campus_names": []},
                country_code="IN",
                website=self.uni.website,
            ),
            {},
        )
        self.assertEqual(
            validate_fanar_candidate(
                "university_campuses",
                {
                    "status": "verified",
                    "campus_names": ["Main Campus", "City Campus"],
                    "confidence": 0.8,
                },
                country_code="IN",
                website=self.uni.website,
            ),
            {},
        )

    def test_hybrid_asks_fanar_per_field_then_gemini_once_for_failures(self):
        from academic_etl.services.quality_enrichment import enrich_university_quality_hybrid

        def fanar_response(field, **kwargs):
            if field == "university_campuses":
                item = {
                    "status": "verified",
                    "campus_names": ["Main Campus", "Technology Campus"],
                    "source_url": "https://example.edu/campuses",
                    "confidence": 0.8,
                }
            elif field == "admissions_contact":
                item = {"status": "verified", "value": "example@gmail.com", "confidence": 0.8}
            else:
                item = {"status": "unavailable", "value": "", "confidence": 0}
            return {"field": field, "item": item, "error": ""}

        needed = {"university_campuses", "admissions_contact", "admissions_phone"}
        with (
            patch("academic_etl.services.fanar_enrich.fanar_is_configured", return_value=True),
            patch(
                "academic_etl.services.quality_enrichment.enrich_quality_field_fanar",
                side_effect=fanar_response,
            ) as fanar,
            patch("academic_etl.services.quality_enrichment.is_configured", return_value=True),
            patch(
                "academic_etl.services.quality_enrichment.enrich_university_quality",
                return_value={"fields": {}, "sources": [], "error": ""},
            ) as gemini,
        ):
            result = enrich_university_quality_hybrid(
                name=self.uni.name,
                country="India",
                country_code="IN",
                website=self.uni.website,
                needed=needed,
            )

        self.assertEqual(fanar.call_count, 3)
        self.assertEqual(gemini.call_count, 1)
        self.assertEqual(result["fanar_candidates"]["university_campuses"]["value"], 2)
        self.assertEqual(result["remaining"], {"admissions_contact", "admissions_phone"})
        self.assertEqual(
            set(gemini.call_args.kwargs["requested_fields"]),
            {"admissions_contact", "admissions_phone"},
        )

    def test_post_process_removes_legacy_source_free_fanar_campus_count(self):
        self.uni.university_campuses = 10
        self.uni.normalized_json = {
            "_quality_resolution": {
                "university_campuses": {
                    "status": "verified",
                    "provider": "fanar",
                    "source_url": "",
                },
                "admissions_contact": {
                    "status": "error",
                    "provider": "gemini",
                    "reason": "source is not grounded",
                },
            }
        }
        self.uni.save(update_fields=["university_campuses", "normalized_json"])

        views._post_process_run(self.run)

        self.uni.refresh_from_db()
        self.assertIsNone(self.uni.university_campuses)
        state = self.uni.normalized_json["_quality_resolution"]["university_campuses"]
        self.assertEqual(state["status"], "unavailable")
        self.assertEqual(
            self.uni.normalized_json["_quality_resolution"]["admissions_contact"]["status"],
            "unavailable",
        )

    def test_fanar_phone_and_financial_validators_reject_bad_formats(self):
        from academic_etl.services.quality_enrichment import validate_fanar_candidate

        valid_phone = validate_fanar_candidate(
            "admissions_phone",
            {"status": "verified", "value": "+91 11 2659 6631", "confidence": 0.8},
            country_code="IN",
            website=self.uni.website,
        )
        self.assertEqual(valid_phone["value"], "+911126596631")
        valid_financial = validate_fanar_candidate(
            "financials",
            {
                "status": "verified", "currency": "INR", "amount_low": 50000,
                "amount_high": 200000, "usd_low": 600, "usd_high": 2400,
                "period": "annual", "confidence": 0.8,
            },
            country_code="IN",
            website=self.uni.website,
        )
        self.assertEqual(valid_financial["value"], "INR 50k-200k ($600-2400)")
        self.assertEqual(
            validate_fanar_candidate(
                "admissions_phone",
                {"status": "verified", "value": "2023-2024", "confidence": 0.8},
                country_code="IN",
                website=self.uni.website,
            ),
            {},
        )
        self.assertEqual(
            validate_fanar_candidate(
                "financials",
                {
                    "status": "verified", "currency": "USD", "amount_low": 1000,
                    "amount_high": 2000, "usd_low": 1000, "usd_high": 2000,
                    "period": "annual", "confidence": 0.8,
                },
                country_code="IN",
                website=self.uni.website,
            ),
            {},
        )


class ContactDataQualityTests(TestCase):
    def test_normalize_data_action_repairs_existing_contact_values(self):
        run = PipelineRun.objects.create(country_name="India", country_code="IN")
        uni = ExtractedUniversity.objects.create(
            pipeline_run=run,
            name="Example University",
            website="www.example.edu",
            admissions_contact="Admissions@Example.EDU",
            admissions_phone="+91 2023-2024",
            admissions_page_link="admissions.example.edu/contact",
        )

        response = self.client.post(
            reverse("academic_etl:run_normalize_data_action", args=[run.pk])
        )

        self.assertRedirects(response, reverse("academic_etl:universities_list", args=[run.pk]))
        uni.refresh_from_db()
        self.assertEqual(uni.website, "https://www.example.edu")
        self.assertEqual(uni.admissions_contact, "admissions@example.edu")
        self.assertEqual(uni.admissions_phone, "")
        self.assertEqual(uni.admissions_page_link, "https://admissions.example.edu/contact")


class UnifiedWorkerTests(TestCase):
    def test_worker_launcher_uses_a_separate_management_process(self):
        from academic_etl.services.unified_worker import launch_unified_worker

        with patch("academic_etl.services.unified_worker.subprocess.Popen") as popen:
            popen.return_value.pid = 4242
            pid = launch_unified_worker(99)

        self.assertEqual(pid, 4242)
        args, kwargs = popen.call_args
        self.assertIn("run_unified_pipeline", args[0])
        self.assertIn("--run-id", args[0])
        self.assertIn("99", args[0])
        self.assertIn("cwd", kwargs)

    def test_management_worker_invokes_the_unified_pipeline(self):
        run = PipelineRun.objects.create(country_name="India", country_code="IN")

        with patch("academic_etl.views.run_unified_pipeline") as worker:
            call_command("run_unified_pipeline", "--run-id", run.pk)

        worker.assert_called_once_with(run.pk, worker_token="")

    def test_worker_launcher_passes_token_and_records_pid(self):
        from academic_etl.services.unified_worker import launch_unified_worker

        with (
            patch("academic_etl.services.unified_worker.subprocess.Popen") as popen,
            patch("academic_etl.services.pipeline_execution.record_worker_pid") as record_pid,
        ):
            popen.return_value.pid = 4242
            pid = launch_unified_worker(99, "worker-token")

        self.assertEqual(pid, 4242)
        command = popen.call_args.args[0]
        self.assertIn("--worker-token", command)
        self.assertIn("worker-token", command)
        record_pid.assert_called_once_with(99, "worker-token", 4242)


class PipelineExecutionTests(TestCase):
    def test_legacy_process_insert_uses_database_lifecycle_defaults(self):
        now = timezone.now()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO academic_etl_pipelinerun (
                    country_name, country_code, crawl_mode, seed_provider,
                    crawl_scope, status, is_incremental,
                    total_discovered_institutions, total_crawled_institutions,
                    total_programs_found, stats_json, error_message,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    "Legacy India", "IN", "full", "wikipedia", "unified_fast",
                    "pending", False, 0, 0, 0, "{}", "", now, now,
                ],
            )
            run_id = cursor.lastrowid

        run = PipelineRun.objects.get(pk=run_id)
        self.assertEqual(run.execution_state, {})
        self.assertEqual(run.worker_token, "")
        self.assertEqual(run.retry_count, 0)

    def test_multi_source_fetches_concurrently_and_writes_progress_serially(self):
        from academic_etl.services.multi_source_scraper import enrich_run_from_web_sources

        run = PipelineRun.objects.create(country_name="India", country_code="IN")
        for index in range(2):
            seed = InstitutionSeed.objects.create(
                pipeline_run=run,
                name=f"University {index}",
                country="India",
                country_code="IN",
                status=InstitutionSeed.Status.VALID,
            )
            ExtractedUniversity.objects.create(
                pipeline_run=run,
                seed=seed,
                name=seed.name,
            )

        with patch(
            "academic_etl.services.multi_source_scraper.scrape_university_multi_source",
            return_value={"description": "Verified description"},
        ):
            enriched = enrich_run_from_web_sources(run, concurrency=2)

        run.refresh_from_db()
        self.assertEqual(enriched, 2)
        self.assertEqual(
            run.universities.filter(description="Verified description").count(),
            2,
        )
        self.assertEqual(run.stats_json["web_scrape"]["processed"], 2)
        self.assertTrue(run.stats_json["web_scrape"]["done"])

    def test_host_lock_allows_only_one_pipeline_process(self):
        from academic_etl.services.pipeline_execution import PipelineHostLock

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "pipeline.lock"
            first = PipelineHostLock(path)
            second = PipelineHostLock(path)
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()
            self.assertTrue(second.acquire())
            second.release()

    def test_stale_worker_is_claimed_and_relaunched_once(self):
        run = PipelineRun.objects.create(
            country_name="India",
            country_code="IN",
            status=PipelineRun.Status.CRAWLING,
            worker_token="old-token",
            worker_heartbeat_at=timezone.now() - timedelta(minutes=2),
        )

        with patch("academic_etl.views.launch_unified_worker", return_value=777) as launcher:
            views._recover_stale_pipeline_runs()
            views._recover_stale_pipeline_runs()

        launcher.assert_called_once()
        self.assertEqual(launcher.call_args.args[0], run.pk)
        run.refresh_from_db()
        self.assertEqual(run.status, PipelineRun.Status.QUEUED)
        self.assertNotEqual(run.worker_token, "old-token")

    def test_tokenless_legacy_worker_is_not_recovered(self):
        PipelineRun.objects.create(
            country_name="India",
            country_code="IN",
            status=PipelineRun.Status.CRAWLING,
            worker_token="",
            worker_heartbeat_at=timezone.now() - timedelta(minutes=2),
        )

        with patch("academic_etl.views.launch_unified_worker") as launcher:
            views._recover_stale_pipeline_runs()

        launcher.assert_not_called()

    def test_progress_update_honors_cancellation_request(self):
        from academic_etl.services.pipeline_execution import (
            PipelineCancelled,
            claim_pipeline_run,
            update_stage_progress,
        )

        run = PipelineRun.objects.create(country_name="India", country_code="IN")
        token = claim_pipeline_run(run.pk)
        PipelineRun.objects.filter(pk=run.pk).update(
            status=PipelineRun.Status.CANCELLING,
            cancel_requested_at=timezone.now(),
        )

        with self.assertRaises(PipelineCancelled):
            update_stage_progress(
                run.pk, token, "wikipedia", processed=1, total=10,
            )

    def test_recoverable_error_retries_three_times_then_fails(self):
        from academic_etl.services.pipeline_execution import PipelineHostLock, claim_pipeline_run

        run = PipelineRun.objects.create(
            country_name="India",
            country_code="IN",
            crawl_mode="fast",
            crawl_scope="unified_fast",
        )
        token = claim_pipeline_run(run.pk)
        with TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "pipeline.lock"
            with (
                patch(
                    "academic_etl.views.enrich_run_from_wikipedia",
                    side_effect=OperationalError("database is locked"),
                ) as wikipedia,
                patch("academic_etl.views.time.sleep"),
                patch(
                    "academic_etl.views.PipelineHostLock",
                    side_effect=lambda: PipelineHostLock(lock_path),
                ),
            ):
                views.run_unified_pipeline(run.pk, worker_token=token)

        run.refresh_from_db()
        self.assertEqual(wikipedia.call_count, 4)
        self.assertEqual(run.retry_count, 3)
        self.assertEqual(run.status, PipelineRun.Status.FAILED)
        self.assertEqual(run.execution_state["current_stage"], "wikipedia")
        self.assertEqual(run.worker_token, "")

    def test_fast_run_completes_with_unresolved_staging_coverage(self):
        run = PipelineRun.objects.create(
            country_name="India",
            country_code="IN",
            crawl_mode="fast",
            crawl_scope="unified_fast",
        )
        InstitutionSeed.objects.create(
            pipeline_run=run,
            name="Unresolved University",
            country="India",
            country_code="IN",
            status=InstitutionSeed.Status.VALID,
        )
        self._run_pipeline_without_external_calls(run)

        run.refresh_from_db()
        progress = views._run_progress(run)
        self.assertEqual(run.status, PipelineRun.Status.REVIEW)
        self.assertEqual(progress["phase_label"], "COMPLETE")
        self.assertEqual(progress["progress_pct"], 100)
        self.assertEqual(progress["unresolved_seeds"], 1)
        self.assertIn("1 unresolved", progress["coverage_detail"])

    def test_thorough_run_terminalizes_remaining_valid_seeds(self):
        run = PipelineRun.objects.create(
            country_name="India",
            country_code="IN",
            crawl_mode="thorough",
            crawl_scope="unified_thorough",
        )
        seed = InstitutionSeed.objects.create(
            pipeline_run=run,
            name="No Website University",
            country="India",
            country_code="IN",
            status=InstitutionSeed.Status.VALID,
        )
        self._run_pipeline_without_external_calls(run)

        run.refresh_from_db()
        seed.refresh_from_db()
        progress = views._run_progress(run)
        self.assertEqual(seed.status, InstitutionSeed.Status.SKIPPED)
        self.assertEqual(run.status, PipelineRun.Status.REVIEW)
        self.assertEqual(progress["phase_label"], "COMPLETE")
        self.assertEqual(progress["terminal_seeds"], 1)
        self.assertEqual(progress["coverage_pct"], 100)

    def test_failed_run_resume_action_keeps_checkpoint(self):
        run = PipelineRun.objects.create(
            country_name="India",
            country_code="IN",
            status=PipelineRun.Status.FAILED,
            retry_count=3,
            execution_state={"current_stage": "programs", "completed_stages": ["wikipedia"]},
        )
        detail = self.client.get(reverse("academic_etl:run_detail", args=[run.pk]))
        self.assertContains(detail, "Resume from checkpoint")

        with patch("academic_etl.views.launch_unified_worker", return_value=888) as launcher:
            response = self.client.post(
                reverse("academic_etl:resume_unified_run", args=[run.pk])
            )

        self.assertEqual(response.status_code, 302)
        run.refresh_from_db()
        self.assertEqual(run.status, PipelineRun.Status.QUEUED)
        self.assertEqual(run.retry_count, 0)
        self.assertEqual(run.execution_state["current_stage"], "programs")
        launcher.assert_called_once()

    def _run_pipeline_without_external_calls(self, run):
        from academic_etl.services.pipeline_execution import PipelineHostLock, claim_pipeline_run

        token = claim_pipeline_run(run.pk)
        with TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "pipeline.lock"
            with (
                patch("academic_etl.views.enrich_run_from_wikipedia"),
                patch("academic_etl.views.crawl_run"),
                patch("academic_etl.services.multi_source_scraper.enrich_run_from_web_sources"),
                patch("academic_etl.views._crawl_programs_only"),
                patch("academic_etl.views._test_ai_provider", return_value=False),
                patch("academic_etl.views._post_process_run"),
                patch("academic_etl.views.validate_run"),
                patch(
                    "academic_etl.views.PipelineHostLock",
                    side_effect=lambda: PipelineHostLock(lock_path),
                ),
            ):
                views.run_unified_pipeline(run.pk, worker_token=token)


class DataResetTests(TestCase):
    def test_reset_request_cancels_active_run_and_launches_one_worker(self):
        from academic_etl.services.data_reset import request_data_reset

        run = PipelineRun.objects.create(
            country_name="India",
            country_code="IN",
            status=PipelineRun.Status.CRAWLING,
            worker_token="worker-token",
        )

        with patch(
            "academic_etl.services.data_reset.launch_data_reset_worker",
            return_value=4242,
        ) as launcher:
            job, created = request_data_reset(DataResetJob.Mode.ALL)
            same_job, created_again = request_data_reset(DataResetJob.Mode.ALL)

        run.refresh_from_db()
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(same_job.pk, job.pk)
        self.assertEqual(run.status, PipelineRun.Status.CANCELLING)
        self.assertIsNotNone(run.cancel_requested_at)
        launcher.assert_called_once_with(job.pk)

    def test_reset_worker_deletes_all_data_and_resets_run_sequence(self):
        from academic_etl.services.data_reset import run_data_reset
        from academic_etl.services.pipeline_execution import PipelineHostLock

        run = PipelineRun.objects.create(country_name="India", country_code="IN")
        university = ExtractedUniversity.objects.create(
            pipeline_run=run,
            name="Staged University",
        )
        FieldEvidence.objects.create(
            entity_type="university",
            entity_id=university.pk,
            field_name="name",
            extracted_value=university.name,
        )
        University.objects.create(name="Live University", slug="live-university")
        job = DataResetJob.objects.create(mode=DataResetJob.Mode.ALL)

        with TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "reset.lock"
            with patch(
                "academic_etl.services.data_reset.PipelineHostLock",
                side_effect=lambda: PipelineHostLock(lock_path),
            ):
                run_data_reset(job.pk)

        job.refresh_from_db()
        self.assertEqual(job.status, DataResetJob.Status.COMPLETED)
        self.assertEqual(PipelineRun.objects.count(), 0)
        self.assertEqual(ExtractedUniversity.objects.count(), 0)
        self.assertEqual(FieldEvidence.objects.count(), 0)
        self.assertEqual(University.objects.count(), 0)
        next_run = PipelineRun.objects.create(country_name="Vietnam", country_code="VN")
        self.assertEqual(next_run.pk, 1)


class DegreeLevelTests(TestCase):
    def test_higher_education_levels(self):
        self.assertEqual(classify_degree_level("Bachelor of Science in Physics")[0], DegreeLevel.BACHELOR)
        self.assertEqual(classify_degree_level("M.Sc Chemistry")[0], DegreeLevel.MASTER)
        self.assertEqual(classify_degree_level("PhD in Economics")[0], DegreeLevel.PHD)

    def test_non_degree_is_flagged(self):
        level, is_he, _ = classify_degree_level("Weekend Workshop on Excel")
        self.assertEqual(level, DegreeLevel.NON_DEGREE)
        self.assertFalse(is_he)
        level, is_he, _ = classify_degree_level("IELTS language prep course")
        self.assertFalse(is_he)


class ExtractionTests(TestCase):
    def _page(self, html, page_type="homepage", url="https://example.edu"):
        return {"url": url, "final_url": url, "page_type": page_type, "depth": 0,
                "title": "Example University", "html": html, "html_hash": "x" * 64,
                "soup": BeautifulSoup(html, "html.parser")}

    def test_field_extraction_with_evidence_metadata(self):
        home = self._page(
            "<html><head><title>Example University | Home</title>"
            "<meta name='description' content='A fine public university.'></head>"
            "<body><h1>Example University</h1>"
            "<p>Contact admissions@example.edu or +91 4712232240 for help.</p></body></html>")
        fields = extract_university_fields([home])
        self.assertEqual(fields["name"]["value"], "Example University")
        self.assertEqual(fields["admissions_contact"]["value"], "admissions@example.edu")
        self.assertEqual(fields["name"]["source_url"], "https://example.edu")
        self.assertTrue(fields["name"]["css_selector"])

    def test_field_extraction_skips_year_ranges_before_a_real_phone(self):
        home = self._page(
            "<html><body><p>Academic year +91 2023-2024. "
            "Contact us at +91 99380 47999.</p></body></html>"
        )
        fields = extract_university_fields([home])
        self.assertEqual(fields["admissions_phone"]["value"], "+919938047999")

    def test_program_extraction(self):
        page = self._page(
            "<html><body><ul>"
            "<li><a href='/bsc-physics'>B.Sc Physics</a></li>"
            "<li><a href='/ma-english'>Master of Arts in English</a></li>"
            "<li><a href='/workshop'>Weekend Photography Workshop</a></li>"
            "</ul></body></html>",
            page_type="programs", url="https://example.edu/programs")
        programs = extract_programs([page])
        names = {p["program_name"]: p for p in programs}
        self.assertIn("B.Sc Physics", names)
        self.assertEqual(names["B.Sc Physics"]["degree_level"], DegreeLevel.BACHELOR)
        self.assertIn("Master of Arts in English", names)
        workshop = names.get("Weekend Photography Workshop")
        if workshop:  # workshops may appear but must never count as higher education
            self.assertFalse(workshop["is_higher_education_program"])


class PipelineDbTests(TestCase):
    def _make_run(self):
        run = PipelineRun.objects.create(country_name="India", country_code="IN")
        seed = InstitutionSeed.objects.create(
            pipeline_run=run, name="Example University", country="India", country_code="IN",
            website="https://example.edu", institution_type="university",
            status=InstitutionSeed.Status.VALID, confidence_score=0.9,
        )
        uni = ExtractedUniversity.objects.create(
            pipeline_run=run, seed=seed, name="Example University",
            slug="example-university", website="https://example.edu",
            description="A leading university in India offering undergraduate and postgraduate programs.",
            location="India",
            country="India", country_code="IN", institution_type="university",
            confidence_score=0.9, admissions_contact="admissions@example.edu",
        )
        ExtractedProgram.objects.create(
            pipeline_run=run, extracted_university=uni, program_name="B.Sc Physics",
            degree_level=DegreeLevel.BACHELOR, is_higher_education_program=True,
            confidence_score=0.8, source_url="https://example.edu/programs",
        )
        ExtractedProgram.objects.create(
            pipeline_run=run, extracted_university=uni, program_name="Excel Workshop",
            degree_level=DegreeLevel.NON_DEGREE, is_higher_education_program=False,
            confidence_score=0.8, source_url="https://example.edu/short",
        )
        return run, uni

    def test_validate_and_dry_run_import(self):
        run, uni = self._make_run()
        validate_run(run)
        uni.refresh_from_db()
        self.assertGreater(uni.completeness_score, 0)
        self.assertIn(uni.validation_status, ("valid", "warnings"))

        # Auto-approved (critical fields filled) -> dry run sees it
        job = import_run(run, dry_run=True, approved_only=True)
        self.assertGreaterEqual(job.total_processed, 1)
        self.assertEqual(University.objects.count(), 0)  # dry run doesn't create
        uni.programs.filter(program_name="B.Sc Physics").update(review_status=ReviewStatus.APPROVED)

        job = import_run(run, dry_run=True, approved_only=True)
        self.assertEqual(job.total_created, 2)  # university + program (would_create)
        self.assertEqual(University.objects.count(), 0)  # dry run touched nothing
        self.assertTrue(job.logs.filter(action="would_create").exists())

    def test_live_import_and_upsert_protection(self):
        run, uni = self._make_run()
        validate_run(run)
        uni.review_status = ReviewStatus.APPROVED
        uni.save()
        uni.programs.filter(program_name="B.Sc Physics").update(review_status=ReviewStatus.APPROVED)

        import_run(run, dry_run=False, approved_only=True)
        self.assertEqual(University.objects.count(), 1)
        self.assertEqual(Program.objects.count(), 1)  # workshop excluded
        target = University.objects.get()
        self.assertEqual(target.slug, "example-university")

        # existing good data must not be clobbered by an empty/low-confidence rerun
        target.description = "Hand-written description."
        target.save()
        uni.description = ""
        uni.confidence_score = 0.3
        uni.save()
        import_run(run, dry_run=False, approved_only=True)
        target.refresh_from_db()
        self.assertEqual(target.description, "Hand-written description.")
        self.assertEqual(University.objects.count(), 1)  # upsert, no duplicate

    def test_evidence_recorded_for_csv_seed(self):
        if not SAMPLE_CSV.exists():
            self.skipTest("sample CSV not present")
        from .services.discovery import run_discovery
        run = PipelineRun.objects.create(
            country_name="India", country_code="IN",
            crawl_mode="csv_seed", seed_provider="csv")
        run_discovery(run, limit=3, csv_path=str(SAMPLE_CSV))
        self.assertEqual(run.universities.count(), 3)
        first = run.universities.first()
        self.assertTrue(
            FieldEvidence.objects.filter(entity_type="university", entity_id=first.pk).exists())

    def test_gemini_enrichment_persists_all_catalog_fields(self):
        from .services.pipeline import enrich_seed_from_gemini

        run = PipelineRun.objects.create(country_name="India", country_code="IN")
        seed = InstitutionSeed.objects.create(
            pipeline_run=run,
            name="Example University",
            country="India",
            country_code="IN",
            website="https://example.edu",
            institution_type="university",
            status=InstitutionSeed.Status.VALID,
            confidence_score=0.9,
        )
        result = {
            "sources": ["https://example.edu/contact"],
            "error": "",
            "fields": {
                "name": "Example University",
                "website": "https://example.edu",
                "description": "A university in India.",
                "campus_student_life": "Students use libraries, labs, hostels, and sports facilities.",
                "number_of_students": 12500,
                "financials": "INR 50k-200k ($600-2400)",
                "global_rank": "QS 801-1000",
                "student_to_faculty_ratio": "20:1",
                "international_student_ratio": "5%",
                "admissions_contact": "admissions@example.edu",
                "admissions_phone": "+919938047999",
                "admissions_page_link": "https://example.edu/admissions",
                "contact_person": "Admissions Office",
                "university_campuses": 2,
                "housing_availability": True,
                "student_loan_available": False,
                "immigration_support": True,
            },
        }

        uni = enrich_seed_from_gemini(run, seed, result)

        self.assertEqual(uni.financials, "INR 50k-200k ($600-2400)")
        self.assertEqual(uni.global_rank, "QS 801-1000")
        self.assertEqual(uni.international_student_ratio, "5%")
        self.assertEqual(uni.admissions_contact, "admissions@example.edu")
        self.assertEqual(uni.admissions_phone, "+919938047999")
        self.assertEqual(uni.contact_person, "Admissions Office")
        self.assertEqual(uni.university_campuses, 2)
        self.assertTrue(uni.housing_availability)
        self.assertFalse(uni.student_loan_available)
        self.assertTrue(uni.immigration_support)


class ViewSmokeTests(TestCase):
    def setUp(self):
        self.run = PipelineRun.objects.create(country_name="India", country_code="IN")
        self.uni = ExtractedUniversity.objects.create(
            pipeline_run=self.run, name="Example University", slug="example-university",
            website="https://example.edu", country="India", location="India",
            description="A public university in India.",
            financials="INR 50k-200k ($600-2400)",
            campus_student_life="Students use libraries, laboratories, and sports facilities.",
            number_of_students=12000)
        self.program = ExtractedProgram.objects.create(
            pipeline_run=self.run, extracted_university=self.uni,
            program_name="B.Sc Physics", degree_level=DegreeLevel.BACHELOR)
        self.evidence = FieldEvidence.objects.create(
            entity_type="university", entity_id=self.uni.pk, field_name="name",
            extracted_value="Example University", confidence_score=0.9)

    def test_all_screens_render(self):
        urls = [
            reverse("academic_etl:dashboard"),
            reverse("academic_etl:runs_list"),
            reverse("academic_etl:run_detail", args=[self.run.pk]),
            reverse("academic_etl:seeds_list", args=[self.run.pk]),
            reverse("academic_etl:universities_list", args=[self.run.pk]),
            reverse("academic_etl:programs_list", args=[self.run.pk]),
            reverse("academic_etl:majors_list", args=[self.run.pk]),
            reverse("academic_etl:clean_universities", args=[self.run.pk]),
            reverse("academic_etl:clean_majors", args=[self.run.pk]),
            reverse("academic_etl:add_university", args=[self.run.pk]),
            reverse("academic_etl:add_major", args=[self.uni.pk]),
            reverse("academic_etl:university_detail", args=[self.uni.pk]),
            reverse("academic_etl:program_detail", args=[self.program.pk]),
            reverse("academic_etl:evidence_detail", args=[self.evidence.pk]),
            reverse("academic_etl:import_preview", args=[self.run.pk]),
        ]
        for url in urls:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, url)

    def test_approve_reject_edit_actions(self):
        resp = self.client.post(
            reverse("academic_etl:university_action", args=[self.uni.pk]),
            {"action": "approve"})
        self.assertEqual(resp.status_code, 302)
        self.uni.refresh_from_db()
        self.assertEqual(self.uni.review_status, ReviewStatus.APPROVED)

        self.client.post(
            reverse("academic_etl:university_action", args=[self.uni.pk]),
            {"action": "edit", "name": "Example University (Main Campus)"})
        self.uni.refresh_from_db()
        self.assertEqual(self.uni.name, "Example University (Main Campus)")
        self.assertEqual(self.uni.review_status, ReviewStatus.EDITED)

        self.client.post(
            reverse("academic_etl:program_action", args=[self.program.pk]),
            {"action": "reject"})
        self.program.refresh_from_db()
        self.assertEqual(self.program.review_status, ReviewStatus.REJECTED)

    def test_university_filters_and_clean_view(self):
        other = ExtractedUniversity.objects.create(
            pipeline_run=self.run, name="Other College", slug="other-college",
            website="", country="India", validation_status=ValidationStatus.INVALID,
            review_status=ReviewStatus.REJECTED, confidence_score=0.2)
        self.uni.validation_status = ValidationStatus.VALID
        self.uni.review_status = ReviewStatus.APPROVED
        self.uni.confidence_score = 0.9
        self.uni.save()

        resp = self.client.get(reverse("academic_etl:universities_list", args=[self.run.pk]),
                               {"q": "Example", "validation": "valid", "min_confidence": "0.8"})
        self.assertContains(resp, "Example University")
        self.assertNotContains(resp, "Other College")

        resp = self.client.get(reverse("academic_etl:clean_universities", args=[self.run.pk]))
        self.assertContains(resp, "Example University")
        self.assertNotContains(resp, other.name)

    def test_major_filters_and_clean_view(self):
        self.program.validation_status = ValidationStatus.VALID
        self.program.review_status = ReviewStatus.APPROVED
        self.program.is_higher_education_program = True
        self.program.program_url = "https://example.edu/bsc-physics"
        self.program.confidence_score = 0.85
        self.program.save()
        ExtractedProgram.objects.create(
            pipeline_run=self.run, extracted_university=self.uni,
            program_name="Excel Workshop", degree_level=DegreeLevel.NON_DEGREE,
            validation_status=ValidationStatus.WARNINGS, review_status=ReviewStatus.REJECTED,
            is_higher_education_program=False, confidence_score=0.4)

        resp = self.client.get(reverse("academic_etl:majors_list", args=[self.run.pk]),
                               {"degree_level": "bachelor", "higher_ed": "yes", "has_url": "yes"})
        self.assertContains(resp, "B.Sc Physics")
        self.assertNotContains(resp, "Excel Workshop")

        resp = self.client.get(reverse("academic_etl:clean_majors", args=[self.run.pk]))
        self.assertContains(resp, "B.Sc Physics")
        self.assertNotContains(resp, "Excel Workshop")

    def test_manual_add_university_and_major_create_manual_evidence(self):
        resp = self.client.post(reverse("academic_etl:add_university", args=[self.run.pk]), {
            "name": "Manual University",
            "location": "Hanoi",
            "country": "Vietnam",
            "country_code": "VN",
            "website": "manual.example.edu",
            "institution_type": "university",
            "sponsored": "false",
            "student_loan_available": "true",
        })
        self.assertEqual(resp.status_code, 302)
        manual_uni = ExtractedUniversity.objects.get(name="Manual University")
        self.assertEqual(manual_uni.review_status, ReviewStatus.PENDING)
        self.assertEqual(manual_uni.website, "https://manual.example.edu")
        self.assertTrue(FieldEvidence.objects.filter(
            entity_type="university", entity_id=manual_uni.pk,
            extraction_method="manual", field_name="name").exists())

        resp = self.client.post(reverse("academic_etl:add_major", args=[manual_uni.pk]), {
            "program_name": "Bachelor of Data Engineering",
            "degree_level": DegreeLevel.BACHELOR,
            "program_url": "manual.example.edu/data-engineering",
            "source_url": "manual.example.edu/catalog",
            "is_higher_education_program": "yes",
        })
        self.assertEqual(resp.status_code, 302)
        major = ExtractedProgram.objects.get(program_name="Bachelor of Data Engineering")
        self.assertEqual(major.extracted_university, manual_uni)
        self.assertTrue(major.is_higher_education_program)
        self.assertTrue(FieldEvidence.objects.filter(
            entity_type="program", entity_id=major.pk,
            extraction_method="manual", field_name="program_name").exists())

    def test_start_unified_run_from_ui_uses_pipeline_services(self):
        def fake_discovery(run, limit=0, csv_path=""):
            InstitutionSeed.objects.create(
                pipeline_run=run, name="UI Seed University", country=run.country_name,
                country_code=run.country_code, website="https://ui.example.edu",
                institution_type="university", status=InstitutionSeed.Status.VALID,
            )
            return []

        with (
            patch("academic_etl.views.run_discovery", side_effect=fake_discovery) as discovery,
            patch("academic_etl.views.launch_unified_worker", return_value=4242) as launcher,
        ):
            resp = self.client.post(reverse("academic_etl:start_unified_run"), {
                "country": "India",
                "discover_limit": "10",
                "crawl_limit": "2",
                "max_pages": "3",
            })

        self.assertEqual(resp.status_code, 302)
        run = PipelineRun.objects.exclude(pk=self.run.pk).get()
        self.assertEqual(run.country_name, "India")
        self.assertEqual(run.seed_provider, "wikipedia")
        discovery.assert_called_once()
        launcher.assert_called_once()
        launch_args = launcher.call_args.args
        self.assertEqual(launch_args[0], run.pk)
        self.assertTrue(launch_args[1])

    def test_start_run_is_blocked_while_reset_is_active(self):
        DataResetJob.objects.create(mode=DataResetJob.Mode.ALL)

        with patch("academic_etl.views.run_discovery") as discovery:
            response = self.client.post(
                reverse("academic_etl:start_unified_run"),
                {"country": "India"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(PipelineRun.objects.count(), 1)
        discovery.assert_not_called()

    def test_progress_endpoint_reports_current_stage(self):
        self.run.status = PipelineRun.Status.CRAWLING
        self.run.worker_token = "worker-token"
        self.run.worker_heartbeat_at = timezone.now()
        self.run.execution_state = {
            "version": 1,
            "current_stage": "programs",
            "completed_stages": ["wikipedia", "web_sources"],
            "stage_progress": {
                "processed": 20,
                "total": 40,
                "current_item": "Example University",
                "current_url": "https://example.edu/programs",
                "programs": 27,
                "fanar_calls": 8,
                "gemini_calls": 2,
                "verified_fields": 6,
                "errors": 1,
            },
        }
        self.run.stats_json = {"current_step": "Step 3/6: Crawling programs pages"}
        self.run.save(update_fields=[
            "status", "worker_token", "worker_heartbeat_at", "execution_state", "stats_json",
        ])

        response = self.client.get(
            reverse("academic_etl:run_progress_json", args=[self.run.pk])
        )
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["stage"], "programs")
        self.assertEqual(payload["stage_number"], 3)
        self.assertEqual(payload["processed"], 20)
        self.assertEqual(payload["total"], 40)
        self.assertEqual(payload["current_item"], "Example University")
        self.assertEqual(payload["progress_pct"], 42)
        self.assertEqual(payload["fanar_calls"], 8)
        self.assertEqual(payload["gemini_calls"], 2)
        self.assertEqual(payload["verified_fields"], 6)
        self.assertEqual(payload["field_errors"], 1)
        self.assertEqual(payload["current_step"], "Step 3/6: Crawling programs pages")

    def test_run_progress_uses_program_crawl_heartbeat(self):
        self.run.status = PipelineRun.Status.CRAWLING
        self.run.stats_json = {
            "programs_crawl": {
                "processed": 10,
                "total": 40,
                "created": 7,
                "programs": 27,
                "errors": 1,
                "done": False,
            }
        }
        self.run.save(update_fields=["status", "stats_json"])

        progress = views._run_progress(self.run)

        self.assertTrue(progress["programs_crawl_running"])
        self.assertEqual(progress["phase_label"], "ĐANG LẤY MAJOR")
        self.assertEqual(progress["progress_pct"], 25)
        self.assertEqual(progress["programs_crawl"]["programs"], 27)

    def test_run_progress_uses_wikipedia_heartbeat(self):
        self.run.status = PipelineRun.Status.CRAWLING
        self.run.stats_json = {
            "current_step": "Step 1/6: Wikipedia enrich",
            "wikipedia_enrich": {
                "attempted": 25,
                "staged": 21,
                "total": 50,
                "done": False,
            },
        }
        self.run.save(update_fields=["status", "stats_json"])

        progress = views._run_progress(self.run)

        self.assertTrue(progress["wikipedia_running"])
        self.assertEqual(progress["phase_label"], "WIKIPEDIA ENRICH")
        self.assertEqual(progress["progress_pct"], 50)

    def test_run_progress_marks_completed_pipeline_as_complete(self):
        self.run.status = PipelineRun.Status.REVIEW
        self.run.stats_json = {"current_step": "Complete"}
        self.run.save(update_fields=["status", "stats_json"])

        progress = views._run_progress(self.run)

        self.assertEqual(progress["phase_label"], "COMPLETE")
        self.assertEqual(progress["tone"], "ok")
        self.assertEqual(progress["progress_pct"], 100)

    @patch("academic_etl.services.wikipedia_extract.extract_programs_from_wikipedia")
    def test_programs_crawl_persists_results_and_heartbeat(self, extract_wikipedia):
        seed = InstitutionSeed.objects.create(
            pipeline_run=self.run,
            name=self.uni.name,
            country="India",
            country_code="IN",
            wikipedia_url="https://en.wikipedia.org/wiki/Example_University",
        )
        self.uni.seed = seed
        self.uni.website = ""
        self.uni.save(update_fields=["seed", "website"])
        extract_wikipedia.return_value = [
            {
                "program_name": "Bachelor of Computer Engineering",
                "faculty_or_school": "Engineering",
                "program_url": "https://example.edu/computer-engineering",
            }
        ]

        views._crawl_programs_only(self.run)

        self.assertTrue(self.run.programs.filter(
            program_name="Bachelor of Computer Engineering",
            degree_level=DegreeLevel.BACHELOR,
        ).exists())
        self.run.refresh_from_db()
        self.assertEqual(self.run.total_programs_found, 2)
        self.assertEqual(self.run.stats_json["programs_crawl"]["processed"], 1)
        self.assertTrue(self.run.stats_json["programs_crawl"]["done"])

    def test_run_detail_action_buttons_call_services(self):
        with patch("academic_etl.views.crawl_run", return_value={"attempted": 0, "crawled": 0, "failed": 0}) as crawler:
            resp = self.client.post(reverse("academic_etl:run_crawl_action", args=[self.run.pk]),
                                    {"crawl_limit": "2", "max_pages": "3"})
        self.assertEqual(resp.status_code, 302)
        crawler.assert_called_once()

        with patch("academic_etl.views.validate_run", return_value={"universities": {}, "programs": {}}) as validator:
            resp = self.client.post(reverse("academic_etl:run_validate_action", args=[self.run.pk]))
        self.assertEqual(resp.status_code, 302)
        validator.assert_called_once_with(self.run)

        def fake_import(run, dry_run=True, approved_only=True, threshold=0.75):
            return ImportJob.objects.create(
                pipeline_run=run, dry_run=dry_run, approved_only=approved_only,
                confidence_threshold=threshold, status=ImportJob.Status.COMPLETED,
            )

        with patch("academic_etl.views.import_run", side_effect=fake_import) as importer:
            resp = self.client.post(reverse("academic_etl:run_import_action", args=[self.run.pk]),
                                    {"dry_run": "1", "approved_only": "1"})
        self.assertEqual(resp.status_code, 302)
        importer.assert_called_once()


class DynamicFallbackTests(TestCase):
    """Scrapling DynamicFetcher fallback for JS-rendered sites (mocked, offline)."""

    # A SPA shell: almost no visible text, content injected by JS at runtime.
    SPA_SHELL = "<html><head><title>App</title></head><body><div id='root'></div>" \
                "<script>renderApp()</script></body></html>"
    # What the headless browser would see after JS runs.
    RENDERED = "<html><head><title>Tech University</title></head><body>" \
               "<h1>Tech University</h1><p>" + ("Programs and admissions. " * 60) + \
               "</p></body></html>"

    def _crawler(self, tmp_path, **kw):
        from academic_etl.services.crawler import SiteCrawler
        c = SiteCrawler(cache_dir=tmp_path, rate_limit=0, **kw)
        c._robots_allows = lambda url: True  # skip network robots fetch
        return c

    def _static_response(self, html):
        class R:
            status_code = 200
            url = "https://tech.edu"
            headers = {"Content-Type": "text/html"}
            text = html
        return R()

    def test_thin_detection(self):
        from pathlib import Path
        import tempfile
        c = self._crawler(Path(tempfile.mkdtemp()), dynamic_min_text_chars=500)
        self.assertTrue(c._looks_thin(self.SPA_SHELL))
        self.assertFalse(c._looks_thin(self.RENDERED))

    def test_fallback_used_when_static_is_thin(self):
        from pathlib import Path
        import tempfile
        from unittest import mock

        c = self._crawler(Path(tempfile.mkdtemp()), use_dynamic_fallback=True)
        with mock.patch.object(c.session, "get",
                               return_value=self._static_response(self.SPA_SHELL)), \
             mock.patch("academic_etl.services.crawler.dynamic_fetch",
                        return_value={"html": self.RENDERED, "final_url": "https://tech.edu",
                                      "status_code": 200, "error": ""}) as dyn:
            result = c.fetch("https://tech.edu")
        dyn.assert_called_once()
        self.assertEqual(result["fetch_method"], "scrapling_dynamic")
        self.assertIn("Tech University", result["html"])

    def test_fallback_skipped_when_static_is_rich(self):
        from pathlib import Path
        import tempfile
        from unittest import mock

        c = self._crawler(Path(tempfile.mkdtemp()), use_dynamic_fallback=True)
        with mock.patch.object(c.session, "get",
                               return_value=self._static_response(self.RENDERED)), \
             mock.patch("academic_etl.services.crawler.dynamic_fetch") as dyn:
            result = c.fetch("https://tech.edu")
        dyn.assert_not_called()
        self.assertEqual(result["fetch_method"], "requests")

    def test_fallback_degrades_when_scrapling_unavailable(self):
        from pathlib import Path
        import tempfile
        from unittest import mock

        c = self._crawler(Path(tempfile.mkdtemp()), use_dynamic_fallback=True)
        with mock.patch.object(c.session, "get",
                               return_value=self._static_response(self.SPA_SHELL)), \
             mock.patch("academic_etl.services.crawler.dynamic_fetch",
                        return_value={"html": "", "error": "scrapling unavailable"}):
            result = c.fetch("https://tech.edu")
        # Falls back to the (thin) static HTML rather than raising.
        self.assertEqual(result["fetch_method"], "requests")
        self.assertIn("root", result["html"])


def _wd_binding(qid, label, website="", country="Vietnam", code="VN",
                place="", article=""):
    """Build one SPARQL JSON result binding."""
    b = {
        "item": {"value": f"http://www.wikidata.org/entity/{qid}"},
        "itemLabel": {"value": label},
        "countryLabel": {"value": country},
        "code": {"value": code},
    }
    if website:
        b["website"] = {"value": website}
    if place:
        b["placeLabel"] = {"value": place}
    if article:
        b["article"] = {"value": article}
    return b


# Mocked SPARQL response: VNU (full metadata, appears twice), HUST (only a
# wikipedia.org "website" which must be rejected), and an unlabeled entity.
WIKIDATA_BINDINGS = [
    _wd_binding("Q1147576", "Vietnam National University, Hanoi",
                website="https://vnu.edu.vn/", place="Hanoi",
                article="https://en.wikipedia.org/wiki/Vietnam_National_University,_Hanoi"),
    _wd_binding("Q1147576", "Vietnam National University, Hanoi",
                website="https://vnu.edu.vn/", place="Cau Giay",
                article="https://en.wikipedia.org/wiki/Vietnam_National_University,_Hanoi"),
    _wd_binding("Q1334434", "Hanoi University of Science and Technology",
                website="https://en.wikipedia.org/wiki/HUST", place="Hanoi",
                article="https://en.wikipedia.org/wiki/Hanoi_University_of_Science_and_Technology"),
    _wd_binding("Q99999999", "Q99999999"),  # unlabeled -> skipped
]


class WikidataProviderTests(TestCase):
    """Parsing, website-filtering and dedup of the Wikidata provider (mocked)."""

    def _discover(self, bindings):
        from unittest import mock
        from academic_etl.services.wikidata import WikidataSeedProvider
        with mock.patch("academic_etl.services.wikidata.query_wikidata",
                        return_value=bindings) as q:
            seeds = WikidataSeedProvider().discover("Vietnam", "VN", limit=200)
        return seeds, q

    def test_bindings_parsed_and_unlabeled_skipped(self):
        seeds, q = self._discover(WIKIDATA_BINDINGS)
        q.assert_called_once()
        # 2 institutions (duplicate VNU row collapsed, unlabeled entity dropped)
        self.assertEqual(len(seeds), 2)
        by_qid = {s["wikidata_qid"]: s for s in seeds}
        vnu = by_qid["Q1147576"]
        self.assertEqual(vnu["name"], "Vietnam National University, Hanoi")
        self.assertEqual(vnu["website"], "https://vnu.edu.vn")
        self.assertEqual(vnu["country_code"], "VN")
        self.assertEqual(vnu["region"], "Hanoi")
        self.assertEqual(vnu["source_name"], "wikidata")
        self.assertIn("wikipedia.org", vnu["wikipedia_url"])
        self.assertEqual(vnu["confidence"], 1.0)  # name+website+wiki+place

    def test_wikipedia_and_wikidata_are_not_used_as_website(self):
        seeds, _ = self._discover(WIKIDATA_BINDINGS)
        hust = {s["wikidata_qid"]: s for s in seeds}["Q1334434"]
        self.assertEqual(hust["website"], "")  # the en.wikipedia.org link rejected
        self.assertIn("wikipedia.org", hust["wikipedia_url"])  # but kept as wikipedia_url
        self.assertEqual(hust["confidence"], 0.8)  # no official website

    def test_dedup_by_domain(self):
        from academic_etl.services.wikidata import WikidataSeedProvider
        seeds = [
            {"name": "Alpha University", "wikidata_qid": "Q1",
             "website": "https://alpha.edu", "country_code": "VN", "region": "Hanoi"},
            {"name": "Alpha University (campus)", "wikidata_qid": "Q2",
             "website": "https://www.alpha.edu/", "country_code": "VN", "region": "Hue"},
        ]
        out = WikidataSeedProvider._dedup(seeds)
        self.assertEqual(len(out), 1)  # same official domain -> one seed

    def test_dedup_by_normalized_name_country_region(self):
        from academic_etl.services.wikidata import WikidataSeedProvider
        seeds = [
            {"name": "Beta College", "wikidata_qid": "", "website": "",
             "country_code": "VN", "region": "Hanoi"},
            {"name": "beta  college", "wikidata_qid": "", "website": "",
             "country_code": "VN", "region": "Hanoi"},
        ]
        out = WikidataSeedProvider._dedup(seeds)
        self.assertEqual(len(out), 1)


class WikidataDiscoveryRunTests(TestCase):
    """End-to-end run_discovery with the wikidata provider (mocked, offline)."""

    def _run(self):
        return PipelineRun.objects.create(
            country_name="Vietnam", country_code="VN",
            crawl_mode="discover_only", seed_provider="wikidata",
        )

    def test_run_discovery_persists_kb_provenance_and_dedups(self):
        from unittest import mock
        from academic_etl.services.discovery import run_discovery

        run = self._run()
        with mock.patch("academic_etl.services.wikidata.query_wikidata",
                        return_value=WIKIDATA_BINDINGS):
            created = run_discovery(run, limit=200)

        self.assertEqual(len(created), 2)
        vnu = InstitutionSeed.objects.get(pipeline_run=run, wikidata_qid="Q1147576")
        self.assertEqual(vnu.source_name, "wikidata")
        self.assertEqual(vnu.website, "https://vnu.edu.vn")
        self.assertIn("wikipedia.org", vnu.wikipedia_url)
        self.assertEqual(vnu.country_code, "VN")
        self.assertEqual(vnu.region, "Hanoi")
        self.assertTrue(vnu.is_higher_education)

        # Re-running discovery on the same run must not duplicate by QID.
        with mock.patch("academic_etl.services.wikidata.query_wikidata",
                        return_value=WIKIDATA_BINDINGS):
            again = run_discovery(run, limit=200)
        self.assertEqual(len(again), 0)
        self.assertEqual(InstitutionSeed.objects.filter(pipeline_run=run).count(), 2)


def _crawl_page(html, page_type, url, final_url=None):
    """Build a SiteCrawler.crawl_site-style page dict with parsed soup."""
    return {
        "url": url, "final_url": final_url or url, "status_code": 200,
        "html": html, "error": "", "html_hash": "h" * 64, "cache_path": "",
        "page_type": page_type, "depth": 0 if page_type == "homepage" else 1,
        "title": "", "fetch_method": "requests",
        "soup": BeautifulSoup(html, "html.parser"),
    }


def _fetched(url, html, final_url=None):
    """A SiteCrawler.fetch-style result dict."""
    return {
        "url": url, "final_url": final_url or url,
        "status_code": 200 if html else None, "html": html, "error": "",
        "html_hash": ("h" * 64) if html else "", "cache_path": "",
        "fetch_method": "requests", "title": "",
    }


class FakeCrawler:
    """Stand-in for SiteCrawler that returns canned pages (no network).

    `crawl_site` returns the site pages; `fetch` serves program detail pages from
    `detail_html` (keyed by full URL or path suffix), else an empty result so
    detail enrichment degrades gracefully."""

    def __init__(self, pages, detail_html=None):
        self._pages = pages
        self._detail_html = detail_html or {}

    def crawl_site(self, start_url):
        return self._pages

    def fetch(self, url, retries=2):
        html = self._detail_html.get(url, "")
        if not html:
            for key, value in self._detail_html.items():
                if url.endswith(key):
                    html = value
                    break
        return _fetched(url, html)


class KbCrawlReconcileTests(TestCase):
    """Crawl Wikidata-seeded official sites, extract fields with evidence, and
    reconcile KB source values vs official-website values (mocked HTML)."""

    HOMEPAGE = (
        "<html><head><title>VNU Hanoi</title>"
        "<meta name='description' content='A leading public university in Hanoi.'></head>"
        "<body><h1>Vietnam National University, Hanoi</h1></body></html>"
    )
    INTERNATIONAL = (
        "<html><body><p>We host 12% international students from over 50 countries "
        "across our campuses.</p></body></html>"
    )
    TUITION = (
        "<html><body><p>Tuition fees are $1,200 per year for undergraduate "
        "programs.</p></body></html>"
    )
    PROGRAMS = (
        "<html><body><ul><li><a href='/bsc-cs'>B.Sc Computer Science</a></li>"
        "<li><a href='/ma-econ'>Master of Arts in Economics</a></li></ul></body></html>"
    )

    def _seed(self, run, name="Vietnam National University, Hanoi",
              website="https://vnu.edu.vn"):
        return InstitutionSeed.objects.create(
            pipeline_run=run, name=name, country="Vietnam", country_code="VN",
            city="Hanoi", website=website, institution_type="university",
            status=InstitutionSeed.Status.VALID, confidence_score=0.9,
            source_name="wikidata", wikidata_qid="Q1147576",
            wikipedia_url="https://en.wikipedia.org/wiki/Vietnam_National_University,_Hanoi",
            source_url="https://www.wikidata.org/wiki/Q1147576",
        )

    def _pages(self, home_final="https://vnu.edu.vn", home_h1=None):
        home = self.HOMEPAGE if home_h1 is None else self.HOMEPAGE.replace(
            "Vietnam National University, Hanoi", home_h1)
        return [
            _crawl_page(home, "homepage", "https://vnu.edu.vn", home_final),
            _crawl_page(self.INTERNATIONAL, "international", "https://vnu.edu.vn/international"),
            _crawl_page(self.TUITION, "tuition", "https://vnu.edu.vn/tuition"),
            _crawl_page(self.PROGRAMS, "programs", "https://vnu.edu.vn/programs"),
        ]

    def _run_crawl(self, pages, **seed_kwargs):
        from academic_etl.services.pipeline import crawl_seed
        run = PipelineRun.objects.create(country_name="Vietnam", country_code="VN",
                                         seed_provider="wikidata")
        seed = self._seed(run, **seed_kwargs)
        uni = crawl_seed(run, seed, FakeCrawler(pages))
        return run, seed, uni

    def test_extracts_fields_with_evidence(self):
        run, seed, uni = self._run_crawl(self._pages())
        self.assertIsNotNone(uni)
        # international student info + tuition text extracted and filled
        self.assertEqual(uni.international_student_ratio, "12%")
        self.assertIn("Tuition", uni.financials)
        self.assertTrue(uni.description)
        # program/major links extracted
        self.assertTrue(uni.programs.filter(program_name="B.Sc Computer Science").exists())
        # every extracted field has evidence
        self.assertTrue(FieldEvidence.objects.filter(
            entity_type="university", entity_id=uni.pk,
            field_name="international_student_ratio").exists())

    def test_kb_source_evidence_ranks_below_official(self):
        run, seed, uni = self._run_crawl(self._pages())
        # KB-asserted name evidence exists (low confidence)
        kb_name = FieldEvidence.objects.get(entity_type="university", entity_id=uni.pk,
                                            field_name="name", extraction_method="wikidata")
        official_name = FieldEvidence.objects.filter(
            entity_type="university", entity_id=uni.pk, field_name="name",
            extraction_method="rule").order_by("-confidence_score").first()
        self.assertIsNotNone(official_name)
        self.assertLess(kb_name.confidence_score, official_name.confidence_score)
        # official website evidence outranks the KB-asserted website
        kb_site = FieldEvidence.objects.get(entity_type="university", entity_id=uni.pk,
                                            field_name="website", extraction_method="wikidata")
        official_site = FieldEvidence.objects.get(
            entity_type="university", entity_id=uni.pk, field_name="website",
            extractor_name="homepage_resolve")
        self.assertGreater(official_site.confidence_score, kb_site.confidence_score)

    def test_agreement_has_no_conflict(self):
        run, seed, uni = self._run_crawl(self._pages())
        self.assertNotIn("source_conflicts", uni.normalized_json)
        validate_run(run)
        uni.refresh_from_db()
        self.assertNotEqual(uni.validation_status, ValidationStatus.NEEDS_REVIEW)

    def test_name_conflict_forces_needs_review(self):
        # Official homepage advertises a different institution name.
        run, seed, uni = self._run_crawl(self._pages(home_h1="Hanoi Medical Academy"))
        self.assertIn("name", uni.normalized_json.get("source_conflicts", []))
        validate_run(run)
        uni.refresh_from_db()
        self.assertEqual(uni.validation_status, ValidationStatus.NEEDS_REVIEW)
        self.assertTrue(ValidationIssue.objects.filter(
            entity_type="university", entity_id=uni.pk,
            code="source_conflict", field_name="name").exists())

    def test_website_domain_conflict_detected(self):
        # Homepage redirects to a different domain than the KB-asserted website.
        run, seed, uni = self._run_crawl(self._pages(home_final="https://different-domain.org"))
        self.assertIn("website", uni.normalized_json.get("source_conflicts", []))

    def test_crawl_persists_the_resolved_website_scheme(self):
        run, seed, uni = self._run_crawl(self._pages(home_final="http://vnu.edu.vn"))
        seed.refresh_from_db()
        self.assertEqual(uni.website, "http://vnu.edu.vn")
        self.assertEqual(seed.website, "http://vnu.edu.vn")


# A rich program detail page with labelled metadata.
PROGRAM_DETAIL_HTML = (
    "<html><head><title>B.Sc Computer Science | Tech University</title>"
    "<meta name='description' content='A four-year undergraduate degree in "
    "computer science covering algorithms, AI and software engineering.'></head>"
    "<body><h1>Bachelor of Science in Computer Science</h1>"
    "<dl>"
    "<dt>Duration</dt><dd>4 years</dd>"
    "<dt>Study mode</dt><dd>Full-time</dd>"
    "<dt>Language of instruction</dt><dd>English</dd>"
    "<dt>Tuition fees</dt><dd>VND 30,000,000 per year</dd>"
    "<dt>Intake</dt><dd>September 2025</dd>"
    "<dt>Application deadline</dt><dd>30 June 2025</dd>"
    "<dt>Faculty</dt><dd>Faculty of Information Technology</dd>"
    "<dt>Field of study</dt><dd>Computer Science</dd>"
    "<dt>Accreditation</dt><dd>Accredited by the Ministry of Education</dd>"
    "</dl>"
    "<h3>Entry requirements</h3>"
    "<p>Applicants must hold a high school diploma with strong results in mathematics.</p>"
    "<h3>Career outcomes</h3>"
    "<p>Graduates work as software engineers, data scientists and systems analysts.</p>"
    "</body></html>"
)


class ProgramDetailExtractorTests(TestCase):
    """services/program_detail.extract_program_detail on mocked HTML."""

    def _detail(self, html=PROGRAM_DETAIL_HTML):
        from academic_etl.services.program_detail import extract_program_detail
        page = {"url": "https://tech.edu/bsc-cs", "final_url": "https://tech.edu/bsc-cs",
                "page_type": "programs", "title": "B.Sc CS", "html_hash": "x" * 64,
                "soup": BeautifulSoup(html, "html.parser")}
        return {k: v["value"] for k, v in extract_program_detail(page).items()}

    def test_all_fields_extracted(self):
        d = self._detail()
        self.assertEqual(d["program_name"], "Bachelor of Science in Computer Science")
        self.assertIn("four-year", d["description"])
        self.assertEqual(d["duration"], "4 years")
        self.assertEqual(d["study_mode"], "Full-time")
        self.assertEqual(d["language"], "English")
        self.assertIn("30,000,000", d["tuition_fee"])
        self.assertEqual(d["currency"], "VND")
        self.assertEqual(d["intake"], "September 2025")
        self.assertEqual(d["application_deadline"], "30 June 2025")
        self.assertIn("Information Technology", d["faculty_or_school"])
        self.assertEqual(d["field_of_study"], "Computer Science")
        self.assertIn("Ministry of Education", d["accreditation"])
        self.assertIn("high school diploma", d["admission_requirements"])
        self.assertIn("software engineers", d["career_outcomes"])

    def test_vietnamese_labels_extracted(self):
        html = (
            "<html><head><title>Cử nhân Khoa học Máy tính</title></head><body>"
            "<h1>Cử nhân Khoa học Máy tính</h1><dl>"
            "<dt>Thời gian đào tạo</dt><dd>4 năm</dd>"
            "<dt>Hình thức đào tạo</dt><dd>Chính quy</dd>"
            "<dt>Ngôn ngữ giảng dạy</dt><dd>Tiếng Anh</dd>"
            "<dt>Học phí</dt><dd>30.000.000 ₫/năm</dd>"
            "<dt>Ngành</dt><dd>Khoa học Máy tính</dd></dl>"
            "<h3>Điều kiện xét tuyển</h3><p>Thí sinh tốt nghiệp THPT với điểm Toán cao.</p>"
            "</body></html>"
        )
        d = self._detail(html)
        self.assertEqual(d["duration"], "4 năm")
        self.assertEqual(d["study_mode"], "Chính quy")
        self.assertEqual(d["language"], "Tiếng Anh")
        self.assertIn("30.000.000", d["tuition_fee"])
        self.assertEqual(d["currency"], "VND")
        self.assertEqual(d["field_of_study"], "Khoa học Máy tính")
        self.assertIn("THPT", d["admission_requirements"])

    def test_vietnamese_degree_levels(self):
        from academic_etl.services.extraction import classify_degree_level
        self.assertEqual(classify_degree_level("Cử nhân Khoa học Máy tính")[0], DegreeLevel.BACHELOR)
        self.assertEqual(classify_degree_level("Thạc sĩ Quản trị Kinh doanh")[0], DegreeLevel.MASTER)
        self.assertEqual(classify_degree_level("Tiến sĩ Vật lý")[0], DegreeLevel.PHD)
        level, is_he, _ = classify_degree_level("Khóa học ngắn hạn về Python")
        self.assertEqual(level, DegreeLevel.NON_DEGREE)
        self.assertFalse(is_he)

    def test_announcement_titles_are_not_programs(self):
        # News/announcement titles that contain degree keywords are dropped.
        html = ("<html><body><ul>"
                "<li><a href='/n1'>THÔNG BÁO TUYỂN SINH THẠC SĨ 2026</a></li>"
                "<li><a href='/n2'>Lễ bảo vệ luận án Tiến sĩ cấp trường</a></li>"
                "<li><a href='/p1'>Thạc sĩ Quản trị Kinh doanh</a></li>"
                "</ul></body></html>")
        page = {"url": "https://x.edu.vn/programs", "final_url": "https://x.edu.vn/programs",
                "page_type": "programs", "title": "", "html_hash": "z" * 64,
                "soup": BeautifulSoup(html, "html.parser")}
        names = {p["program_name"] for p in extract_programs([page])}
        self.assertIn("Thạc sĩ Quản trị Kinh doanh", names)
        self.assertNotIn("THÔNG BÁO TUYỂN SINH THẠC SĨ 2026", names)
        self.assertFalse(any("Lễ bảo vệ" in n for n in names))


class ProgramDetailPipelineTests(TestCase):
    """End-to-end: crawl seed -> follow program links -> enrich + evidence."""

    HOMEPAGE = "<html><head><title>Tech University</title></head><body>" \
               "<h1>Tech University</h1></body></html>"
    PROGRAMS = ("<html><body><ul>"
                "<li><a href='/bsc-cs'>Bachelor of Science in Computer Science</a></li>"
                "</ul></body></html>")

    def _run_crawl(self):
        from academic_etl.services.pipeline import crawl_seed
        run = PipelineRun.objects.create(country_name="Vietnam", country_code="VN",
                                         seed_provider="wikidata")
        seed = InstitutionSeed.objects.create(
            pipeline_run=run, name="Tech University", country="Vietnam", country_code="VN",
            website="https://tech.edu", institution_type="university",
            status=InstitutionSeed.Status.VALID, confidence_score=0.9, source_name="wikidata")
        pages = [
            _crawl_page(self.HOMEPAGE, "homepage", "https://tech.edu"),
            _crawl_page(self.PROGRAMS, "programs", "https://tech.edu/programs"),
        ]
        crawler = FakeCrawler(pages, detail_html={"/bsc-cs": PROGRAM_DETAIL_HTML})
        uni = crawl_seed(run, seed, crawler)
        return run, uni

    def test_program_detail_fields_and_evidence(self):
        run, uni = self._run_crawl()
        program = uni.programs.get(program_name="Bachelor of Science in Computer Science")
        # detail fields filled
        self.assertEqual(program.duration, "4 years")
        self.assertEqual(program.currency, "VND")
        self.assertIn("30,000,000", program.tuition_fee)
        self.assertEqual(program.language, "English")
        self.assertTrue(program.source_url)
        self.assertTrue(program.raw_json.get("detail_crawled"))
        # FieldEvidence saved for several program detail fields
        ev_fields = set(FieldEvidence.objects.filter(
            entity_type="program", entity_id=program.pk).values_list("field_name", flat=True))
        for f in ("duration", "tuition_fee", "currency", "intake", "admission_requirements"):
            self.assertIn(f, ev_fields)

    def test_non_degree_detail_forces_needs_review(self):
        # An UNKNOWN-level program whose detail reveals a non-degree offering.
        from academic_etl.services.pipeline import _apply_program_detail
        from academic_etl.services.program_detail import extract_program_detail
        run, uni = self._run_crawl()
        program = ExtractedProgram.objects.create(
            pipeline_run=run, extracted_university=uni, program_name="Data Analytics",
            degree_level=DegreeLevel.UNKNOWN)
        html = ("<html><body><h1>Data Analytics</h1>"
                "<p>This is a two-day weekend workshop on data analytics, not a degree.</p>"
                "</body></html>")
        page = {"url": "https://tech.edu/da", "final_url": "https://tech.edu/da",
                "page_type": "programs", "title": "", "html_hash": "y" * 64,
                "soup": BeautifulSoup(html, "html.parser")}
        _apply_program_detail(program, extract_program_detail(page), page, timezone.now())
        program.refresh_from_db()
        self.assertEqual(program.degree_level, DegreeLevel.NON_DEGREE)
        self.assertFalse(program.is_higher_education_program)
        self.assertEqual(program.validation_status, ValidationStatus.NEEDS_REVIEW)


class ProgramValidationTests(TestCase):
    def test_missing_provenance_warns(self):
        run = PipelineRun.objects.create(country_name="Vietnam", country_code="VN")
        uni = ExtractedUniversity.objects.create(pipeline_run=run, name="Tech University")
        ExtractedProgram.objects.create(
            pipeline_run=run, extracted_university=uni, program_name="B.Sc Physics",
            degree_level=DegreeLevel.BACHELOR, is_higher_education_program=True,
            program_url="", source_url="")
        validate_run(run)
        self.assertTrue(ValidationIssue.objects.filter(
            entity_type="program", code="missing_provenance").exists())


class CsvExportTests(TestCase):
    def _make(self):
        run = PipelineRun.objects.create(country_name="Vietnam", country_code="VN")
        uni = ExtractedUniversity.objects.create(
            pipeline_run=run, name="Tech University", slug="tech-university",
            website="https://tech.edu", sponsored=True, number_of_students=12000,
            review_status=ReviewStatus.APPROVED, validation_status=ValidationStatus.VALID)
        program = ExtractedProgram.objects.create(
            pipeline_run=run, extracted_university=uni, program_name="B.Sc CS",
            degree_level=DegreeLevel.BACHELOR, duration="4 years", currency="VND",
            tuition_fee="30,000,000", program_url="https://tech.edu/cs",
            is_higher_education_program=True,
            review_status=ReviewStatus.APPROVED, validation_status=ValidationStatus.VALID)
        return run, uni, program

    def test_university_csv_matches_sample_shape(self):
        from academic_etl.services.exporter import university_rows
        run, uni, _ = self._make()
        header, rows = university_rows(run.universities.all())
        # leading unnamed index col + id, then the sample columns
        self.assertEqual(header[:4], ["", "id", "name", "location"])
        self.assertIn("university_campuses", header)
        self.assertEqual(len(rows), 1)
        record = dict(zip(header, rows[0]))
        self.assertEqual(record["name"], "Tech University")
        self.assertEqual(record["sponsored"], "0")

    def test_clean_university_export_requires_complete_core_fields(self):
        run, uni, _ = self._make()

        incomplete = self.client.get(reverse("academic_etl:export_universities_csv", args=[run.pk]))
        self.assertNotContains(incomplete, "Tech University")

        uni.location = "704"
        uni.description = "A public university in Vietnam."
        uni.financials = "VND 30m ($1200)"
        uni.campus_student_life = (
            "The campus has academic facilities, student services, and sports spaces."
        )
        uni.save(update_fields=["location", "description", "financials", "campus_student_life"])

        complete = self.client.get(reverse("academic_etl:export_universities_csv", args=[run.pk]))
        self.assertContains(complete, "Tech University")

        uni.financials = "Tuition is VND 30,000,000 per year"
        uni.save(update_fields=["financials"])

        invalid_financials = self.client.get(
            reverse("academic_etl:export_universities_csv", args=[run.pk])
        )
        self.assertNotContains(invalid_financials, "Tech University")

    def test_major_csv_includes_detail_fields(self):
        from academic_etl.services.exporter import major_rows
        run, uni, program = self._make()
        header, rows = major_rows(
            run.programs.select_related("extracted_university").all())
        self.assertIn("university_name", header)
        self.assertIn("duration", header)
        self.assertIn("tuition_fee", header)
        record = dict(zip(header, rows[0]))
        self.assertEqual(record["university_name"], "Tech University")
        self.assertEqual(record["duration"], "4 years")
        self.assertEqual(record["currency"], "VND")

    def test_export_views_return_csv(self):
        run, _, _ = self._make()
        for name in ("export_universities_csv", "export_majors_csv"):
            resp = self.client.get(reverse(f"academic_etl:{name}", args=[run.pk]))
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/csv", resp["Content-Type"])
            self.assertIn("attachment", resp["Content-Disposition"])


class EnglishCrawlTests(TestCase):
    """SiteCrawler prefers a site's English version (no network, fetch mocked)."""

    # VN homepage advertises an English alternate; English pages link to more
    # English pages plus a Vietnamese duplicate that must be dropped.
    SITE = {
        "https://uni.edu.vn": (
            "<html lang='vi'><head>"
            "<link rel='alternate' hreflang='en' href='https://uni.edu.vn/en/'></head>"
            "<body><h1>Trường Đại học</h1>"
            "<a href='/tuyen-sinh'>Tuyển sinh</a></body></html>"),
        "https://uni.edu.vn/en": (
            "<html lang='en'><head><title>University</title></head><body>"
            "<h1>University</h1>"
            "<a href='/en/admissions'>Admissions</a>"
            "<a href='/en/programs'>Programs</a>"
            "<a href='/vi/programs'>Programs</a></body></html>"),
        "https://uni.edu.vn/en/admissions": "<html><body><h1>Admissions</h1></body></html>",
        "https://uni.edu.vn/en/programs": (
            "<html><body><h1>Programs</h1>"
            "<a href='/en/bsc-cs'>Bachelor of Computer Science</a></body></html>"),
    }

    def _crawler(self):
        import tempfile
        from pathlib import Path
        from academic_etl.services.crawler import SiteCrawler
        c = SiteCrawler(cache_dir=Path(tempfile.mkdtemp()), rate_limit=0, max_pages=10)
        c._robots_allows = lambda url: True
        c.fetch = lambda url, retries=2: _fetched(url, self.SITE.get(url.rstrip("/"), ""))
        return c

    def test_english_home_url_detection(self):
        from academic_etl.services.crawler import english_home_url
        soup = BeautifulSoup(self.SITE["https://uni.edu.vn"], "html.parser")
        self.assertEqual(english_home_url(soup, "https://uni.edu.vn"), "https://uni.edu.vn/en/")
        # via a language-switcher anchor
        soup2 = BeautifulSoup("<a href='/en/'>English</a>", "html.parser")
        self.assertEqual(english_home_url(soup2, "https://x.edu.vn"), "https://x.edu.vn/en/")

    def test_switches_to_english_and_drops_vietnamese(self):
        pages = self._crawler().crawl_site("https://uni.edu.vn")
        urls = {p["url"].rstrip("/") for p in pages}
        self.assertIn("https://uni.edu.vn/en", urls)            # hopped to English root
        self.assertIn("https://uni.edu.vn/en/programs", urls)   # followed English links
        self.assertNotIn("https://uni.edu.vn/vi/programs", urls)  # dropped VN duplicate


# Canned Wikipedia HTML (parse-API "text" payload shape).
WIKI_LIST_HTML = (
    "<div class='mw-parser-output'>"
    "<table class='wikitable'>"
    "<tr><td><a href='/wiki/Hanoi_University' title='Hanoi University'>Hanoi University</a></td></tr>"
    "<tr><td><a href='/wiki/Can_Tho_University' title='Can Tho University'>Can Tho University</a></td></tr>"
    "<tr><td><a href='/wiki/Ministry_of_Education_and_Training_(Vietnam)' "
    "title='Ministry of Education and Training (Vietnam)'>Ministry</a></td></tr>"
    "</table>"
    "<ul><li><a href='/wiki/List_of_universities_in_Vietnam' "
    "title='List of universities in Vietnam'>List</a></li></ul>"
    "</div>"
)
WIKI_ARTICLE_HTML = (
    "<div class='mw-parser-output'>"
    "<table class='infobox'>"
    "<tr><th>Type</th><td>Public university</td></tr>"
    "<tr><th>Established</th><td>1956</td></tr>"
    "<tr><th>Students</th><td>38,015 (2023)</td></tr>"
    "<tr><th>Location</th><td>Hanoi, Vietnam</td></tr>"
    "<tr><th>Website</th><td><a href='https://hust.edu.vn'>hust.edu.vn</a></td></tr>"
    "</table>"
    "<p>The Hanoi University of Science and Technology (HUST; Vietnamese: "
    "Đại học Bách khoa) is the largest technical university in Vietnam, "
    "established in 1956.</p>"
    "</div>"
)


class IsEnglishTests(TestCase):
    def test_english_vs_non_english(self):
        from academic_etl.services.lang import is_english
        self.assertTrue(is_english("Bachelor of Science in Computer Science"))
        self.assertTrue(is_english("4 years"))
        self.assertTrue(is_english("Đà Nẵng University of Technology"))  # mostly English
        self.assertFalse(is_english("Đại học Bách khoa Hà Nội"))
        self.assertFalse(is_english("Chứng Chỉ Tiếng Anh"))
        self.assertFalse(is_english("北京大学"))


class WikipediaProviderTests(TestCase):
    def _discover(self):
        from academic_etl.services.wikipedia import WikipediaListProvider
        with patch("academic_etl.services.wikipedia.fetch_parse_html",
                   return_value=("List of universities in Vietnam", WIKI_LIST_HTML)):
            return WikipediaListProvider().discover("Vietnam", "VN")

    def test_institutions_parsed_noise_filtered(self):
        seeds = self._discover()
        names = {s["name"] for s in seeds}
        self.assertIn("Hanoi University", names)
        self.assertIn("Can Tho University", names)
        self.assertNotIn("Ministry of Education and Training (Vietnam)", names)  # ministry
        self.assertFalse(any("List of" in n for n in names))                    # list link
        h = next(s for s in seeds if s["name"] == "Hanoi University")
        self.assertEqual(h["source_name"], "wikipedia")
        self.assertTrue(h["wikipedia_url"].endswith("/wiki/Hanoi_University"))

    def test_run_discovery_wikipedia_branch(self):
        from academic_etl.services.discovery import run_discovery
        run = PipelineRun.objects.create(country_name="Vietnam", country_code="VN",
                                         seed_provider="wikipedia")
        with patch("academic_etl.services.wikipedia.fetch_parse_html",
                   return_value=("List of universities in Vietnam", WIKI_LIST_HTML)):
            run_discovery(run, limit=0)
        seed = InstitutionSeed.objects.get(pipeline_run=run, name="Hanoi University")
        self.assertEqual(seed.source_name, "wikipedia")
        self.assertTrue(seed.wikipedia_url)


class WikipediaExtractTests(TestCase):
    def test_infobox_and_lead_parsed_english(self):
        from academic_etl.services.wikipedia_extract import parse_university_html
        d = {k: v["value"] for k, v in parse_university_html(
            WIKI_ARTICLE_HTML, "https://en.wikipedia.org/wiki/X", "Vietnam").items()}
        self.assertEqual(d["website"], "https://hust.edu.vn")
        self.assertEqual(d["number_of_students"], 38015)
        self.assertEqual(d["city"], "Hanoi")
        self.assertIn("largest technical university", d["description"])
        self.assertNotIn("Đại học", d["description"])  # native-language parenthetical stripped

    def test_enrich_from_wikipedia_stages_english_and_backfills_website(self):
        from academic_etl.services.pipeline import enrich_from_wikipedia
        run = PipelineRun.objects.create(country_name="Vietnam", country_code="VN",
                                         seed_provider="wikipedia")
        seed = InstitutionSeed.objects.create(
            pipeline_run=run, name="Hanoi University of Science and Technology",
            country="Vietnam", country_code="VN", institution_type="university",
            status=InstitutionSeed.Status.VALID, source_name="wikipedia",
            wikipedia_url="https://en.wikipedia.org/wiki/Hanoi_University_of_Science_and_Technology")
        uni = enrich_from_wikipedia(run, seed, html=WIKI_ARTICLE_HTML)
        self.assertEqual(uni.website, "https://hust.edu.vn")
        self.assertEqual(uni.number_of_students, 38015)
        self.assertEqual(uni.city, "Hanoi")
        self.assertTrue(uni.description)
        seed.refresh_from_db()
        self.assertEqual(seed.website, "https://hust.edu.vn")  # backfilled for official crawl
        self.assertTrue(FieldEvidence.objects.filter(
            entity_type="university", entity_id=uni.pk, extraction_method="wikipedia").exists())


class EnglishOnlyExportTests(TestCase):
    def _make(self):
        run = PipelineRun.objects.create(country_name="Vietnam", country_code="VN")
        en = ExtractedUniversity.objects.create(
            pipeline_run=run, name="Hanoi University", description="A university in Hanoi.",
            slug="hanoi-university", review_status=ReviewStatus.APPROVED,
            validation_status=ValidationStatus.VALID)
        vi = ExtractedUniversity.objects.create(
            pipeline_run=run, name="Đại học Quốc gia Hà Nội", description="Trường đại học.",
            slug="dhqg", review_status=ReviewStatus.APPROVED, validation_status=ValidationStatus.VALID)
        ExtractedProgram.objects.create(
            pipeline_run=run, extracted_university=en, program_name="Bachelor of Physics",
            degree_level=DegreeLevel.BACHELOR, is_higher_education_program=True)
        ExtractedProgram.objects.create(
            pipeline_run=run, extracted_university=en, program_name="Cử nhân Vật lý",
            degree_level=DegreeLevel.BACHELOR, is_higher_education_program=True)
        return run, en, vi

    def test_export_excludes_non_english(self):
        from academic_etl.services.exporter import major_rows, university_rows
        run, en, vi = self._make()
        _, urows = university_rows(run.universities.all(), english_only=True)
        names = {r[2] for r in urows}  # col index 2 = name
        self.assertIn("Hanoi University", names)
        self.assertNotIn("Đại học Quốc gia Hà Nội", names)
        # english_only=False keeps both
        _, all_rows = university_rows(run.universities.all(), english_only=False)
        self.assertEqual(len(all_rows), 2)
        # majors
        _, mrows = major_rows(run.programs.select_related("extracted_university").all(),
                              english_only=True)
        mnames = {r[5] for r in mrows}  # col 5 = program_name
        self.assertIn("Bachelor of Physics", mnames)
        self.assertNotIn("Cử nhân Vật lý", mnames)

    def test_validation_flags_non_english_needs_review(self):
        run, en, vi = self._make()
        validate_run(run)
        vi.refresh_from_db()
        self.assertEqual(vi.validation_status, ValidationStatus.NEEDS_REVIEW)
        self.assertTrue(ValidationIssue.objects.filter(
            entity_type="university", entity_id=vi.pk, code="non_english").exists())


class ApproveAllTests(TestCase):
    def test_approve_all_valid(self):
        run = PipelineRun.objects.create(country_name="Vietnam", country_code="VN")
        uni = ExtractedUniversity.objects.create(
            pipeline_run=run, name="Hanoi University", slug="hanoi-university",
            validation_status=ValidationStatus.VALID)
        ExtractedProgram.objects.create(
            pipeline_run=run, extracted_university=uni, program_name="Bachelor of Physics",
            degree_level=DegreeLevel.BACHELOR, is_higher_education_program=True,
            validation_status=ValidationStatus.WARNINGS)
        resp = self.client.post(reverse("academic_etl:run_approve_all_action", args=[run.pk]))
        self.assertEqual(resp.status_code, 302)
        uni.refresh_from_db()
        self.assertEqual(uni.review_status, ReviewStatus.APPROVED)
        self.assertEqual(run.programs.filter(review_status=ReviewStatus.APPROVED).count(), 1)
