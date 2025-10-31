"""Prometheus metrics collection for cloud-hosted MCP."""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from functools import wraps
import time
from typing import Callable

# Tool invocation metrics
tool_invocations = Counter(
    'dementia_tool_invocations_total',
    'Total tool invocations',
    ['tool', 'status']  # status: success | error
)

# Tool execution latency
tool_latency = Histogram(
    'dementia_tool_latency_seconds',
    'Tool execution latency in seconds',
    ['tool'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)

# Error rate
error_rate = Counter(
    'dementia_error_rate_total',
    'Error rate per tool',
    ['tool', 'error_type']
)

# Active connections
active_connections = Gauge(
    'dementia_active_connections',
    'Current active connections'
)

# Database connection pool metrics
db_pool_size = Gauge(
    'dementia_db_pool_size',
    'Database connection pool size'
)

db_pool_available = Gauge(
    'dementia_db_pool_available',
    'Available database connections in pool'
)

# Context lock metrics
contexts_locked = Counter(
    'dementia_contexts_locked_total',
    'Total contexts locked'
)

contexts_recalled = Counter(
    'dementia_contexts_recalled_total',
    'Total contexts recalled',
    ['hit']  # hit: true | false (cache hit/miss in future)
)

# Request size metrics
request_size_bytes = Histogram(
    'dementia_request_size_bytes',
    'HTTP request size in bytes',
    buckets=[100, 1000, 10000, 100000, 1000000]
)

response_size_bytes = Histogram(
    'dementia_response_size_bytes',
    'HTTP response size in bytes',
    buckets=[100, 1000, 10000, 100000, 1000000]
)


def track_tool_execution(tool_name: str):
    """
    Decorator to track tool execution metrics.

    Usage:
        @track_tool_execution("wake_up")
        async def wake_up():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                error_type = type(e).__name__
                error_rate.labels(tool=tool_name, error_type=error_type).inc()
                raise
            finally:
                latency = time.time() - start_time
                tool_invocations.labels(tool=tool_name, status=status).inc()
                tool_latency.labels(tool=tool_name).observe(latency)

        return wrapper
    return decorator


def get_metrics_text() -> tuple[str, str]:
    """
    Get Prometheus metrics in text format.

    Returns:
        Tuple of (metrics_text, content_type)
    """
    return generate_latest(), CONTENT_TYPE_LATEST


# Example usage in server_hosted.py:
#
# from src.metrics import (
#     track_tool_execution,
#     active_connections,
#     contexts_locked,
#     get_metrics_text
# )
#
# @app.on_event("startup")
# async def startup():
#     active_connections.inc()
#
# @app.on_event("shutdown")
# async def shutdown():
#     active_connections.dec()
#
# @app.get("/metrics")
# async def metrics():
#     data, content_type = get_metrics_text()
#     return Response(content=data, media_type=content_type)
#
# @app.post("/mcp/execute")
# @track_tool_execution("custom_tool")
# async def execute_tool(...):
#     ...
