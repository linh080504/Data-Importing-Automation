"""Staging models for the country-based academic ETL pipeline.

Flow: PipelineRun -> InstitutionSeed (discovery) -> CrawledPage (crawl)
-> ExtractedUniversity / ExtractedProgram (+ FieldEvidence per field)
-> ValidationIssue (validate) -> ImportJob / ImportLog (import).
"""

from django.db import models


class InstitutionType(models.TextChoices):
    UNIVERSITY = "university"
    COLLEGE = "college"  # college with higher-education programs
    INSTITUTE = "institute"
    INSTITUTE_OF_TECHNOLOGY = "institute_of_technology"
    POLYTECHNIC = "polytechnic"
    GRADUATE_SCHOOL = "graduate_school"
    POSTGRADUATE_INSTITUTE = "postgraduate_institute"
    MEDICAL_UNIVERSITY = "medical_university"
    BUSINESS_SCHOOL = "business_school"
    ART_SCHOOL = "art_school"
    # invalid / non-higher-education types (kept so we can record WHY a seed was rejected)
    HIGH_SCHOOL = "high_school"
    SECONDARY_SCHOOL = "secondary_school"
    PRIMARY_SCHOOL = "primary_school"
    KINDERGARTEN = "kindergarten"
    LANGUAGE_CENTER = "language_center"
    TRAINING_CENTER = "training_center"
    COACHING_CENTER = "coaching_center"
    BOOTCAMP = "bootcamp"
    UNKNOWN = "unknown"


VALID_INSTITUTION_TYPES = {
    InstitutionType.UNIVERSITY,
    InstitutionType.COLLEGE,
    InstitutionType.INSTITUTE,
    InstitutionType.INSTITUTE_OF_TECHNOLOGY,
    InstitutionType.POLYTECHNIC,
    InstitutionType.GRADUATE_SCHOOL,
    InstitutionType.POSTGRADUATE_INSTITUTE,
    InstitutionType.MEDICAL_UNIVERSITY,
    InstitutionType.BUSINESS_SCHOOL,
    InstitutionType.ART_SCHOOL,
}

INVALID_INSTITUTION_TYPES = {
    InstitutionType.HIGH_SCHOOL,
    InstitutionType.SECONDARY_SCHOOL,
    InstitutionType.PRIMARY_SCHOOL,
    InstitutionType.KINDERGARTEN,
    InstitutionType.LANGUAGE_CENTER,
    InstitutionType.TRAINING_CENTER,
    InstitutionType.COACHING_CENTER,
    InstitutionType.BOOTCAMP,
}


class DegreeLevel(models.TextChoices):
    ASSOCIATE = "associate"
    DIPLOMA = "diploma"  # higher-education diploma
    BACHELOR = "bachelor"
    MASTER = "master"
    PHD = "phd"
    POSTGRAD_CERT = "postgraduate_certificate"
    POSTGRAD_DIPLOMA = "postgraduate_diploma"
    PROFESSIONAL = "professional"
    NON_DEGREE = "non_degree"  # short course / workshop / bootcamp etc.
    UNKNOWN = "unknown"


HIGHER_ED_DEGREE_LEVELS = {
    DegreeLevel.BACHELOR,
    DegreeLevel.MASTER,
    DegreeLevel.PHD,
    DegreeLevel.POSTGRAD_CERT,
    DegreeLevel.POSTGRAD_DIPLOMA,
    DegreeLevel.PROFESSIONAL,
}


class ReviewStatus(models.TextChoices):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


class ValidationStatus(models.TextChoices):
    NOT_VALIDATED = "not_validated"
    VALID = "valid"
    WARNINGS = "warnings"
    INVALID = "invalid"
    NEEDS_REVIEW = "needs_review"


class Country(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=2, unique=True, help_text="ISO 3166-1 alpha-2")
    numeric_code = models.CharField(max_length=3, blank=True, default="", help_text="ISO 3166-1 numeric")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "countries"

    def __str__(self):
        return f"{self.name} ({self.code})"


class CountryConfig(models.Model):
    """Country-specific configuration for the global ETL pipeline."""

    class CrawlFrequency(models.TextChoices):
        WEEKLY = "weekly"
        BIWEEKLY = "biweekly"
        MONTHLY = "monthly"
        QUARTERLY = "quarterly"

    country_name = models.CharField(max_length=100, unique=True)
    country_code = models.CharField(max_length=2, unique=True, help_text="ISO 3166-1 alpha-2")
    currency_code = models.CharField(max_length=3, help_text="ISO 4217 (VND, INR, USD)")
    numeric_code = models.CharField(max_length=3, blank=True, default="", help_text="ISO 3166-1 numeric")
    denomination_config = models.JSONField(
        default=dict, blank=True,
        help_text='Denomination abbreviations and multipliers, e.g. {"k": 1000, "tr": 1000000}',
    )
    primary_languages = models.JSONField(
        default=list, blank=True,
        help_text='ISO 639-1 codes, e.g. ["vi", "en"]',
    )
    url_language_markers = models.JSONField(
        default=list, blank=True,
        help_text='URL path markers for local language, e.g. ["/vi/", "/vn/"]',
    )
    degree_level_map = models.JSONField(
        default=dict, blank=True,
        help_text='Local degree terms -> canonical level, e.g. {"cử nhân": "bachelor"}',
    )
    crawl_frequency = models.CharField(
        max_length=20, choices=CrawlFrequency.choices, default=CrawlFrequency.MONTHLY,
    )
    max_institutions = models.PositiveIntegerField(default=200)
    preferred_providers = models.JSONField(
        default=list, blank=True,
        help_text='Ordered list: ["wikipedia", "wikidata", "hipolabs"]',
    )
    is_active = models.BooleanField(default=True)
    last_crawl_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "country configs"

    def __str__(self):
        return f"{self.country_name} ({self.country_code})"


class ExchangeRate(models.Model):
    """Cached exchange rates for financial format standardization."""
    currency_code = models.CharField(max_length=3, db_index=True, help_text="ISO 4217")
    rate_to_usd = models.DecimalField(max_digits=16, decimal_places=6, help_text="1 USD = X units of this currency")
    source = models.CharField(max_length=50, default="frankfurter")
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["currency_code", "-fetched_at"])]

    def __str__(self):
        return f"{self.currency_code}: 1 USD = {self.rate_to_usd}"


class PipelineRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        QUEUED = "queued"
        DISCOVERING = "discovering"
        CRAWLING = "crawling"
        RETRYING = "retrying"
        CANCELLING = "cancelling"
        CANCELLED = "cancelled"
        VALIDATING = "validating"
        REVIEW = "review"
        IMPORTING = "importing"
        COMPLETED = "completed"
        FAILED = "failed"

    country_name = models.CharField(max_length=100)
    country_code = models.CharField(max_length=2, blank=True, default="")
    crawl_mode = models.CharField(
        max_length=20,
        default="full",
        help_text="discover_only | full | csv_seed",
    )
    seed_provider = models.CharField(
        max_length=50, default="wikipedia",
        help_text="wikipedia | wikidata | csv | fanar",
    )
    crawl_scope = models.CharField(max_length=50, default="official_site", blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    parent_run = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="child_runs", help_text="Previous run this incremental run is updating",
    )
    is_incremental = models.BooleanField(default=False)
    total_discovered_institutions = models.PositiveIntegerField(default=0)
    total_crawled_institutions = models.PositiveIntegerField(default=0)
    total_programs_found = models.PositiveIntegerField(default=0)
    stats_json = models.JSONField(default=dict, blank=True)
    execution_state = models.JSONField(default=dict, blank=True, db_default={})
    worker_token = models.CharField(
        max_length=64, blank=True, default="", db_default="", db_index=True,
    )
    worker_pid = models.PositiveIntegerField(null=True, blank=True)
    worker_heartbeat_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0, db_default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    cancel_requested_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Run #{self.pk} {self.country_name} [{self.status}]"


class DataResetJob(models.Model):
    class Mode(models.TextChoices):
        STAGING = "staging"
        PRODUCTION = "production"
        ALL = "all"

    class Status(models.TextChoices):
        PENDING = "pending"
        CANCELLING = "cancelling"
        CLEARING = "clearing"
        COMPLETED = "completed"
        FAILED = "failed"

    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.ALL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    worker_pid = models.PositiveIntegerField(null=True, blank=True)
    deleted_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def active(cls):
        return cls.objects.filter(status__in=[
            cls.Status.PENDING,
            cls.Status.CANCELLING,
            cls.Status.CLEARING,
        ])

    def __str__(self):
        return f"Reset #{self.pk} {self.mode} [{self.status}]"


class InstitutionSeed(models.Model):
    class Status(models.TextChoices):
        DISCOVERED = "discovered"
        VALID = "valid"
        INVALID = "invalid"
        NEEDS_REVIEW = "needs_review"
        CRAWLED = "crawled"
        CRAWL_FAILED = "crawl_failed"
        SKIPPED = "skipped"

    pipeline_run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="seeds")
    name = models.CharField(max_length=500)
    country = models.CharField(max_length=100)
    country_code = models.CharField(max_length=2, blank=True, default="")
    city = models.CharField(max_length=255, blank=True, default="")
    region = models.CharField(max_length=255, blank=True, default="")
    website = models.URLField(max_length=500, blank=True, default="")
    institution_type = models.CharField(
        max_length=30, choices=InstitutionType.choices, default=InstitutionType.UNKNOWN
    )
    source_url = models.URLField(max_length=500, blank=True, default="")
    source_name = models.CharField(max_length=100, blank=True, default="")
    # Knowledge-base provenance (populated by the Wikidata/Wikipedia provider).
    wikidata_qid = models.CharField(max_length=20, blank=True, default="", db_index=True)
    wikipedia_url = models.URLField(max_length=500, blank=True, default="")
    confidence_score = models.FloatField(default=0.0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DISCOVERED)
    raw_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("pipeline_run", "name", "city", "website")]

    @property
    def is_higher_education(self):
        return self.institution_type in VALID_INSTITUTION_TYPES

    def __str__(self):
        return self.name


class CrawledPage(models.Model):
    pipeline_run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="pages")
    seed = models.ForeignKey(
        InstitutionSeed, on_delete=models.CASCADE, related_name="pages", null=True, blank=True
    )
    url = models.URLField(max_length=1000)
    final_url = models.URLField(max_length=1000, blank=True, default="")
    page_type = models.CharField(max_length=30, default="other")
    status_code = models.IntegerField(null=True, blank=True)
    title = models.CharField(max_length=500, blank=True, default="")
    depth = models.PositiveSmallIntegerField(default=0)
    html_hash = models.CharField(max_length=64, blank=True, default="")
    html_cache_path = models.CharField(max_length=500, blank=True, default="")
    # How the HTML was obtained: "requests" (static) or "scrapling_dynamic" (JS-rendered).
    render_engine = models.CharField(max_length=20, blank=True, default="requests")
    fetch_error = models.TextField(blank=True, default="")
    crawled_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.page_type}] {self.url}"


class ExtractedUniversity(models.Model):
    pipeline_run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="universities")
    seed = models.ForeignKey(
        InstitutionSeed, on_delete=models.SET_NULL, related_name="extracted_universities",
        null=True, blank=True,
    )
    # CSV / target university fields
    external_id = models.CharField(max_length=50, blank=True, default="")
    name = models.CharField(max_length=500, blank=True, default="")
    location = models.CharField(max_length=500, blank=True, default="")
    description = models.TextField(blank=True, default="")
    slug = models.SlugField(max_length=500, blank=True, default="")
    sponsored = models.BooleanField(null=True, blank=True)
    website = models.URLField(max_length=500, blank=True, default="")
    global_rank = models.CharField(max_length=100, blank=True, default="")
    financials = models.CharField(max_length=500, blank=True, default="")
    financials_raw = models.CharField(max_length=500, blank=True, default="")
    financials_currency = models.CharField(max_length=3, blank=True, default="")
    financials_amount_low = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    financials_amount_high = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    financials_usd_low = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    financials_usd_high = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    student_loan_available = models.BooleanField(null=True, blank=True)
    campus_student_life = models.TextField(blank=True, default="")
    number_of_students = models.PositiveIntegerField(null=True, blank=True)
    student_to_faculty_ratio = models.CharField(max_length=50, blank=True, default="")
    international_student_ratio = models.CharField(max_length=50, blank=True, default="")
    housing_availability = models.BooleanField(null=True, blank=True)
    admissions_contact = models.CharField(max_length=254, blank=True, default="")
    admissions_phone = models.CharField(max_length=50, blank=True, default="")
    contact_person = models.CharField(max_length=255, blank=True, default="")
    admissions_page_link = models.URLField(max_length=500, blank=True, default="")
    immigration_support = models.BooleanField(null=True, blank=True)
    university_campuses = models.PositiveIntegerField(null=True, blank=True)
    # pipeline metadata
    country = models.CharField(max_length=100, blank=True, default="")
    country_code = models.CharField(max_length=2, blank=True, default="")
    city = models.CharField(max_length=255, blank=True, default="")
    region = models.CharField(max_length=255, blank=True, default="")
    institution_type = models.CharField(
        max_length=30, choices=InstitutionType.choices, default=InstitutionType.UNKNOWN
    )
    raw_json = models.JSONField(default=dict, blank=True)
    normalized_json = models.JSONField(default=dict, blank=True)
    confidence_score = models.FloatField(default=0.0)
    completeness_score = models.FloatField(default=0.0)
    validation_status = models.CharField(
        max_length=20, choices=ValidationStatus.choices, default=ValidationStatus.NOT_VALIDATED
    )
    review_status = models.CharField(
        max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING
    )
    review_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        from .services.normalize import normalize_email, normalize_phone
        self.sponsored = False
        self.admissions_phone = normalize_phone(self.admissions_phone)
        self.admissions_contact = normalize_email(self.admissions_contact)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"sponsored"}
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "extracted universities"

    def __str__(self):
        return self.name or f"ExtractedUniversity #{self.pk}"


class ExtractedProgram(models.Model):
    pipeline_run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="programs")
    extracted_university = models.ForeignKey(
        ExtractedUniversity, on_delete=models.CASCADE, related_name="programs"
    )
    university_slug = models.SlugField(max_length=500, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="")
    country_code = models.CharField(max_length=2, blank=True, default="")
    campus = models.CharField(max_length=255, blank=True, default="")
    program_name = models.CharField(max_length=500)
    degree_level = models.CharField(
        max_length=30, choices=DegreeLevel.choices, default=DegreeLevel.UNKNOWN
    )
    field_of_study = models.CharField(max_length=255, blank=True, default="")
    faculty_or_school = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    duration = models.CharField(max_length=100, blank=True, default="")
    study_mode = models.CharField(max_length=100, blank=True, default="")
    language = models.CharField(max_length=100, blank=True, default="")
    tuition_fee = models.CharField(max_length=255, blank=True, default="")
    tuition_fee_raw = models.CharField(max_length=500, blank=True, default="")
    tuition_amount_low = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    tuition_amount_high = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    tuition_usd_low = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    tuition_usd_high = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    tuition_period = models.CharField(max_length=20, blank=True, default="", help_text="annual | semester | total | monthly")
    currency = models.CharField(max_length=10, blank=True, default="")
    intake = models.CharField(max_length=255, blank=True, default="")
    application_deadline = models.CharField(max_length=255, blank=True, default="")
    admission_requirements = models.TextField(blank=True, default="")
    career_outcomes = models.TextField(blank=True, default="")
    accreditation = models.CharField(max_length=255, blank=True, default="")
    program_url = models.URLField(max_length=1000, blank=True, default="")
    source_url = models.URLField(max_length=1000, blank=True, default="")
    is_higher_education_program = models.BooleanField(null=True, blank=True)
    raw_json = models.JSONField(default=dict, blank=True)
    normalized_json = models.JSONField(default=dict, blank=True)
    confidence_score = models.FloatField(default=0.0)
    validation_status = models.CharField(
        max_length=20, choices=ValidationStatus.choices, default=ValidationStatus.NOT_VALIDATED
    )
    review_status = models.CharField(
        max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.program_name} ({self.degree_level})"


class FieldEvidence(models.Model):
    """Provenance for every extracted field value."""

    entity_type = models.CharField(max_length=30)  # "university" | "program"
    entity_id = models.PositiveIntegerField()
    field_name = models.CharField(max_length=100)
    extracted_value = models.TextField(blank=True, default="")
    normalized_value = models.TextField(blank=True, default="")
    source_url = models.URLField(max_length=1000, blank=True, default="")
    page_title = models.CharField(max_length=500, blank=True, default="")
    page_type = models.CharField(max_length=30, blank=True, default="")
    css_selector = models.CharField(max_length=255, blank=True, default="")
    text_snippet = models.TextField(blank=True, default="")
    raw_text = models.TextField(blank=True, default="")
    confidence_score = models.FloatField(default=0.0)
    extractor_name = models.CharField(max_length=100, blank=True, default="")
    extraction_method = models.CharField(max_length=30, default="rule")  # rule | csv | manual
    validation_notes = models.TextField(blank=True, default="")
    crawled_at = models.DateTimeField(null=True, blank=True)
    raw_html_hash = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["entity_type", "entity_id", "field_name"])]

    def __str__(self):
        return f"{self.entity_type}#{self.entity_id}.{self.field_name}"


class ValidationIssue(models.Model):
    class Severity(models.TextChoices):
        ERROR = "error"
        WARNING = "warning"
        INFO = "info"

    pipeline_run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="issues")
    entity_type = models.CharField(max_length=30)
    entity_id = models.PositiveIntegerField()
    field_name = models.CharField(max_length=100, blank=True, default="")
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.WARNING)
    code = models.CharField(max_length=50, blank=True, default="")
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.severity}] {self.entity_type}#{self.entity_id}: {self.code}"


class ImportJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        RUNNING = "running"
        COMPLETED = "completed"
        FAILED = "failed"

    pipeline_run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="import_jobs")
    dry_run = models.BooleanField(default=True)
    approved_only = models.BooleanField(default=True)
    confidence_threshold = models.FloatField(default=0.75)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total_processed = models.PositiveIntegerField(default=0)
    total_created = models.PositiveIntegerField(default=0)
    total_updated = models.PositiveIntegerField(default=0)
    total_skipped = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        mode = "dry-run" if self.dry_run else "live"
        return f"ImportJob #{self.pk} ({mode}) for run #{self.pipeline_run_id}"


class ImportLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create"
        UPDATE = "update"
        SKIP = "skip"
        WOULD_CREATE = "would_create"
        WOULD_UPDATE = "would_update"
        ERROR = "error"

    import_job = models.ForeignKey(ImportJob, on_delete=models.CASCADE, related_name="logs")
    entity_type = models.CharField(max_length=30)
    entity_id = models.PositiveIntegerField()
    target_id = models.PositiveIntegerField(null=True, blank=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    matched_by = models.CharField(max_length=50, blank=True, default="")
    diff_json = models.JSONField(default=dict, blank=True)
    message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} {self.entity_type}#{self.entity_id}"


class ExtractedSpecialization(models.Model):
    """Third level of the academic hierarchy: specializations within a program/major."""
    pipeline_run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="specializations")
    extracted_program = models.ForeignKey(
        ExtractedProgram, on_delete=models.CASCADE, related_name="specializations",
    )
    specialization_name = models.CharField(max_length=500)
    description = models.TextField(blank=True, default="")
    specialization_url = models.URLField(max_length=1000, blank=True, default="")
    source_url = models.URLField(max_length=1000, blank=True, default="")
    raw_json = models.JSONField(default=dict, blank=True)
    confidence_score = models.FloatField(default=0.0)
    validation_status = models.CharField(
        max_length=20, choices=ValidationStatus.choices, default=ValidationStatus.NOT_VALIDATED,
    )
    review_status = models.CharField(
        max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("extracted_program", "specialization_name")]

    def __str__(self):
        return f"{self.specialization_name} (under {self.extracted_program.program_name})"


class CrawlSchedule(models.Model):
    """Scheduled crawl jobs per country for automation."""

    class Frequency(models.TextChoices):
        WEEKLY = "weekly"
        BIWEEKLY = "biweekly"
        MONTHLY = "monthly"
        QUARTERLY = "quarterly"

    class Strategy(models.TextChoices):
        HYBRID = "hybrid"
        CRAWL = "crawl"
        GEMINI = "gemini"
        FANAR = "fanar"

    country_code = models.CharField(max_length=2, unique=True)
    country_name = models.CharField(max_length=100)
    frequency = models.CharField(max_length=20, choices=Frequency.choices, default=Frequency.MONTHLY)
    strategy = models.CharField(max_length=20, choices=Strategy.choices, default=Strategy.HYBRID)
    discover_limit = models.PositiveIntegerField(default=200)
    crawl_limit = models.PositiveIntegerField(default=50)
    max_pages_per_site = models.PositiveIntegerField(default=8)
    is_incremental = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    last_run = models.ForeignKey(
        PipelineRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    error_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.country_name} ({self.frequency})"
