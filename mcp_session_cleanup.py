"""
MCP Session Cleanup - Background task for cleaning expired sessions.

Runs periodically to remove expired sessions from PostgreSQL, keeping the
database clean and preventing unbounded growth.

Enhanced version with multi-tier cleanup strategy for better session hygiene.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List

# Use structlog for consistent logging format
try:
    from src.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    # Fallback to standard logging for tests
    import logging
    logger = logging.getLogger(__name__)


def run_cleanup_once(session_store, current_time: Optional[datetime] = None) -> int:
    """
    Run session cleanup once.

    Args:
        session_store: PostgreSQLSessionStore instance
        current_time: Time to check against (default: now)

    Returns:
        Number of sessions deleted
    """
    try:
        deleted = session_store.cleanup_expired(current_time)

        if deleted > 0:
            logger.info(f"MCP session cleanup: deleted {deleted} expired sessions")
        else:
            logger.debug("MCP session cleanup: no expired sessions to delete")

        return deleted

    except Exception as e:
        logger.error(f"MCP session cleanup failed: {e}")
        return 0  # Return 0 on error


def run_immediate_cleanup(session_store) -> int:
    """
    Run immediate cleanup for very old expired sessions.
    
    This cleanup targets sessions that have been expired for more than 1 hour,
    ensuring they don't accumulate in the database.

    Args:
        session_store: PostgreSQLSessionStore instance

    Returns:
        Number of sessions deleted
    """
    try:
        # Clean up sessions expired more than 1 hour ago
        current_time = datetime.now(timezone.utc)
        cleanup_time = current_time - timedelta(hours=1)
        
        deleted = session_store.cleanup_expired(cleanup_time)

        if deleted > 0:
            logger.info(f"MCP immediate cleanup: deleted {deleted} very old expired sessions")
        
        return deleted

    except Exception as e:
        logger.error(f"MCP immediate cleanup failed: {e}")
        return 0


async def start_cleanup_scheduler(
    session_store,
    interval_seconds: int = 3600,  # Default: 1 hour
    aggressive_cleanup: bool = False
) -> None:
    """
    Start periodic session cleanup task with enhanced cleanup strategies.

    Runs cleanup every interval_seconds until cancelled.
    With aggressive_cleanup enabled, runs more frequent cleanup for better session hygiene.

    Args:
        session_store: PostgreSQLSessionStore instance
        interval_seconds: Base cleanup interval in seconds (default: 3600 = 1 hour)
        aggressive_cleanup: If True, run immediate cleanup every 10 minutes (default: False)

    Example:
        # Start cleanup task in background
        cleanup_task = asyncio.create_task(
            start_cleanup_scheduler(session_store, interval_seconds=3600)
        )

        # Start aggressive cleanup (10 min immediate + 1 hour regular)
        aggressive_task = asyncio.create_task(
            start_cleanup_scheduler(session_store, aggressive_cleanup=True)
        )

        # Later: Cancel on shutdown
        cleanup_task.cancel()
        await cleanup_task
    """
    if aggressive_cleanup:
        logger.info(f"MCP session cleanup scheduler started (aggressive mode: immediate=600s, regular=3600s)")
        # Run both immediate (10 min) and regular (1 hour) cleanup
        intervals = [600, 3600]  # 10 minutes, 1 hour
    else:
        logger.info(f"MCP session cleanup scheduler started (interval: {interval_seconds}s)")
        intervals = [interval_seconds]

    try:
        # Track last run times for each interval
        last_runs = {interval: 0.0 for interval in intervals}
        
        while True:
            current_time = asyncio.get_event_loop().time()
            
            # Run cleanup for each interval that's due
            for interval in sorted(intervals):  # Process in order
                if current_time - last_runs[interval] >= interval:
                    # Run appropriate cleanup based on interval
                    if interval <= 600 and aggressive_cleanup:
                        # Immediate cleanup for very old sessions
                        deleted = run_immediate_cleanup(session_store)
                    else:
                        # Regular cleanup
                        deleted = run_cleanup_once(session_store)
                    
                    last_runs[interval] = current_time
                    
                    if deleted > 0:
                        logger.debug(f"MCP cleanup completed for interval {interval}s: {deleted} sessions deleted")

            # Wait for next shortest interval
            next_wake = min(last_runs[interval] + interval for interval in intervals)
            sleep_time = max(0, next_wake - asyncio.get_event_loop().time())
            
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    except asyncio.CancelledError:
        logger.info("MCP session cleanup scheduler stopped")
        raise  # Re-raise to properly handle cancellation

    except Exception as e:
        logger.error(f"MCP session cleanup scheduler error: {e}")
        # Continue running despite errors
        await asyncio.sleep(min(intervals) if intervals else 60)


# Backward compatibility function
async def start_cleanup_scheduler_legacy(
    session_store,
    interval_seconds: int = 3600  # Default: 1 hour
) -> None:
    """
    Legacy compatibility function for existing code.
    
    This maintains the exact same interface as the original function.
    """
    return await start_cleanup_scheduler(session_store, interval_seconds, aggressive_cleanup=False)
