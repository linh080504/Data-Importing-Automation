"""Cooperative background reset for ETL staging and production data."""

import os
import subprocess
import sys
import time
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from academic_etl.models import (
    CrawledPage,
    DataResetJob,
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
from universities.models import Program, Specialization, University

from .pipeline_execution import LOCK_POLL_SECONDS, PipelineHostLock


ACTIVE_RUN_STATUSES = [
    PipelineRun.Status.QUEUED,
    PipelineRun.Status.DISCOVERING,
    PipelineRun.Status.CRAWLING,
    PipelineRun.Status.RETRYING,
    PipelineRun.Status.VALIDATING,
    PipelineRun.Status.IMPORTING,
]

STAGING_MODELS = [
    PipelineRun,
    InstitutionSeed,
    CrawledPage,
    ExtractedUniversity,
    ExtractedProgram,
    ExtractedSpecialization,
    ValidationIssue,
    FieldEvidence,
    ImportJob,
    ImportLog,
]
PRODUCTION_MODELS = [University, Program, Specialization]


def launch_data_reset_worker(job_id: int) -> int:
    manage_py = Path(settings.BASE_DIR) / "manage.py"
    kwargs = {"cwd": str(settings.BASE_DIR), "close_fds": os.name != "nt"}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    process = subprocess.Popen(
        [sys.executable, str(manage_py), "run_data_reset", "--job-id", str(job_id)],
        **kwargs,
    )
    DataResetJob.objects.filter(pk=job_id).update(worker_pid=process.pid)
    return process.pid


def request_data_reset(mode: str) -> tuple[DataResetJob, bool]:
    if mode not in DataResetJob.Mode.values:
        raise ValueError(f"Unsupported reset mode: {mode}")
    with transaction.atomic():
        existing = DataResetJob.active().order_by("requested_at").first()
        if existing:
            return existing, False
        job = DataResetJob.objects.create(
            mode=mode,
            status=DataResetJob.Status.PENDING,
        )
        PipelineRun.objects.filter(status__in=ACTIVE_RUN_STATUSES).update(
            cancel_requested_at=timezone.now(),
            status=PipelineRun.Status.CANCELLING,
        )
    try:
        launch_data_reset_worker(job.pk)
    except OSError as exc:
        job.status = DataResetJob.Status.FAILED
        job.error_message = str(exc)[:2000]
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "error_message", "completed_at", "updated_at"])
        raise
    return job, True


def _reset_sequences(models):
    tables = [model._meta.db_table for model in models]
    if not tables:
        return
    placeholders = ",".join(["%s"] * len(tables))
    with connection.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})",
            tables,
        )


def run_data_reset(job_id: int):
    job = DataResetJob.objects.get(pk=job_id)
    job.status = DataResetJob.Status.CANCELLING
    job.started_at = job.started_at or timezone.now()
    job.save(update_fields=["status", "started_at", "updated_at"])
    lock = PipelineHostLock()
    try:
        while not lock.acquire():
            time.sleep(LOCK_POLL_SECONDS)
            DataResetJob.objects.filter(pk=job_id).update(updated_at=timezone.now())

        job.status = DataResetJob.Status.CLEARING
        job.save(update_fields=["status", "updated_at"])
        deleted_count = 0
        reset_models = []
        with transaction.atomic():
            if job.mode in {DataResetJob.Mode.STAGING, DataResetJob.Mode.ALL}:
                deleted_count += PipelineRun.objects.all().delete()[0]
                deleted_count += FieldEvidence.objects.all().delete()[0]
                reset_models.extend(STAGING_MODELS)
            if job.mode in {DataResetJob.Mode.PRODUCTION, DataResetJob.Mode.ALL}:
                deleted_count += University.objects.all().delete()[0]
                reset_models.extend(PRODUCTION_MODELS)
            _reset_sequences(reset_models)

        job.status = DataResetJob.Status.COMPLETED
        job.deleted_count = deleted_count
        job.completed_at = timezone.now()
        job.worker_pid = None
        job.save(update_fields=[
            "status", "deleted_count", "completed_at", "worker_pid", "updated_at",
        ])
    except Exception as exc:
        job.status = DataResetJob.Status.FAILED
        job.error_message = str(exc)[:2000]
        job.completed_at = timezone.now()
        job.worker_pid = None
        job.save(update_fields=[
            "status", "error_message", "completed_at", "worker_pid", "updated_at",
        ])
        raise
    finally:
        lock.release()
