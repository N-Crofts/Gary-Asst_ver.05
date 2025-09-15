import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.routes.health import update_last_run, get_last_run
from app.observability.logger import log_event, timing, _sanitize_subject, init_sentry


class TestHealthEndpoints:
    """Test health check endpoints."""

    def setup_method(self):
        """Clear last run data before each test."""
        import app.routes.health
        app.routes.health._last_run = None

    def test_healthz_basic(self):
        """Test basic health check without last run."""
        client = TestClient(app)

        response = client.get("/healthz")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert "observability" in data
        assert data["observability"]["enabled"] is False
        assert data["observability"]["sentry_configured"] is False
        assert "last_run" not in data

    def test_healthz_with_last_run(self):
        """Test health check with last run information."""
        client = TestClient(app)

        # Update last run information
        update_last_run(
            action="sent",
            driver="console",
            source="sample",
            subject="Test Subject",
            recipients_count=2,
            message_id="test-123",
            duration_ms=150.5,
            success=True,
        )

        response = client.get("/healthz")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "last_run" in data

        last_run = data["last_run"]
        assert last_run["action"] == "sent"
        assert last_run["driver"] == "console"
        assert last_run["source"] == "sample"
        assert last_run["subject"] == "Test Subject"
        assert last_run["recipients_count"] == 2
        assert last_run["message_id"] == "test-123"
        assert last_run["duration_ms"] == 150.5
        assert last_run["success"] is True

    def test_healthz_with_error(self):
        """Test health check with error in last run."""
        client = TestClient(app)

        # Update last run with error
        update_last_run(
            action="failed",
            driver="unknown",
            source="scheduled",
            subject="Scheduled Digest",
            recipients_count=0,
            success=False,
            error="Connection timeout",
        )

        response = client.get("/healthz")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "last_run" in data

        last_run = data["last_run"]
        assert last_run["action"] == "failed"
        assert last_run["success"] is False
        assert last_run["error"] == "Connection timeout"

    def test_healthz_observability_enabled(self):
        """Test health check with observability enabled."""
        client = TestClient(app)

        with patch.dict(os.environ, {"OBS_ENABLED": "true", "SENTRY_DSN": "https://test@sentry.io/123"}):
            response = client.get("/healthz")

            assert response.status_code == 200
            data = response.json()
            assert data["observability"]["enabled"] is True
            assert data["observability"]["sentry_configured"] is True

    def test_readiness_check_healthy(self):
        """Test readiness check when all services are healthy."""
        client = TestClient(app)

        response = client.get("/healthz/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert "checks" in data
        assert data["checks"]["database"] == "ok"
        assert data["checks"]["email_service"] == "ok"
        assert data["checks"]["scheduler"] == "ok"

    def test_liveness_check(self):
        """Test liveness check."""
        client = TestClient(app)

        response = client.get("/healthz/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "uptime" in data


class TestLastRunTracking:
    """Test last run tracking functionality."""

    def test_update_last_run_success(self):
        """Test updating last run with success."""
        update_last_run(
            action="sent",
            driver="smtp",
            source="live",
            subject="Live Digest",
            recipients_count=5,
            message_id="smtp-456",
            duration_ms=200.0,
            success=True,
        )

        last_run = get_last_run()
        assert last_run is not None
        assert last_run["action"] == "sent"
        assert last_run["driver"] == "smtp"
        assert last_run["source"] == "live"
        assert last_run["subject"] == "Live Digest"
        assert last_run["recipients_count"] == 5
        assert last_run["message_id"] == "smtp-456"
        assert last_run["duration_ms"] == 200.0
        assert last_run["success"] is True
        assert "time" in last_run

    def test_update_last_run_failure(self):
        """Test updating last run with failure."""
        update_last_run(
            action="failed",
            driver="sendgrid",
            source="scheduled",
            subject="Scheduled Digest",
            recipients_count=0,
            success=False,
            error="API key invalid",
        )

        last_run = get_last_run()
        assert last_run is not None
        assert last_run["action"] == "failed"
        assert last_run["success"] is False
        assert last_run["error"] == "API key invalid"

    def test_update_last_run_minimal(self):
        """Test updating last run with minimal information."""
        update_last_run(
            action="rendered",
            driver="console",
            source="sample",
            subject="Test",
            recipients_count=0,
        )

        last_run = get_last_run()
        assert last_run is not None
        assert last_run["action"] == "rendered"
        assert last_run["driver"] == "console"
        assert last_run["source"] == "sample"
        assert last_run["subject"] == "Test"
        assert last_run["recipients_count"] == 0
        assert last_run["success"] is True
        assert "message_id" not in last_run
        assert "duration_ms" not in last_run
        assert "error" not in last_run


class TestStructuredLogging:
    """Test structured logging functionality."""

    def test_log_event_basic(self):
        """Test basic log event."""
        with patch('app.observability.logger.logger') as mock_logger:
            log_event(
                action="sent",
                driver="console",
                source="sample",
                subject="Test Subject",
                recipients_count=2,
            )

            mock_logger.info.assert_called_once()
            log_data = json.loads(mock_logger.info.call_args[0][0])

            assert log_data["action"] == "sent"
            assert log_data["driver"] == "console"
            assert log_data["source"] == "sample"
            assert log_data["subject"] == "Test Subject"
            assert log_data["recipients_count"] == 2
            assert "timestamp" in log_data

    def test_log_event_with_optional_fields(self):
        """Test log event with optional fields."""
        with patch('app.observability.logger.logger') as mock_logger:
            log_event(
                action="sent",
                driver="smtp",
                source="live",
                subject="Live Digest",
                recipients_count=5,
                message_id="smtp-123",
                duration_ms=150.5,
                custom_field="test_value",
            )

            mock_logger.info.assert_called_once()
            log_data = json.loads(mock_logger.info.call_args[0][0])

            assert log_data["message_id"] == "smtp-123"
            assert log_data["duration_ms"] == 150.5
            assert log_data["custom_field"] == "test_value"

    def test_log_event_sanitizes_subject(self):
        """Test that log event sanitizes sensitive subjects."""
        with patch('app.observability.logger.logger') as mock_logger:
            log_event(
                action="sent",
                driver="console",
                source="sample",
                subject="Password reset for user",
                recipients_count=1,
            )

            mock_logger.info.assert_called_once()
            log_data = json.loads(mock_logger.info.call_args[0][0])

            assert log_data["subject"] == "[REDACTED]"

    def test_log_event_truncates_long_subject(self):
        """Test that log event truncates very long subjects."""
        with patch('app.observability.logger.logger') as mock_logger:
            long_subject = "A" * 150
            log_event(
                action="sent",
                driver="console",
                source="sample",
                subject=long_subject,
                recipients_count=1,
            )

            mock_logger.info.assert_called_once()
            log_data = json.loads(mock_logger.info.call_args[0][0])

            assert log_data["subject"] == "A" * 97 + "..."

    def test_sanitize_subject_removes_sensitive_patterns(self):
        """Test subject sanitization removes sensitive patterns."""
        sensitive_subjects = [
            "Password reset",
            "Secret key rotation",
            "API key update",
            "Auth token refresh",
            "Credential management",
        ]

        for subject in sensitive_subjects:
            sanitized = _sanitize_subject(subject)
            assert sanitized == "[REDACTED]"

    def test_sanitize_subject_preserves_normal_subjects(self):
        """Test subject sanitization preserves normal subjects."""
        normal_subjects = [
            "Daily Digest",
            "Meeting Reminder",
            "Weekly Report",
            "Project Update",
        ]

        for subject in normal_subjects:
            sanitized = _sanitize_subject(subject)
            assert sanitized == subject


class TestTimingContext:
    """Test timing context manager."""

    def test_timing_context_success(self):
        """Test timing context with successful operation."""
        with timing("test_operation") as timer:
            import time
            time.sleep(0.01)  # 10ms sleep

        duration = timer.get_duration_ms()
        assert duration is not None
        assert duration >= 10  # Should be at least 10ms
        assert duration < 100  # Should be less than 100ms

    def test_timing_context_exception(self):
        """Test timing context with exception."""
        with pytest.raises(ValueError):
            with timing("test_operation") as timer:
                raise ValueError("Test error")

        # Timer should still have duration even with exception
        assert timer.get_duration_ms() is not None


class TestSentryIntegration:
    """Test Sentry integration."""

    def test_init_sentry_disabled(self):
        """Test Sentry initialization when disabled."""
        with patch.dict(os.environ, {"OBS_ENABLED": "false"}):
            result = init_sentry()
            assert result is False

    def test_init_sentry_no_dsn(self):
        """Test Sentry initialization without DSN."""
        with patch.dict(os.environ, {"OBS_ENABLED": "true", "SENTRY_DSN": ""}):
            result = init_sentry()
            assert result is False

    def test_init_sentry_with_dsn(self):
        """Test Sentry initialization with DSN."""
        with patch.dict(os.environ, {"OBS_ENABLED": "true", "SENTRY_DSN": "https://test@sentry.io/123"}):
            # Since sentry_sdk is not installed, this should return False
            result = init_sentry()
            assert result is False

    def test_init_sentry_import_error(self):
        """Test Sentry initialization with import error."""
        with patch.dict(os.environ, {"OBS_ENABLED": "true", "SENTRY_DSN": "https://test@sentry.io/123"}):
            with patch('builtins.__import__', side_effect=ImportError):
                result = init_sentry()
                assert result is False


class TestDigestLoggingIntegration:
    """Test digest endpoint logging integration."""

    def test_digest_send_logs_event(self):
        """Test that digest send endpoint logs structured events."""
        client = TestClient(app)

        with patch('app.observability.logger.logger') as mock_logger:
            response = client.post(
                "/digest/send",
                json={"send": True, "source": "sample"}
            )

            assert response.status_code == 200

            # Check that structured log was called
            mock_logger.info.assert_called()

            # Find the structured log call
            structured_log_calls = [
                call for call in mock_logger.info.call_args_list
                if call[0] and isinstance(call[0][0], str) and call[0][0].startswith('{')
            ]

            assert len(structured_log_calls) > 0

            # Parse the structured log
            log_data = json.loads(structured_log_calls[0][0][0])
            assert log_data["action"] in ["sent", "rendered"]
            assert log_data["driver"] == "console"
            assert log_data["source"] == "sample"
            assert "recipients_count" in log_data
            assert "duration_ms" in log_data

    def test_digest_send_updates_last_run(self):
        """Test that digest send endpoint updates last run."""
        client = TestClient(app)

        response = client.post(
            "/digest/send",
            json={"send": True, "source": "sample"}
        )

        assert response.status_code == 200

        # Check health endpoint includes last run
        health_response = client.get("/healthz")
        assert health_response.status_code == 200

        health_data = health_response.json()
        assert "last_run" in health_data

        last_run = health_data["last_run"]
        assert last_run["action"] in ["sent", "rendered"]
        assert last_run["driver"] == "console"
        assert last_run["source"] == "sample"


class TestSchedulerLoggingIntegration:
    """Test scheduler logging integration."""

    def test_scheduler_test_logs_event(self):
        """Test that scheduler test endpoint logs structured events."""
        client = TestClient(app)

        with patch.dict(os.environ, {"DEFAULT_RECIPIENTS": "test@example.com"}):
            with patch('app.observability.logger.logger') as mock_logger:
                response = client.post("/scheduler/test")

                assert response.status_code == 200

                # Check that structured log was called
                mock_logger.info.assert_called()

                # Find the structured log call
                structured_log_calls = [
                    call for call in mock_logger.info.call_args_list
                    if call[0] and isinstance(call[0][0], str) and call[0][0].startswith('{')
                ]

                assert len(structured_log_calls) > 0

                # Parse the structured log
                log_data = json.loads(structured_log_calls[0][0][0])
                assert log_data["action"] in ["sent", "rendered"]
                assert log_data["driver"] == "console"
                assert log_data["source"] == "scheduled"
                assert "recipients_count" in log_data
                assert "duration_ms" in log_data

    def test_scheduler_test_updates_last_run(self):
        """Test that scheduler test endpoint updates last run."""
        client = TestClient(app)

        with patch.dict(os.environ, {"DEFAULT_RECIPIENTS": "test@example.com"}):
            response = client.post("/scheduler/test")

            assert response.status_code == 200

            # Check health endpoint includes last run
            health_response = client.get("/healthz")
            assert health_response.status_code == 200

            health_data = health_response.json()
            assert "last_run" in health_data

            last_run = health_data["last_run"]
            assert last_run["action"] in ["sent", "rendered"]
            assert last_run["driver"] == "console"
            assert last_run["source"] == "scheduled"
