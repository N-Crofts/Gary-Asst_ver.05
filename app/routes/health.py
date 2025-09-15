import os
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.observability.logger import init_sentry

router = APIRouter()

# Global state for last run tracking
_last_run: Optional[Dict[str, Any]] = None


def update_last_run(
    action: str,
    driver: str,
    source: str,
    subject: str,
    recipients_count: int,
    message_id: Optional[str] = None,
    duration_ms: Optional[float] = None,
    success: bool = True,
    error: Optional[str] = None
) -> None:
    """
    Update the last run information.

    Args:
        action: The action performed
        driver: The email driver used
        source: The data source
        subject: The email subject
        recipients_count: Number of recipients
        message_id: Optional message ID
        duration_ms: Optional duration in milliseconds
        success: Whether the operation was successful
        error: Optional error message
    """
    global _last_run

    _last_run = {
        "time": datetime.utcnow().isoformat() + "Z",
        "action": action,
        "driver": driver,
        "source": source,
        "subject": subject,
        "recipients_count": recipients_count,
        "success": success,
    }

    if message_id is not None:
        _last_run["message_id"] = message_id

    if duration_ms is not None:
        _last_run["duration_ms"] = round(duration_ms, 2)

    if error is not None:
        _last_run["error"] = error


def get_last_run() -> Optional[Dict[str, Any]]:
    """Get the last run information."""
    return _last_run


@router.get("/healthz")
async def health_check() -> JSONResponse:
    """
    Enhanced health check endpoint with last run information.

    Returns:
        JSON response with status and last run metadata
    """
    response = {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    # Add last run information if available
    last_run = get_last_run()
    if last_run:
        response["last_run"] = last_run

    # Add observability status
    obs_enabled = os.getenv("OBS_ENABLED", "false").lower() == "true"
    response["observability"] = {
        "enabled": obs_enabled,
        "sentry_configured": bool(os.getenv("SENTRY_DSN")),
    }

    return JSONResponse(status_code=200, content=response)


@router.get("/healthz/ready")
async def readiness_check() -> JSONResponse:
    """
    Readiness check endpoint for Kubernetes/container orchestration.

    Returns:
        JSON response indicating if the service is ready to accept traffic
    """
    # Basic readiness checks
    checks = {
        "database": "ok",  # Placeholder for future database checks
        "email_service": "ok",  # Placeholder for future email service checks
        "scheduler": "ok",  # Placeholder for future scheduler checks
    }

    # Check if any critical services are down
    all_healthy = all(status == "ok" for status in checks.values())

    response = {
        "status": "ready" if all_healthy else "not_ready",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "checks": checks,
    }

    status_code = 200 if all_healthy else 503
    return JSONResponse(status_code=status_code, content=response)


@router.get("/healthz/live")
async def liveness_check() -> JSONResponse:
    """
    Liveness check endpoint for Kubernetes/container orchestration.

    Returns:
        JSON response indicating if the service is alive
    """
    response = {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "uptime": "running",  # Placeholder for future uptime tracking
    }

    return JSONResponse(status_code=200, content=response)


# Initialize Sentry on module import if enabled
init_sentry()
