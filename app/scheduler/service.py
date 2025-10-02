import os
import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo

from app.routes.digest import _build_digest_context, _get_default_recipients, _get_sender, _default_subject
from app.services.emailer import select_emailer_from_env
from app.observability.logger import log_event, timing, log_error
from app.routes.health import update_last_run
from app.channels.slack_client import post_digest_to_slack

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Cron-like scheduler service for automated digest sending.
    """

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._cron_expression = self._parse_cron_expression()
        self._timezone = self._get_timezone()
        self._last_run: Optional[datetime] = None
        self._next_run: Optional[datetime] = None
        self._update_next_run()

    def _parse_cron_expression(self) -> Dict[str, Any]:
        """
        Parse cron expression from environment variable.
        Default: "0 8 * * 1-5" (8 AM ET, Monday-Friday)
        """
        cron_str = os.getenv("SCHEDULER_CRON", "0 8 * * 1-5")

        # Parse simple cron format: "minute hour * * day_of_week"
        parts = cron_str.split()
        if len(parts) != 5:
            logger.warning(f"Invalid cron expression: {cron_str}, using default")
            return {"minute": 0, "hour": 8, "day_of_week": "1-5"}

        try:
            return {
                "minute": int(parts[0]) if parts[0] != "*" else None,
                "hour": int(parts[1]) if parts[1] != "*" else None,
                "day_of_week": parts[4] if parts[4] != "*" else None
            }
        except ValueError:
            logger.warning(f"Invalid cron expression: {cron_str}, using default")
            return {"minute": 0, "hour": 8, "day_of_week": "1-5"}

    def _get_timezone(self) -> str:
        """Get timezone from environment variable."""
        return os.getenv("SCHEDULER_TIMEZONE", "America/New_York")

    def _is_weekday(self, dt: datetime) -> bool:
        """Check if datetime is a weekday (Monday=1, Sunday=7)."""
        return dt.weekday() < 5  # Monday=0, Friday=4

    def _is_scheduled_time(self, dt: datetime) -> bool:
        """Check if datetime matches the scheduled time."""
        cron = self._cron_expression

        # Check minute
        if cron["minute"] is not None and dt.minute != cron["minute"]:
            return False

        # Check hour
        if cron["hour"] is not None and dt.hour != cron["hour"]:
            return False

        # Check day of week
        if cron["day_of_week"] is not None:
            if "-" in cron["day_of_week"]:
                # Range like "1-5" (Monday-Friday)
                start, end = map(int, cron["day_of_week"].split("-"))
                weekday = dt.weekday() + 1  # Convert to 1-7 format
                if not (start <= weekday <= end):
                    return False
            else:
                # Single day like "1" (Monday)
                weekday = dt.weekday() + 1  # Convert to 1-7 format
                if weekday != int(cron["day_of_week"]):
                    return False

        return True

    def _update_next_run(self):
        """Calculate the next scheduled run time."""
        now = datetime.now(ZoneInfo(self._timezone))

        # Start from current time
        next_run = now.replace(second=0, microsecond=0)

        # If we have specific minute/hour, set them
        if self._cron_expression["minute"] is not None:
            next_run = next_run.replace(minute=self._cron_expression["minute"])
        if self._cron_expression["hour"] is not None:
            next_run = next_run.replace(hour=self._cron_expression["hour"])

        # If the time has already passed today, move to next day
        if next_run <= now:
            next_run += timedelta(days=1)

        # Find next valid day
        max_days = 7  # Prevent infinite loop
        for _ in range(max_days):
            if self._is_scheduled_time(next_run):
                break
            next_run += timedelta(days=1)

        self._next_run = next_run
        logger.info(f"Next scheduled run: {self._next_run} ({self._timezone})")

    async def _send_digest(self):
        """Send the daily digest."""
        try:
            logger.info("Starting scheduled digest send")

            # Build digest context
            context = _build_digest_context()

            # Get recipients and sender
            recipients = _get_default_recipients()
            sender = _get_sender()
            subject = _default_subject()

            if not recipients:
                logger.warning("No recipients configured for scheduled digest")
                return

            # Send email
            emailer = select_emailer_from_env()
            driver_used = getattr(emailer, 'driver', 'unknown')

            # Render HTML and plaintext
            from app.rendering.digest_renderer import render_digest_html
            from app.rendering.plaintext import render_plaintext

            html = render_digest_html(context)
            plaintext = render_plaintext(context)

            # Time the email sending operation
            with timing("scheduled_digest_send") as timer:
                # Send email
                message_id = emailer.send(
                    subject=subject,
                    html=html,
                    recipients=recipients,
                    sender=sender,
                    plaintext=plaintext
                )

            # Log the event with structured data
            log_event(
                action="sent",
                driver=driver_used,
                source="scheduled",
                subject=subject,
                recipients_count=len(recipients),
                message_id=message_id,
                duration_ms=timer.get_duration_ms(),
            )

            # Update last run information for health endpoint
            update_last_run(
                action="sent",
                driver=driver_used,
                source="scheduled",
                subject=subject,
                recipients_count=len(recipients),
                message_id=message_id,
                duration_ms=timer.get_duration_ms(),
                success=True,
            )

            self._last_run = datetime.now(ZoneInfo(self._timezone))
            logger.info(f"Scheduled digest sent successfully. Message ID: {message_id}")

            # Post to Slack if enabled
            try:
                meeting_count = len(context.get("meetings", []))
                slack_success = await post_digest_to_slack(
                    subject=subject,
                    meeting_count=meeting_count,
                    base_url=os.getenv("BASE_URL", "http://localhost:8000")
                )
                if slack_success:
                    logger.info("Slack notification posted successfully")
                else:
                    logger.info("Slack notification skipped (not enabled or failed)")
            except Exception as slack_error:
                logger.warning(f"Slack notification failed: {slack_error}")
                # Don't fail the entire digest send if Slack fails

        except Exception as e:
            # Log error with structured data
            log_error(e, {
                "action": "scheduled_digest_failed",
                "source": "scheduled",
                "error_type": type(e).__name__,
            })

            # Update last run information with error
            update_last_run(
                action="failed",
                driver="unknown",
                source="scheduled",
                subject="Scheduled Digest",
                recipients_count=0,
                success=False,
                error=str(e),
            )

            logger.error(f"Failed to send scheduled digest: {e}")
            raise

    async def _scheduler_loop(self):
        """Main scheduler loop."""
        logger.info("Scheduler started")

        while self._running:
            try:
                now = datetime.now(ZoneInfo(self._timezone))

                # Check if it's time to run
                if self._next_run and now >= self._next_run:
                    await self._send_digest()
                    self._update_next_run()

                # Sleep for 1 minute before checking again
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(60)  # Continue running despite errors

        logger.info("Scheduler stopped")

    async def start(self):
        """Start the scheduler."""
        if self._running:
            logger.warning("Scheduler is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Scheduler started")

    async def stop(self):
        """Stop the scheduler."""
        if not self._running:
            logger.warning("Scheduler is not running")
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status."""
        return {
            "running": self._running,
            "cron_expression": os.getenv("SCHEDULER_CRON", "0 8 * * 1-5"),
            "timezone": self._timezone,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "next_run": self._next_run.isoformat() if self._next_run else None,
            "enabled": os.getenv("RUN_SCHEDULER", "0") == "1"
        }

    def is_enabled(self) -> bool:
        """Check if scheduler is enabled via environment variable."""
        return os.getenv("RUN_SCHEDULER", "0") == "1"


# Global scheduler instance
_scheduler: Optional[SchedulerService] = None


def get_scheduler() -> SchedulerService:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = SchedulerService()
    return _scheduler


async def start_scheduler():
    """Start the global scheduler if enabled."""
    scheduler = get_scheduler()
    if scheduler.is_enabled():
        await scheduler.start()
    else:
        logger.info("Scheduler disabled (RUN_SCHEDULER=0)")


async def stop_scheduler():
    """Stop the global scheduler."""
    scheduler = get_scheduler()
    await scheduler.stop()
