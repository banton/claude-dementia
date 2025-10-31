"""Structured logging configuration for cloud-hosted Dementia MCP."""

import sys
import structlog
import logging
from typing import Any, Dict
from datetime import datetime, timezone

def add_correlation_id(logger: Any, method_name: str, event_dict: Dict) -> Dict:
    """Add correlation_id to log context if present."""
    # Check thread-local storage for correlation_id (set by middleware)
    import contextvars
    correlation_id_var = contextvars.ContextVar('correlation_id', default=None)
    correlation_id = correlation_id_var.get()
    if correlation_id:
        event_dict['correlation_id'] = correlation_id
    return event_dict

def add_timestamp(logger: Any, method_name: str, event_dict: Dict) -> Dict:
    """Add ISO 8601 timestamp to log event."""
    event_dict['timestamp'] = datetime.now(timezone.utc).isoformat()
    return event_dict

def configure_logging(environment: str = "production", log_level: str = "INFO"):
    """
    Configure structured logging for cloud deployment.

    Args:
        environment: "production" | "development" | "staging"
        log_level: "DEBUG" | "INFO" | "WARNING" | "ERROR"
    """
    # Standard library logging configuration
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper())
    )

    # Structlog configuration
    processors = [
        structlog.stdlib.filter_by_level,
        add_timestamp,
        add_correlation_id,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if environment == "development":
        # Human-readable colored output for local development
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        # JSON output for cloud logging aggregation
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

def get_logger(name: str = None):
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Structured logger with bind() method for context
    """
    return structlog.get_logger(name)

# Example usage:
# logger = get_logger(__name__)
# logger.info("tool_executed", tool="wake_up", latency_ms=45, success=True)
# Output (production): {"timestamp":"2025-01-30T12:34:56.789Z","level":"info","event":"tool_executed","tool":"wake_up","latency_ms":45,"success":true}
