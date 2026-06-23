"""Durable local execution state for the unified ETL pipeline."""

import os
import uuid
from datetime import timedelta
from pathlib import Path

import requests
from django.conf import settings
from django.db import OperationalError
from django.db.models import Q
from django.utils import timezone

from academic_etl.models import PipelineRun


MAX_RETRIES = 3
RETRY_DELAYS_SECONDS = (15, 60, 300)
STALE_AFTER_SECONDS = 90
LOCK_POLL_SECONDS = 5
PIPELINE_STAGES = (
    "wikipedia",
    "web_sources",
    "programs",
    "ai_fields",
    "ai_majors",
    "validation",
)


class PipelineLeaseLost(RuntimeError):
    pass


class PipelineCancelled(RuntimeError):
    pass


class PipelineHostLock:
    """Cross-process advisory lock; released automatically when a worker dies."""

    def __init__(self, path=None):
        self.path = Path(path or settings.ETL_VAR_DIR / "unified_pipeline.lock")
        self.handle = None

    def acquire(self) -> bool:
        if self.handle is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self.handle = handle
        return True

    def release(self):
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None

    def __enter__(self):
        if not self.acquire():
            raise BlockingIOError("Another unified pipeline owns the host lock")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()


def _stale_cutoff():
    seconds = getattr(settings, "ETL_WORKER_STALE_SECONDS", STALE_AFTER_SECONDS)
    return timezone.now() - timedelta(seconds=seconds)


def claim_pipeline_run(run_id: int, *, allow_failed: bool = False) -> str | None:
    """Atomically reserve a run for one detached worker."""
    token = uuid.uuid4().hex
    now = timezone.now()
    qs = PipelineRun.objects.filter(pk=run_id)
    if allow_failed:
        qs = qs.filter(status=PipelineRun.Status.FAILED)
    else:
        qs = qs.exclude(status__in=[
            PipelineRun.Status.REVIEW,
            PipelineRun.Status.COMPLETED,
            PipelineRun.Status.FAILED,
            PipelineRun.Status.CANCELLING,
            PipelineRun.Status.CANCELLED,
        ])
    qs = qs.filter(
        Q(worker_token="")
        | Q(worker_heartbeat_at__isnull=True)
        | Q(worker_heartbeat_at__lt=_stale_cutoff())
    )
    updates = {
        "status": PipelineRun.Status.QUEUED,
        "worker_token": token,
        "worker_pid": None,
        "worker_heartbeat_at": now,
        "next_retry_at": None,
        "error_message": "",
        "updated_at": now,
    }
    if allow_failed:
        updates["retry_count"] = 0
    updated = qs.update(
        **updates,
    )
    return token if updated else None


def claim_stale_pipeline_runs() -> list[tuple[int, str]]:
    stale_ids = list(
        PipelineRun.objects.filter(
            ~Q(worker_token=""),
            status__in=[
                PipelineRun.Status.QUEUED,
                PipelineRun.Status.CRAWLING,
                PipelineRun.Status.RETRYING,
                PipelineRun.Status.VALIDATING,
            ],
        ).filter(
            Q(worker_heartbeat_at__isnull=True)
            | Q(worker_heartbeat_at__lt=_stale_cutoff())
        ).values_list("pk", flat=True)
    )
    claimed = []
    for run_id in stale_ids:
        token = claim_pipeline_run(run_id)
        if token:
            claimed.append((run_id, token))
    return claimed


def record_worker_pid(run_id: int, token: str, pid: int):
    PipelineRun.objects.filter(pk=run_id, worker_token=token).update(
        worker_pid=pid,
        worker_heartbeat_at=timezone.now(),
    )


def owns_pipeline_run(run_id: int, token: str) -> bool:
    if not token:
        return True
    return PipelineRun.objects.filter(pk=run_id, worker_token=token).exists()


def _owned_run(run_id: int, token: str) -> PipelineRun:
    qs = PipelineRun.objects.filter(pk=run_id)
    if token:
        qs = qs.filter(worker_token=token)
    run = qs.first()
    if run is None:
        raise PipelineLeaseLost(f"Worker no longer owns run #{run_id}")
    return run


def check_cancelled(run_id: int, token: str) -> PipelineRun:
    run = _owned_run(run_id, token)
    if run.cancel_requested_at is not None:
        raise PipelineCancelled(f"Cancellation requested for run #{run_id}")
    return run


def heartbeat(run_id: int, token: str, *, status=None, current_step=None) -> PipelineRun:
    run = _owned_run(run_id, token)
    update_fields = ["worker_heartbeat_at", "updated_at"]
    run.worker_heartbeat_at = timezone.now()
    if status is not None:
        run.status = status
        update_fields.append("status")
    if current_step is not None:
        run.stats_json = {**(run.stats_json or {}), "current_step": current_step}
        update_fields.append("stats_json")
    run.save(update_fields=update_fields)
    return run


def begin_stage(run_id: int, token: str, stage: str, label: str, status: str) -> bool:
    run = check_cancelled(run_id, token)
    state = dict(run.execution_state or {})
    completed = list(state.get("completed_stages") or [])
    if stage in completed:
        return False
    attempts = dict(state.get("stage_attempts") or {})
    attempts[stage] = attempts.get(stage, 0) + 1
    state.update({
        "version": 1,
        "current_stage": stage,
        "stage_status": "running",
        "stage_attempts": attempts,
        "completed_stages": completed,
        "stage_started_at": timezone.now().isoformat(),
        "stage_progress": {
            "processed": 0,
            "total": 0,
            "current_item": "",
            "current_url": "",
            "updated_at": timezone.now().isoformat(),
        },
    })
    run.execution_state = state
    run.stats_json = {**(run.stats_json or {}), "current_step": label}
    run.status = status
    run.worker_heartbeat_at = timezone.now()
    run.next_retry_at = None
    run.save(update_fields=[
        "execution_state", "stats_json", "status", "worker_heartbeat_at",
        "next_retry_at", "updated_at",
    ])
    return True


def update_stage_progress(
    run_id: int,
    token: str,
    stage: str,
    *,
    processed: int,
    total: int,
    current_item: str = "",
    current_url: str = "",
    **metrics,
) -> PipelineRun:
    run = check_cancelled(run_id, token)
    state = dict(run.execution_state or {})
    progress = {
        "processed": max(int(processed or 0), 0),
        "total": max(int(total or 0), 0),
        "current_item": str(current_item or "")[:500],
        "current_url": str(current_url or "")[:1000],
        "updated_at": timezone.now().isoformat(),
    }
    progress.update(metrics)
    state.update({
        "version": 1,
        "current_stage": stage,
        "stage_status": "running",
        "stage_progress": progress,
    })
    run.execution_state = state
    run.worker_heartbeat_at = timezone.now()
    run.save(update_fields=["execution_state", "worker_heartbeat_at", "updated_at"])
    return run


def complete_stage(run_id: int, token: str, stage: str):
    run = check_cancelled(run_id, token)
    state = dict(run.execution_state or {})
    completed = list(state.get("completed_stages") or [])
    if stage not in completed:
        completed.append(stage)
    progress = dict(state.get("stage_progress") or {})
    if progress.get("total"):
        progress["processed"] = progress["total"]
    progress["updated_at"] = timezone.now().isoformat()
    state.update({
        "current_stage": stage,
        "stage_status": "completed",
        "completed_stages": completed,
        "stage_completed_at": timezone.now().isoformat(),
        "stage_progress": progress,
    })
    run.execution_state = state
    run.worker_heartbeat_at = timezone.now()
    run.save(update_fields=["execution_state", "worker_heartbeat_at", "updated_at"])


def mark_retrying(run_id: int, token: str, exc: Exception) -> int | None:
    run = _owned_run(run_id, token)
    retry_count = run.retry_count + 1
    if retry_count > MAX_RETRIES:
        return None
    delay = RETRY_DELAYS_SECONDS[retry_count - 1]
    run.retry_count = retry_count
    run.next_retry_at = timezone.now() + timedelta(seconds=delay)
    run.status = PipelineRun.Status.RETRYING
    run.error_message = str(exc)[:2000]
    run.worker_heartbeat_at = timezone.now()
    run.stats_json = {
        **(run.stats_json or {}),
        "current_step": f"Retry {retry_count}/{MAX_RETRIES} in {delay}s",
    }
    run.save(update_fields=[
        "retry_count", "next_retry_at", "status", "error_message",
        "worker_heartbeat_at", "stats_json", "updated_at",
    ])
    return delay


def mark_failed(run_id: int, token: str, exc: Exception):
    run = _owned_run(run_id, token)
    state = dict(run.execution_state or {})
    state["stage_status"] = "failed"
    state["failed_at"] = timezone.now().isoformat()
    run.execution_state = state
    run.status = PipelineRun.Status.FAILED
    run.error_message = str(exc)[:2000]
    run.stats_json = {**(run.stats_json or {}), "current_step": f"FAILED: {exc}"}
    run.worker_heartbeat_at = timezone.now()
    run.worker_token = ""
    run.worker_pid = None
    run.next_retry_at = None
    run.save(update_fields=[
        "execution_state", "status", "error_message", "stats_json",
        "worker_heartbeat_at", "worker_token", "worker_pid", "next_retry_at", "updated_at",
    ])


def mark_cancelled(run_id: int, token: str):
    run = _owned_run(run_id, token)
    state = dict(run.execution_state or {})
    state.update({
        "stage_status": "cancelled",
        "cancelled_at": timezone.now().isoformat(),
    })
    run.execution_state = state
    run.status = PipelineRun.Status.CANCELLED
    run.stats_json = {**(run.stats_json or {}), "current_step": "Cancelled"}
    run.worker_heartbeat_at = timezone.now()
    run.worker_token = ""
    run.worker_pid = None
    run.next_retry_at = None
    run.save(update_fields=[
        "execution_state", "status", "stats_json", "worker_heartbeat_at",
        "worker_token", "worker_pid", "next_retry_at", "updated_at",
    ])


def mark_complete(run_id: int, token: str):
    run = _owned_run(run_id, token)
    state = dict(run.execution_state or {})
    state.update({
        "current_stage": "complete",
        "stage_status": "completed",
        "completed_at": timezone.now().isoformat(),
    })
    run.execution_state = state
    run.status = PipelineRun.Status.REVIEW
    run.stats_json = {**(run.stats_json or {}), "current_step": "Complete"}
    run.total_crawled_institutions = run.universities.count()
    run.total_programs_found = run.programs.count()
    run.error_message = ""
    run.worker_heartbeat_at = timezone.now()
    run.worker_token = ""
    run.worker_pid = None
    run.next_retry_at = None
    run.cancel_requested_at = None
    run.save(update_fields=[
        "execution_state", "status", "stats_json", "total_crawled_institutions",
        "total_programs_found", "error_message", "worker_heartbeat_at", "worker_token",
        "worker_pid", "next_retry_at", "cancel_requested_at", "updated_at",
    ])


def release_worker(run_id: int, token: str):
    if not token:
        return
    PipelineRun.objects.filter(pk=run_id, worker_token=token).update(
        worker_token="",
        worker_pid=None,
        next_retry_at=None,
    )


def is_recoverable_error(exc: Exception) -> bool:
    if isinstance(exc, OperationalError):
        message = str(exc).lower()
        return "locked" in message or "busy" in message
    return isinstance(exc, (
        TimeoutError,
        ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
    ))
