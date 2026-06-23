from django.contrib import admin

from .models import (
    Country,
    CountryConfig,
    CrawlSchedule,
    CrawledPage,
    ExchangeRate,
    ExtractedProgram,
    ExtractedSpecialization,
    ExtractedUniversity,
    FieldEvidence,
    ImportJob,
    ImportLog,
    InstitutionSeed,
    PipelineRun,
    ValidationIssue,
)


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "numeric_code")
    search_fields = ("name", "code")


@admin.register(CountryConfig)
class CountryConfigAdmin(admin.ModelAdmin):
    list_display = ("country_name", "country_code", "currency_code", "crawl_frequency", "is_active")
    list_filter = ("is_active", "crawl_frequency")
    search_fields = ("country_name", "country_code")


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("currency_code", "rate_to_usd", "source", "fetched_at")
    list_filter = ("source",)
    search_fields = ("currency_code",)


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ("pk", "country_name", "crawl_mode", "seed_provider", "status",
                    "total_discovered_institutions", "total_crawled_institutions",
                    "total_programs_found", "created_at")
    list_filter = ("status", "crawl_mode", "seed_provider")


@admin.register(InstitutionSeed)
class InstitutionSeedAdmin(admin.ModelAdmin):
    list_display = ("name", "pipeline_run", "institution_type", "status",
                    "confidence_score", "website", "source_name", "wikidata_qid")
    list_filter = ("status", "institution_type", "source_name")
    search_fields = ("name", "website", "wikidata_qid")


@admin.register(CrawledPage)
class CrawledPageAdmin(admin.ModelAdmin):
    list_display = ("url", "page_type", "status_code", "render_engine", "depth", "seed", "crawled_at")
    list_filter = ("page_type", "status_code", "render_engine")
    search_fields = ("url", "title")


@admin.register(ExtractedUniversity)
class ExtractedUniversityAdmin(admin.ModelAdmin):
    list_display = ("name", "pipeline_run", "country", "validation_status",
                    "review_status", "confidence_score", "completeness_score")
    list_filter = ("validation_status", "review_status", "institution_type")
    search_fields = ("name", "slug", "website")


@admin.register(ExtractedProgram)
class ExtractedProgramAdmin(admin.ModelAdmin):
    list_display = ("program_name", "degree_level", "extracted_university",
                    "is_higher_education_program", "validation_status", "review_status",
                    "confidence_score")
    list_filter = ("degree_level", "validation_status", "review_status",
                   "is_higher_education_program")
    search_fields = ("program_name",)


@admin.register(FieldEvidence)
class FieldEvidenceAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "entity_id", "field_name", "extractor_name",
                    "extraction_method", "confidence_score", "created_at")
    list_filter = ("entity_type", "extraction_method", "extractor_name")
    search_fields = ("field_name", "extracted_value")


@admin.register(ValidationIssue)
class ValidationIssueAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "entity_id", "field_name", "severity", "code", "pipeline_run")
    list_filter = ("severity", "code", "entity_type")


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = ("pk", "pipeline_run", "dry_run", "approved_only", "status",
                    "total_processed", "total_created", "total_updated", "total_skipped")
    list_filter = ("dry_run", "status")


@admin.register(ImportLog)
class ImportLogAdmin(admin.ModelAdmin):
    list_display = ("import_job", "entity_type", "entity_id", "action", "matched_by", "target_id")
    list_filter = ("action", "entity_type")


@admin.register(ExtractedSpecialization)
class ExtractedSpecializationAdmin(admin.ModelAdmin):
    list_display = ("specialization_name", "extracted_program", "confidence_score",
                    "validation_status", "review_status")
    list_filter = ("validation_status", "review_status")
    search_fields = ("specialization_name",)


@admin.register(CrawlSchedule)
class CrawlScheduleAdmin(admin.ModelAdmin):
    list_display = ("country_name", "country_code", "frequency", "strategy",
                    "is_active", "last_run_at", "next_run_at", "error_count")
    list_filter = ("is_active", "frequency", "strategy")
    search_fields = ("country_name", "country_code")
