"""Target ("production") models that approved ETL records are imported into.

Kept intentionally close to the columns of the University_Import_Clean CSV so
the importer can map staging fields 1:1. If the real Beyondegree backend ever
lands in this repo, the importer in academic_etl/services/importer.py is the
only place that needs re-pointing.
"""

from django.db import models


class University(models.Model):
    name = models.CharField(max_length=500)
    slug = models.SlugField(max_length=500, unique=True)
    location = models.CharField(max_length=500, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="")
    country_code = models.CharField(max_length=3, blank=True, default="")
    description = models.TextField(blank=True, default="")
    sponsored = models.BooleanField(default=False)
    website = models.URLField(max_length=500, blank=True, default="")
    global_rank = models.CharField(max_length=100, blank=True, default="")
    financials = models.CharField(max_length=500, blank=True, default="")
    financials_currency = models.CharField(max_length=3, blank=True, default="")
    financials_amount_low = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    financials_amount_high = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    financials_usd_low = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    financials_usd_high = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    student_loan_available = models.BooleanField(default=False)
    campus_student_life = models.TextField(blank=True, default="")
    number_of_students = models.PositiveIntegerField(null=True, blank=True)
    student_to_faculty_ratio = models.CharField(max_length=50, blank=True, default="")
    international_student_ratio = models.CharField(max_length=50, blank=True, default="")
    housing_availability = models.BooleanField(default=False)
    admissions_contact = models.EmailField(max_length=254, blank=True, default="")
    admissions_phone = models.CharField(max_length=50, blank=True, default="")
    contact_person = models.CharField(max_length=255, blank=True, default="")
    admissions_page_link = models.URLField(max_length=500, blank=True, default="")
    immigration_support = models.BooleanField(default=False)
    university_campuses = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "universities"

    def __str__(self):
        return self.name


class Program(models.Model):
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name="programs")
    program_name = models.CharField(max_length=500)
    degree_level = models.CharField(max_length=50, blank=True, default="")
    field_of_study = models.CharField(max_length=255, blank=True, default="")
    faculty_or_school = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    duration = models.CharField(max_length=100, blank=True, default="")
    study_mode = models.CharField(max_length=100, blank=True, default="")
    language = models.CharField(max_length=100, blank=True, default="")
    tuition_fee = models.CharField(max_length=255, blank=True, default="")
    tuition_amount_low = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    tuition_amount_high = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    tuition_usd_low = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    tuition_usd_high = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    tuition_period = models.CharField(max_length=20, blank=True, default="")
    currency = models.CharField(max_length=10, blank=True, default="")
    program_url = models.URLField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("university", "program_name", "degree_level")]

    def __str__(self):
        return f"{self.program_name} ({self.degree_level})"


class Specialization(models.Model):
    """Third level: specializations/concentrations within a program/major."""
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="specializations")
    specialization_name = models.CharField(max_length=500)
    description = models.TextField(blank=True, default="")
    specialization_url = models.URLField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("program", "specialization_name")]

    def __str__(self):
        return self.specialization_name
