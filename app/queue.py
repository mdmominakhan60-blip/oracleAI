"""Celery application instance — leaf module for queue configuration."""
from __future__ import annotations

from celery import Celery

from .config import settings

celery_app = Celery(
    "oracle",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.tasks"],
)

celery_app.conf.update(
    task_default_queue="llm",
    task_default_exchange="oracle",
    task_default_routing_key="llm",
    task_routes={
        "oracle.llm.chat": {"queue": "llm", "routing_key": "llm"},
        "oracle.llm.forecast": {"queue": "llm", "routing_key": "llm"},
        "oracle.maintenance": {"queue": "maintenance", "routing_key": "maintenance"},
    },
    beat_schedule={
        "oracle-maintenance-hourly": {
            "task": "oracle.maintenance",
            "schedule": 3600.0,
            "options": {"queue": "maintenance"},
        },
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=86400,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=settings.celery_worker_prefetch,
    task_time_limit=settings.celery_task_time_limit,
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    broker_transport_options={
        "visibility_timeout": settings.celery_visibility_timeout,
        "socket_timeout": 10,
        "socket_connect_timeout": 10,
        "retry_on_timeout": True,
    },
    result_backend_transport_options={
        "retry_policy": {"timeout": 5.0},
    },
)
