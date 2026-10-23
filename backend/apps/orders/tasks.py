"""Celery asynchronous tasks for order reservation lifecycle management."""

import logging

from celery import shared_task

from .services import sweep_expired_order_reservations

logger = logging.getLogger(__name__)


@shared_task(name="apps.orders.tasks.sweep_expired_orders_task")  # type: ignore[untyped-decorator]
def sweep_expired_orders_task(batch_size: int = 200) -> int:
    """
    Background job to sweep and reclaim expired pending order reservations.
    """
    try:
        count = sweep_expired_order_reservations(batch_size=batch_size)
        if count > 0:
            logger.info("Swept and reclaimed %d expired order reservations.", count)
        return count
    except Exception as exc:
        logger.exception("Error executing expired order sweep: %s", exc)
        raise
