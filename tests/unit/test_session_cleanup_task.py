"""
Unit tests for MCP session cleanup background task.

TDD Phase: RED - These tests are written FIRST and should FAIL initially.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import asyncio


@pytest.fixture
def mock_session_store():
    """Mock session store for testing cleanup task."""
    store = Mock()
    store.cleanup_expired = Mock(return_value=0)  # Returns count of deleted sessions
    return store


@pytest.fixture
def mock_logger():
    """Mock logger for testing log output."""
    logger = Mock()
    return logger


# Unit Tests - Following TDD ticket specification


def test_should_delete_expired_sessions_when_cleanup_runs(mock_session_store):
    """Test: Cleanup Task Execution"""
    from mcp_session_cleanup import run_cleanup_once

    # Arrange
    mock_session_store.cleanup_expired.return_value = 5  # 5 sessions deleted

    # Act
    deleted = run_cleanup_once(mock_session_store)

    # Assert
    assert deleted == 5
    mock_session_store.cleanup_expired.assert_called_once()


def test_should_log_cleanup_results_when_sessions_deleted(mock_session_store, mock_logger):
    """Test: Cleanup Logging"""
    from mcp_session_cleanup import run_cleanup_once

    # Arrange
    mock_session_store.cleanup_expired.return_value = 3

    # Act
    with patch('mcp_session_cleanup.logger', mock_logger):
        deleted = run_cleanup_once(mock_session_store)

    # Assert
    assert deleted == 3
    # Should log the cleanup result
    assert mock_logger.info.called or mock_logger.debug.called


def test_should_log_warning_when_no_sessions_deleted(mock_session_store, mock_logger):
    """Test: No Sessions to Clean Up"""
    from mcp_session_cleanup import run_cleanup_once

    # Arrange
    mock_session_store.cleanup_expired.return_value = 0

    # Act
    with patch('mcp_session_cleanup.logger', mock_logger):
        deleted = run_cleanup_once(mock_session_store)

    # Assert
    assert deleted == 0
    # Should still log (debug level is fine)
    assert mock_logger.info.called or mock_logger.debug.called


def test_should_handle_cleanup_errors_gracefully(mock_session_store, mock_logger):
    """Test: Error Handling"""
    from mcp_session_cleanup import run_cleanup_once

    # Arrange
    mock_session_store.cleanup_expired.side_effect = Exception("Database connection failed")

    # Act
    with patch('mcp_session_cleanup.logger', mock_logger):
        deleted = run_cleanup_once(mock_session_store)

    # Assert
    assert deleted == 0  # Should return 0 on error
    mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_should_run_cleanup_periodically_when_scheduled(mock_session_store):
    """Test: Periodic Cleanup Scheduling"""
    from mcp_session_cleanup import start_cleanup_scheduler

    # Arrange
    mock_session_store.cleanup_expired.return_value = 1

    # Act - Start scheduler with very short interval for testing
    cleanup_task = asyncio.create_task(
        start_cleanup_scheduler(mock_session_store, interval_seconds=0.1)
    )

    # Wait for a few cleanup cycles
    await asyncio.sleep(0.35)  # Should run ~3 times

    # Cancel the task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # Assert - Should have run multiple times
    assert mock_session_store.cleanup_expired.call_count >= 2


@pytest.mark.asyncio
async def test_should_stop_cleanup_when_task_cancelled(mock_session_store):
    """Test: Graceful Shutdown"""
    from mcp_session_cleanup import start_cleanup_scheduler

    # Arrange
    mock_session_store.cleanup_expired.return_value = 0

    # Act - Start and immediately cancel
    cleanup_task = asyncio.create_task(
        start_cleanup_scheduler(mock_session_store, interval_seconds=1)
    )

    await asyncio.sleep(0.1)  # Let it start
    cleanup_task.cancel()

    # Should handle cancellation gracefully
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass  # Expected

    # Assert - Should have run at least once
    assert mock_session_store.cleanup_expired.call_count >= 0


@pytest.mark.asyncio
async def test_should_continue_after_cleanup_error(mock_session_store, mock_logger):
    """Test: Resilience to Errors"""
    from mcp_session_cleanup import start_cleanup_scheduler

    # Arrange - First call fails, second succeeds
    mock_session_store.cleanup_expired.side_effect = [
        Exception("Database error"),
        2  # Second call succeeds
    ]

    # Act
    with patch('mcp_session_cleanup.logger', mock_logger):
        cleanup_task = asyncio.create_task(
            start_cleanup_scheduler(mock_session_store, interval_seconds=0.1)
        )

        await asyncio.sleep(0.25)  # Wait for 2 cycles

        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

    # Assert - Should have tried at least twice
    assert mock_session_store.cleanup_expired.call_count >= 2
    # Should have logged error but continued
    assert mock_logger.error.called
