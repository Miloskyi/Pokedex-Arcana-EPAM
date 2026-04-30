"""Structured JSON logging via structlog with a slow-query warning hook."""

import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for JSON output with timestamp and log level.

    Call once at application startup.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure the standard-library root logger
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.ExceptionRenderer(),
            structlog.dev.ConsoleRenderer(),   # human-readable in dev; swap for JSONRenderer in prod
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Return a structlog bound logger for *name*."""
    return structlog.get_logger(name)


def log_slow_query(
    query_id: str,
    total_latency_ms: int,
    slowest_agent: str,
) -> None:
    """Emit a WARN log when *total_latency_ms* exceeds 10 000 ms."""
    if total_latency_ms > 10_000:
        logger = get_logger(__name__)
        logger.warning(
            "slow_query_detected",
            query_id=query_id,
            total_latency_ms=total_latency_ms,
            slowest_agent=slowest_agent,
        )
