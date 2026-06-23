from django.contrib import admin

from .models import Program, Specialization, University


@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "country", "website", "number_of_students", "updated_at")
    search_fields = ("name", "slug", "website")
    list_filter = ("country",)


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("program_name", "degree_level", "university", "updated_at")
    list_filter = ("degree_level",)
    search_fields = ("program_name",)


@admin.register(Specialization)
class SpecializationAdmin(admin.ModelAdmin):
    list_display = ("specialization_name", "program", "updated_at")
    search_fields = ("specialization_name",)
