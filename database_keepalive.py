"""
Database Keep-Alive - Background task to prevent Neon database from sleeping.

Runs periodic lightweight queries to keep the Neon connection pool warm,
preventing the 10-15 second cold start delays that cause Custom Connector
to timeout and reconnect.

Strategy:
- Ping database every 5 minutes with lightweight query
- Log wake times to monitor effectiveness
- Handle errors gracefully (don't crash server)
- Use existing PostgreSQL adapter infrastructure
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

# Use structlog for consistent logging format
try:
    from src.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    # Fallback to standard logging for tests
    import logging
    logger = logging.getLogger(__name__)


async def ping_database_once(db_adapter) -> tuple[bool, float]:
    """
    Execute a lightweight query to keep database connection alive (ASYNC).

    Args:
        db_adapter: PostgreSQLAdapterAsync instance

    Returns:
        Tuple of (success: bool, elapsed_ms: float)
    """
    import time

    try:
        start_time = time.time()

        # Use async execute_query for lightweight ping
        result = await db_adapter.execute_query("SELECT 1 as ping")

        elapsed_ms = (time.time() - start_time) * 1000

        if elapsed_ms > 1000:  # Warn if query takes > 1 second
            logger.warning("slow_database_keepalive",
                         elapsed_ms=round(elapsed_ms, 2),
                         threshold_ms=1000)
        else:
            logger.debug("database_keepalive_success",
                       elapsed_ms=round(elapsed_ms, 2))

        return (True, elapsed_ms)

    except Exception as e:
        logger.error("database_keepalive_failed",
                    error=str(e),
                    error_type=type(e).__name__)
        return (False, 0.0)


async def start_keepalive_scheduler(
    db_adapter,
    interval_seconds: int = 300  # Default: 5 minutes
) -> None:
    """
    Start periodic database keep-alive task (ASYNC).

    Runs lightweight ping every interval_seconds until cancelled.

    Args:
        db_adapter: PostgreSQLAdapterAsync instance
        interval_seconds: Ping interval in seconds (default: 300 = 5 minutes)

    Example:
        # Start keep-alive task in background
        from postgres_adapter_async import PostgreSQLAdapterAsync

        adapter = PostgreSQLAdapterAsync()
        keepalive_task = asyncio.create_task(
            start_keepalive_scheduler(adapter, interval_seconds=300)
        )

        # Later: Cancel on shutdown
        keepalive_task.cancel()
        await keepalive_task
    """
    logger.info("database_keepalive_scheduler_started",
                interval_seconds=interval_seconds)

    try:
        while True:
            # Run ping (async)
            success, elapsed_ms = await ping_database_once(db_adapter)

            if success:
                logger.info("database_keepalive_ping",
                          elapsed_ms=round(elapsed_ms, 2),
                          next_ping_seconds=interval_seconds)

            # Wait for next interval
            await asyncio.sleep(interval_seconds)

    except asyncio.CancelledError:
        logger.info("database_keepalive_scheduler_stopped")
        raise  # Re-raise to properly handle cancellation

    except Exception as e:
        logger.error("database_keepalive_scheduler_error",
                    error=str(e),
                    error_type=type(e).__name__)
        # Continue running despite errors
        await asyncio.sleep(interval_seconds)
