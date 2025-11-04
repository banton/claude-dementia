"""
MCP Session Cleanup - Background task for cleaning expired sessions.

Runs periodically to remove expired sessions from PostgreSQL, keeping the
database clean and preventing unbounded growth.

TDD Phase: GREEN - Minimal implementation to make tests pass.
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


def run_cleanup_once(session_store) -> int:
    """
    Run session cleanup once.

    Args:
        session_store: PostgreSQLSessionStore instance

    Returns:
        Number of sessions deleted
    """
    try:
        deleted = session_store.cleanup_expired()

        if deleted > 0:
            logger.info(f"MCP session cleanup: deleted {deleted} expired sessions")
        else:
            logger.debug("MCP session cleanup: no expired sessions to delete")

        return deleted

    except Exception as e:
        logger.error(f"MCP session cleanup failed: {e}")
        return 0  # Return 0 on error


async def start_cleanup_scheduler(
    session_store,
    interval_seconds: int = 3600  # Default: 1 hour
) -> None:
    """
    Start periodic session cleanup task.

    Runs cleanup every interval_seconds until cancelled.

    Args:
        session_store: PostgreSQLSessionStore instance
        interval_seconds: Cleanup interval in seconds (default: 3600 = 1 hour)

    Example:
        # Start cleanup task in background
        cleanup_task = asyncio.create_task(
            start_cleanup_scheduler(session_store, interval_seconds=3600)
        )

        # Later: Cancel on shutdown
        cleanup_task.cancel()
        await cleanup_task
    """
    logger.info(f"MCP session cleanup scheduler started (interval: {interval_seconds}s)")

    try:
        while True:
            # Run cleanup
            deleted = run_cleanup_once(session_store)

            # Wait for next interval
            await asyncio.sleep(interval_seconds)

    except asyncio.CancelledError:
        logger.info("MCP session cleanup scheduler stopped")
        raise  # Re-raise to properly handle cancellation

    except Exception as e:
        logger.error(f"MCP session cleanup scheduler error: {e}")
        # Continue running despite errors
        await asyncio.sleep(interval_seconds)
