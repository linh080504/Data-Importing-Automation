"""Launch the unified ETL pipeline outside the Django web-server process."""

import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings


def launch_unified_worker(run_id: int, worker_token: str = "") -> int:
    """Start one independent management-command worker and return its PID.

    A daemon thread inside ``runserver`` dies whenever Django's autoreloader
    restarts the web process. The worker command owns the run instead, so the
    HTTP server can restart without leaving a run permanently marked crawling.
    """
    manage_py = Path(settings.BASE_DIR) / "manage.py"
    kwargs = {
        "cwd": str(settings.BASE_DIR),
        "close_fds": os.name != "nt",
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    command = [
        sys.executable, str(manage_py), "run_unified_pipeline", "--run-id", str(run_id),
    ]
    if worker_token:
        command.extend(["--worker-token", worker_token])
    process = subprocess.Popen(command, **kwargs)
    if worker_token:
        from .pipeline_execution import record_worker_pid

        record_worker_pid(run_id, worker_token, process.pid)
    return process.pid
