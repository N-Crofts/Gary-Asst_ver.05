import os
import time
import json
import logging
from contextlib import contextmanager
from typing import Dict, Any, Optional
from datetime import datetime

# Import sentry_sdk at module level for testing
try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None

logger = logging.getLogger(__name__)


class TimingContext:
    """Context manager for timing operations."""

    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.start_time: Optional[float] = None
        self.duration_ms: Optional[float] = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            self.duration_ms = (time.time() - self.start_time) * 1000

    def get_duration_ms(self) -> Optional[float]:
        """Get duration in milliseconds."""
        return self.duration_ms


@contextmanager
def timing(operation_name: str):
    """Context manager for timing operations."""
    context = TimingContext(operation_name)
    with context:
        yield context


def log_event(
    action: str,
    driver: str,
    source: str,
    subject: str,
    recipients_count: int,
    message_id: Optional[str] = None,
    duration_ms: Optional[float] = None,
    **kwargs
) -> None:
    """
    Log a structured event with required fields.

    Args:
        action: The action performed (e.g., 'sent', 'rendered', 'failed')
        driver: The email driver used (e.g., 'console', 'smtp', 'sendgrid')
        source: The data source (e.g., 'sample', 'live')
        subject: The email subject
        recipients_count: Number of recipients
        message_id: Optional message ID from email service
        duration_ms: Optional duration in milliseconds
        **kwargs: Additional fields to include in the log
    """
    # Sanitize subject to avoid logging secrets
    sanitized_subject = _sanitize_subject(subject)

    # Build structured log entry
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "action": action,
        "driver": driver,
        "source": source,
        "subject": sanitized_subject,
        "recipients_count": recipients_count,
    }

    # Add optional fields if present
    if message_id is not None:
        log_entry["message_id"] = message_id

    if duration_ms is not None:
        log_entry["duration_ms"] = round(duration_ms, 2)

    # Add any additional fields
    log_entry.update(kwargs)

    # Log as JSON string for structured logging
    logger.info(json.dumps(log_entry, separators=(',', ':')))


def _sanitize_subject(subject: str) -> str:
    """
    Sanitize subject to avoid logging sensitive information.

    Args:
        subject: The original subject

    Returns:
        Sanitized subject safe for logging
    """
    # Remove common sensitive patterns
    sensitive_patterns = [
        "password",
        "secret",
        "key",
        "token",
        "auth",
        "credential",
    ]

    sanitized = subject.lower()
    for pattern in sensitive_patterns:
        if pattern in sanitized:
            return "[REDACTED]"

    # Truncate very long subjects
    if len(subject) > 100:
        return subject[:97] + "..."

    return subject


def init_sentry() -> bool:
    """
    Initialize Sentry if enabled and DSN is provided.

    Returns:
        True if Sentry was initialized, False otherwise
    """
    if not os.getenv("OBS_ENABLED", "false").lower() == "true":
        return False

    sentry_dsn = os.getenv("SENTRY_DSN")
    if not sentry_dsn:
        logger.info("Sentry DSN not provided, skipping Sentry initialization")
        return False

    try:
        if sentry_sdk is None:
            raise ImportError("sentry_sdk not available")

        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        # Configure Sentry
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[
                FastApiIntegration(auto_enabling_instrumentations=True),
                LoggingIntegration(
                    level=logging.INFO,
                    event_level=logging.ERROR
                ),
            ],
            traces_sample_rate=0.1,  # Sample 10% of transactions
            environment=os.getenv("ENVIRONMENT", "development"),
        )

        logger.info("Sentry initialized successfully")
        return True

    except ImportError:
        logger.warning("Sentry SDK not installed, skipping Sentry initialization")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")
        return False


def log_error(error: Exception, context: Dict[str, Any] = None) -> None:
    """
    Log an error with optional context.

    Args:
        error: The exception to log
        context: Optional context dictionary
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": "ERROR",
        "error": str(error),
        "error_type": type(error).__name__,
    }

    if context:
        log_entry.update(context)

    logger.error(json.dumps(log_entry, separators=(',', ':')))


def log_warning(message: str, context: Dict[str, Any] = None) -> None:
    """
    Log a warning with optional context.

    Args:
        message: The warning message
        context: Optional context dictionary
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": "WARNING",
        "message": message,
    }

    if context:
        log_entry.update(context)

    logger.warning(json.dumps(log_entry, separators=(',', ':')))


def log_info(message: str, context: Dict[str, Any] = None) -> None:
    """
    Log an info message with optional context.

    Args:
        message: The info message
        context: Optional context dictionary
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": "INFO",
        "message": message,
    }

    if context:
        log_entry.update(context)

    logger.info(json.dumps(log_entry, separators=(',', ':')))
