from django.urls import path

from . import views

app_name = "academic_etl"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # Unified pipeline (single entry point)
    path("runs/start/", views.start_unified_run, name="start_unified_run"),
    # Pipeline runs
    path("runs/", views.runs_list, name="runs_list"),
    path("runs/<int:run_id>/", views.run_detail, name="run_detail"),
    path("runs/<int:run_id>/progress/", views.run_progress_json, name="run_progress_json"),
    path("runs/<int:run_id>/resume/", views.resume_unified_run, name="resume_unified_run"),
    path("runs/<int:run_id>/gemini/", views.run_gemini_action, name="run_gemini_action"),
    path("runs/<int:run_id>/gemini-majors/", views.run_majors_action, name="run_majors_action"),
    path("runs/<int:run_id>/delete/", views.run_delete_action, name="run_delete_action"),
    path("runs/<int:run_id>/crawl/", views.run_crawl_action, name="run_crawl_action"),
    path("runs/<int:run_id>/validate/", views.run_validate_action, name="run_validate_action"),
    path("runs/<int:run_id>/normalize-data/", views.run_normalize_data_action, name="run_normalize_data_action"),
    path("runs/<int:run_id>/approve-all/", views.run_approve_all_action, name="run_approve_all_action"),
    path("runs/<int:run_id>/import/", views.run_import_action, name="run_import_action"),
    path("runs/<int:run_id>/seeds/", views.seeds_list, name="seeds_list"),
    path("runs/<int:run_id>/universities/", views.universities_list, name="universities_list"),
    path("runs/<int:run_id>/programs/", views.programs_list, name="programs_list"),
    path("runs/<int:run_id>/majors/", views.majors_list, name="majors_list"),
    path("runs/<int:run_id>/specializations/", views.specializations_list, name="specializations_list"),
    path("runs/<int:run_id>/clean/universities/", views.clean_universities, name="clean_universities"),
    path("runs/<int:run_id>/clean/majors/", views.clean_majors, name="clean_majors"),
    path("runs/<int:run_id>/export/universities.csv", views.export_universities_csv, name="export_universities_csv"),
    path("runs/<int:run_id>/export/majors.csv", views.export_majors_csv, name="export_majors_csv"),
    path("runs/<int:run_id>/export/majors-simple.csv", views.export_simple_majors_csv, name="export_simple_majors_csv"),
    path("runs/<int:run_id>/universities/add/", views.add_university, name="add_university"),
    path("runs/<int:run_id>/import-preview/", views.import_preview, name="import_preview"),
    # University/program detail + actions
    path("universities/<int:pk>/", views.university_detail, name="university_detail"),
    path("universities/<int:pk>/action/", views.university_action, name="university_action"),
    path("universities/<int:pk>/majors/add/", views.add_major, name="add_major"),
    path("programs/<int:pk>/", views.program_detail, name="program_detail"),
    path("programs/<int:pk>/action/", views.program_action, name="program_action"),
    path("specializations/<int:pk>/action/", views.specialization_action, name="specialization_action"),
    path("evidence/<int:pk>/", views.evidence_detail, name="evidence_detail"),
    path("import-jobs/<int:pk>/", views.import_job_detail, name="import_job_detail"),
    # Global workspaces (cross-run views)
    path("all/universities/", views.global_universities, name="global_universities"),
    path("all/majors/", views.global_majors, name="global_majors"),
    # Schedule management
    path("schedules/", views.schedules_list, name="schedules_list"),
    path("schedules/create/", views.schedule_create, name="schedule_create"),
    path("schedules/<int:pk>/toggle/", views.schedule_toggle, name="schedule_toggle"),
    path("schedules/<int:pk>/delete/", views.schedule_delete, name="schedule_delete"),
    # Country configuration
    path("countries/", views.country_configs_list, name="country_configs_list"),
    # Data management
    path("clear/staging/", views.clear_staging, name="clear_staging"),
    path("clear/production/", views.clear_production, name="clear_production"),
    path("clear/all/", views.clear_all, name="clear_all"),
]
