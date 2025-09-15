import os
import asyncio
from datetime import datetime, time, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.scheduler.service import SchedulerService, get_scheduler, start_scheduler, stop_scheduler
from app.main import app


class TestSchedulerService:
    """Test the SchedulerService class."""

    def test_parse_cron_expression_default(self):
        """Test parsing default cron expression."""
        with patch.dict(os.environ, {}, clear=True):
            scheduler = SchedulerService()
            cron = scheduler._parse_cron_expression()
            assert cron == {"minute": 0, "hour": 8, "day_of_week": "1-5"}

    def test_parse_cron_expression_custom(self):
        """Test parsing custom cron expression."""
        with patch.dict(os.environ, {"SCHEDULER_CRON": "30 9 * * 1-5"}):
            scheduler = SchedulerService()
            cron = scheduler._parse_cron_expression()
            assert cron == {"minute": 30, "hour": 9, "day_of_week": "1-5"}

    def test_parse_cron_expression_invalid(self):
        """Test parsing invalid cron expression falls back to default."""
        with patch.dict(os.environ, {"SCHEDULER_CRON": "invalid"}):
            scheduler = SchedulerService()
            cron = scheduler._parse_cron_expression()
            assert cron == {"minute": 0, "hour": 8, "day_of_week": "1-5"}

    def test_get_timezone_default(self):
        """Test default timezone."""
        with patch.dict(os.environ, {}, clear=True):
            scheduler = SchedulerService()
            assert scheduler._get_timezone() == "America/New_York"

    def test_get_timezone_custom(self):
        """Test custom timezone."""
        with patch.dict(os.environ, {"SCHEDULER_TIMEZONE": "Europe/London"}):
            scheduler = SchedulerService()
            assert scheduler._get_timezone() == "Europe/London"

    def test_is_weekday(self):
        """Test weekday detection."""
        scheduler = SchedulerService()

        # Monday
        monday = datetime(2024, 1, 1, 10, 0)  # Monday
        assert scheduler._is_weekday(monday) is True

        # Friday
        friday = datetime(2024, 1, 5, 10, 0)  # Friday
        assert scheduler._is_weekday(friday) is True

        # Saturday
        saturday = datetime(2024, 1, 6, 10, 0)  # Saturday
        assert scheduler._is_weekday(saturday) is False

        # Sunday
        sunday = datetime(2024, 1, 7, 10, 0)  # Sunday
        assert scheduler._is_weekday(sunday) is False

    def test_is_scheduled_time_exact_match(self):
        """Test exact time matching."""
        with patch.dict(os.environ, {"SCHEDULER_CRON": "30 9 * * 1-5"}):
            scheduler = SchedulerService()

            # Monday 9:30 AM
            monday_930 = datetime(2024, 1, 1, 9, 30)  # Monday 9:30 AM
            assert scheduler._is_scheduled_time(monday_930) is True

            # Monday 9:31 AM (wrong minute)
            monday_931 = datetime(2024, 1, 1, 9, 31)  # Monday 9:31 AM
            assert scheduler._is_scheduled_time(monday_931) is False

            # Monday 10:30 AM (wrong hour)
            monday_1030 = datetime(2024, 1, 1, 10, 30)  # Monday 10:30 AM
            assert scheduler._is_scheduled_time(monday_1030) is False

            # Saturday 9:30 AM (wrong day)
            saturday_930 = datetime(2024, 1, 6, 9, 30)  # Saturday 9:30 AM
            assert scheduler._is_scheduled_time(saturday_930) is False

    def test_is_scheduled_time_wildcards(self):
        """Test wildcard matching."""
        with patch.dict(os.environ, {"SCHEDULER_CRON": "* * * * 1-5"}):
            scheduler = SchedulerService()

            # Any time on weekday should match
            monday_any = datetime(2024, 1, 1, 14, 23)  # Monday 2:23 PM
            assert scheduler._is_scheduled_time(monday_any) is True

            # Weekend should not match
            saturday_any = datetime(2024, 1, 6, 14, 23)  # Saturday 2:23 PM
            assert scheduler._is_scheduled_time(saturday_any) is False

    def test_is_scheduled_time_single_day(self):
        """Test single day matching."""
        with patch.dict(os.environ, {"SCHEDULER_CRON": "0 8 * * 1"}):
            scheduler = SchedulerService()

            # Monday 8:00 AM
            monday_8am = datetime(2024, 1, 1, 8, 0)  # Monday 8:00 AM
            assert scheduler._is_scheduled_time(monday_8am) is True

            # Tuesday 8:00 AM (wrong day)
            tuesday_8am = datetime(2024, 1, 2, 8, 0)  # Tuesday 8:00 AM
            assert scheduler._is_scheduled_time(tuesday_8am) is False

    def test_update_next_run(self):
        """Test next run calculation."""
        with patch.dict(os.environ, {"SCHEDULER_CRON": "0 8 * * 1-5", "SCHEDULER_TIMEZONE": "America/New_York"}):
            scheduler = SchedulerService()

            # Mock current time to Monday 7:00 AM
            with patch('app.scheduler.service.datetime') as mock_datetime:
                mock_now = datetime(2024, 1, 1, 7, 0, tzinfo=ZoneInfo("America/New_York"))
                mock_datetime.now.return_value = mock_now

                scheduler._update_next_run()

                # Next run should be Monday 8:00 AM
                expected = datetime(2024, 1, 1, 8, 0, tzinfo=ZoneInfo("America/New_York"))
                assert scheduler._next_run == expected

    def test_get_status(self):
        """Test status retrieval."""
        with patch.dict(os.environ, {"SCHEDULER_CRON": "0 8 * * 1-5", "SCHEDULER_TIMEZONE": "America/New_York", "RUN_SCHEDULER": "1"}):
            scheduler = SchedulerService()
            status = scheduler.get_status()

            assert status["running"] is False
            assert status["cron_expression"] == "0 8 * * 1-5"
            assert status["timezone"] == "America/New_York"
            assert status["last_run"] is None
            assert status["next_run"] is not None
            assert status["enabled"] is True

    def test_is_enabled(self):
        """Test enabled status check."""
        with patch.dict(os.environ, {"RUN_SCHEDULER": "1"}):
            scheduler = SchedulerService()
            assert scheduler.is_enabled() is True

        with patch.dict(os.environ, {"RUN_SCHEDULER": "0"}):
            scheduler = SchedulerService()
            assert scheduler.is_enabled() is False


class TestSchedulerIntegration:
    """Test scheduler integration with FastAPI."""

    def test_get_scheduler_status_endpoint(self):
        """Test GET /scheduler/status endpoint."""
        client = TestClient(app)

        with patch.dict(os.environ, {"SCHEDULER_CRON": "0 8 * * 1-5", "SCHEDULER_TIMEZONE": "America/New_York", "RUN_SCHEDULER": "1"}):
            response = client.get("/scheduler/status")

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert "scheduler" in data
            assert data["scheduler"]["cron_expression"] == "0 8 * * 1-5"
            assert data["scheduler"]["timezone"] == "America/New_York"
            assert data["scheduler"]["enabled"] is True

    def test_start_scheduler_endpoint(self):
        """Test POST /scheduler/start endpoint."""
        client = TestClient(app)

        with patch('app.routes.scheduler.get_scheduler') as mock_get_scheduler:
            mock_scheduler = MagicMock()
            mock_scheduler._running = False
            mock_scheduler.get_status.return_value = {"running": False}
            mock_scheduler.start = AsyncMock()
            mock_get_scheduler.return_value = mock_scheduler

            response = client.post("/scheduler/start")

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert "Scheduler started successfully" in data["message"]
            mock_scheduler.start.assert_called_once()

    def test_stop_scheduler_endpoint(self):
        """Test POST /scheduler/stop endpoint."""
        client = TestClient(app)

        with patch('app.routes.scheduler.get_scheduler') as mock_get_scheduler:
            mock_scheduler = MagicMock()
            mock_scheduler._running = True
            mock_scheduler.get_status.return_value = {"running": True}
            mock_scheduler.stop = AsyncMock()
            mock_get_scheduler.return_value = mock_scheduler

            response = client.post("/scheduler/stop")

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert "Scheduler stopped successfully" in data["message"]
            mock_scheduler.stop.assert_called_once()

    def test_restart_scheduler_endpoint(self):
        """Test POST /scheduler/restart endpoint."""
        client = TestClient(app)

        with patch('app.routes.scheduler.get_scheduler') as mock_get_scheduler:
            mock_scheduler = MagicMock()
            mock_scheduler._running = True
            mock_scheduler.get_status.return_value = {"running": True}
            mock_scheduler.stop = AsyncMock()
            mock_scheduler.start = AsyncMock()
            mock_get_scheduler.return_value = mock_scheduler

            response = client.post("/scheduler/restart")

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert "Scheduler restarted successfully" in data["message"]
            mock_scheduler.stop.assert_called_once()
            mock_scheduler.start.assert_called_once()

    def test_test_scheduler_endpoint(self):
        """Test POST /scheduler/test endpoint."""
        client = TestClient(app)

        with patch('app.routes.scheduler.get_scheduler') as mock_get_scheduler:
            mock_scheduler = MagicMock()
            mock_scheduler._send_digest = AsyncMock()
            mock_scheduler.get_status.return_value = {"running": False}
            mock_get_scheduler.return_value = mock_scheduler

            response = client.post("/scheduler/test")

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert "Test digest sent successfully" in data["message"]
            mock_scheduler._send_digest.assert_called_once()


class TestSchedulerLifecycle:
    """Test scheduler lifecycle management."""

    @pytest.mark.asyncio
    async def test_start_stop_scheduler(self):
        """Test starting and stopping scheduler."""
        scheduler = SchedulerService()

        # Initially not running
        assert scheduler._running is False

        # Start scheduler
        await scheduler.start()
        assert scheduler._running is True

        # Stop scheduler
        await scheduler.stop()
        assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_double_start_scheduler(self):
        """Test starting scheduler when already running."""
        scheduler = SchedulerService()

        # Start scheduler
        await scheduler.start()
        assert scheduler._running is True

        # Try to start again (should not raise error)
        await scheduler.start()
        assert scheduler._running is True

    @pytest.mark.asyncio
    async def test_double_stop_scheduler(self):
        """Test stopping scheduler when not running."""
        scheduler = SchedulerService()

        # Initially not running
        assert scheduler._running is False

        # Try to stop (should not raise error)
        await scheduler.stop()
        assert scheduler._running is False


class TestSchedulerSendDigest:
    """Test scheduler digest sending functionality."""

    @pytest.mark.asyncio
    async def test_send_digest_success(self):
        """Test successful digest sending."""
        with patch.dict(os.environ, {"DEFAULT_RECIPIENTS": "test@example.com"}):
            scheduler = SchedulerService()

            # Send digest
            await scheduler._send_digest()

            # Verify last run was set (indicates success)
            assert scheduler._last_run is not None

    @pytest.mark.asyncio
    async def test_send_digest_no_recipients(self):
        """Test digest sending with no recipients."""
        scheduler = SchedulerService()

        with patch('app.scheduler.service._get_default_recipients') as mock_get_recipients:
            mock_get_recipients.return_value = []

            # Should not raise error, just log warning
            await scheduler._send_digest()

            # Verify last run was not set
            assert scheduler._last_run is None

    @pytest.mark.asyncio
    async def test_send_digest_error(self):
        """Test digest sending with error."""
        scheduler = SchedulerService()

        with patch('app.scheduler.service._build_digest_context') as mock_build_context:
            mock_build_context.side_effect = Exception("Test error")

            # Should raise the exception
            with pytest.raises(Exception, match="Test error"):
                await scheduler._send_digest()


class TestGlobalSchedulerFunctions:
    """Test global scheduler functions."""

    def test_get_scheduler_singleton(self):
        """Test that get_scheduler returns singleton instance."""
        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()
        assert scheduler1 is scheduler2

    @pytest.mark.asyncio
    async def test_start_scheduler_global(self):
        """Test global start_scheduler function."""
        with patch('app.scheduler.service.get_scheduler') as mock_get_scheduler:
            mock_scheduler = MagicMock()
            mock_scheduler.is_enabled.return_value = True
            mock_scheduler.start = AsyncMock()
            mock_get_scheduler.return_value = mock_scheduler

            await start_scheduler()

            mock_scheduler.is_enabled.assert_called_once()
            mock_scheduler.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_scheduler_disabled(self):
        """Test global start_scheduler when disabled."""
        with patch('app.scheduler.service.get_scheduler') as mock_get_scheduler:
            mock_scheduler = MagicMock()
            mock_scheduler.is_enabled.return_value = False
            mock_scheduler.start = AsyncMock()
            mock_get_scheduler.return_value = mock_scheduler

            await start_scheduler()

            mock_scheduler.is_enabled.assert_called_once()
            mock_scheduler.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_scheduler_global(self):
        """Test global stop_scheduler function."""
        with patch('app.scheduler.service.get_scheduler') as mock_get_scheduler:
            mock_scheduler = MagicMock()
            mock_scheduler.stop = AsyncMock()
            mock_get_scheduler.return_value = mock_scheduler

            await stop_scheduler()

            mock_scheduler.stop.assert_called_once()
