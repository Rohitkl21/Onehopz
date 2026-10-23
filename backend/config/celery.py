"""Celery application configuration for OneHopz."""

import os
from typing import Any

from celery import Celery

# Set default Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("onehopz")

# Read configuration from Django settings, using the CELERY_ namespace
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from installed apps
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)  # type: ignore[untyped-decorator]
def debug_task(self: Any) -> None:
    """Minimal diagnostic task for verifying broker connectivity."""
    print(f"OneHopz Celery Debug Task: Request: {self.request!r}")
