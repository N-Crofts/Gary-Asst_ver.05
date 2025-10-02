"""
Test Slack integration functionality.

This test suite verifies:
1. Slack client configuration and API calls
2. Digest notification posting with rich formatting
3. Action endpoints for external integrations
4. Scheduler integration with Slack posting
"""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import json
from datetime import datetime

from app.channels.slack_client import SlackClient, create_slack_client, post_digest_to_slack
from app.routes.actions import send_now_action, send_now_redirect, preview_action
from app.scheduler.service import SchedulerService


class TestSlackClient:
    """Test Slack client functionality."""

    def test_slack_client_creation(self):
        """Test that SlackClient can be created with proper credentials."""
        client = SlackClient(
            bot_token="xoxb-test-token",
            channel_id="C1234567890"
        )

        assert client.bot_token == "xoxb-test-token"
        assert client.channel_id == "C1234567890"
        assert client.base_url == "https://slack.com/api"
        assert client.timeout == 15.0

    @pytest.mark.asyncio
    async def test_post_message_success(self):
        """Test successful message posting."""
        client = SlackClient("xoxb-test", "C123")

        mock_response = {
            "ok": True,
            "channel": "C123",
            "ts": "1234567890.123456",
            "message": {"text": "Test message"}
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = AsyncMock()
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            mock_response_obj.raise_for_status = AsyncMock(return_value=None)
            mock_instance.post.return_value = mock_response_obj

            result = await client.post_message("Test message")

            assert result["ok"] is True
            assert result["ts"] == "1234567890.123456"
            mock_instance.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_message_api_error(self):
        """Test handling of Slack API errors."""
        client = SlackClient("xoxb-test", "C123")

        mock_response = {
            "ok": False,
            "error": "channel_not_found"
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = AsyncMock()
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            mock_response_obj.raise_for_status = AsyncMock(return_value=None)
            mock_instance.post.return_value = mock_response_obj

            with pytest.raises(Exception) as exc_info:
                await client.post_message("Test message")

            assert "Slack API error: channel_not_found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_post_message_http_error(self):
        """Test handling of HTTP errors."""
        client = SlackClient("xoxb-test", "C123")

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.side_effect = Exception("Connection failed")

            with pytest.raises(Exception) as exc_info:
                await client.post_message("Test message")

            assert "Slack API error: Connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_post_digest_notification(self):
        """Test posting digest notification with rich formatting."""
        client = SlackClient("xoxb-test", "C123")

        mock_response = {
            "ok": True,
            "channel": "C123",
            "ts": "1234567890.123456"
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = AsyncMock()
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            mock_response_obj.raise_for_status = AsyncMock(return_value=None)
            mock_instance.post.return_value = mock_response_obj

            result = await client.post_digest_notification(
                subject="RPCK – Morning Briefing: Mon, Jan 1, 2024",
                meeting_count=5,
                preview_url="http://localhost:8000/digest/preview?source=live",
                send_now_url="http://localhost:8000/actions/send-now"
            )

            assert result["ok"] is True

            # Verify the message was posted with blocks
            call_args = mock_instance.post.call_args
            payload = call_args[1]["json"]

            assert payload["channel"] == "C123"
            assert "blocks" in payload
            assert len(payload["blocks"]) == 4  # header, section, actions, context
            assert payload["blocks"][0]["type"] == "header"
            assert payload["blocks"][2]["type"] == "actions"

            # Check that buttons are included
            buttons = payload["blocks"][2]["elements"]
            assert len(buttons) == 2
            assert buttons[0]["text"]["text"] == "Preview Digest"
            assert buttons[1]["text"]["text"] == "Send to Inbox Now"

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        """Test successful connection test."""
        client = SlackClient("xoxb-test", "C123")

        mock_response = {
            "ok": True,
            "url": "https://test.slack.com/",
            "team": "Test Team",
            "user": "test-bot",
            "team_id": "T1234567890",
            "user_id": "U1234567890",
            "bot_id": "B1234567890"
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = AsyncMock()
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            mock_response_obj.raise_for_status = AsyncMock(return_value=None)
            mock_instance.post.return_value = mock_response_obj

            result = await client.test_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self):
        """Test connection test failure."""
        client = SlackClient("xoxb-test", "C123")

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.side_effect = Exception("Connection failed")

            result = await client.test_connection()
            assert result is False


class TestSlackClientFactory:
    """Test Slack client factory functions."""

    def test_create_slack_client_with_credentials(self):
        """Test creating client with proper credentials."""
        with patch.dict(os.environ, {
            'SLACK_BOT_TOKEN': 'xoxb-test-token',
            'SLACK_CHANNEL_ID': 'C1234567890'
        }):
            client = create_slack_client()
            assert client is not None
            assert client.bot_token == "xoxb-test-token"
            assert client.channel_id == "C1234567890"

    def test_create_slack_client_missing_credentials(self):
        """Test creating client with missing credentials."""
        with patch.dict(os.environ, {}, clear=True):
            client = create_slack_client()
            assert client is None

    def test_create_slack_client_missing_token(self):
        """Test creating client with missing token."""
        with patch.dict(os.environ, {
            'SLACK_CHANNEL_ID': 'C1234567890'
        }, clear=True):
            client = create_slack_client()
            assert client is None

    def test_create_slack_client_missing_channel(self):
        """Test creating client with missing channel."""
        with patch.dict(os.environ, {
            'SLACK_BOT_TOKEN': 'xoxb-test-token'
        }, clear=True):
            client = create_slack_client()
            assert client is None

    @pytest.mark.asyncio
    async def test_post_digest_to_slack_success(self):
        """Test successful digest posting to Slack."""
        with patch.dict(os.environ, {
            'SLACK_BOT_TOKEN': 'xoxb-test-token',
            'SLACK_CHANNEL_ID': 'C1234567890'
        }):
            with patch("app.channels.slack_client.SlackClient.post_digest_notification") as mock_post:
                mock_post.return_value = {"ok": True, "ts": "1234567890.123456"}

                result = await post_digest_to_slack(
                    subject="Test Subject",
                    meeting_count=3,
                    base_url="http://localhost:8000"
                )

                assert result is True
                mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_digest_to_slack_not_configured(self):
        """Test digest posting when Slack is not configured."""
        with patch.dict(os.environ, {}, clear=True):
            result = await post_digest_to_slack(
                subject="Test Subject",
                meeting_count=3
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_post_digest_to_slack_failure(self):
        """Test digest posting failure handling."""
        with patch.dict(os.environ, {
            'SLACK_BOT_TOKEN': 'xoxb-test-token',
            'SLACK_CHANNEL_ID': 'C1234567890'
        }):
            with patch("app.channels.slack_client.SlackClient.post_digest_notification") as mock_post:
                mock_post.side_effect = Exception("API Error")

                result = await post_digest_to_slack(
                    subject="Test Subject",
                    meeting_count=3
                )

                assert result is False


class TestSlackActions:
    """Test Slack action endpoints."""

    @pytest.mark.asyncio
    async def test_send_now_action_success(self):
        """Test successful send now action."""
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch("app.routes.actions._handle_send") as mock_handle:
            mock_response = MagicMock()
            mock_response.body.decode.return_value = json.dumps({
                "ok": True,
                "action": "sent",
                "recipients_count": 2,
                "driver": "console"
            })
            mock_handle.return_value = mock_response

            with patch.dict(os.environ, {'API_KEY': ''}):  # No API key required
                response = await send_now_action(mock_request)

                assert response.status_code == 200
                response_data = json.loads(response.body.decode())
                assert response_data["ok"] is True
                assert response_data["action"] == "sent"

    @pytest.mark.asyncio
    async def test_send_now_action_with_api_key(self):
        """Test send now action with API key authentication."""
        mock_request = MagicMock()
        mock_request.headers = {"x-api-key": "test-key"}

        with patch("app.routes.actions._handle_send") as mock_handle:
            mock_response = MagicMock()
            mock_response.body.decode.return_value = json.dumps({
                "ok": True,
                "action": "sent",
                "recipients_count": 2,
                "driver": "console"
            })
            mock_handle.return_value = mock_response

            with patch.dict(os.environ, {'API_KEY': 'test-key'}):
                response = await send_now_action(mock_request)

                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_send_now_action_invalid_api_key(self):
        """Test send now action with invalid API key."""
        mock_request = MagicMock()
        mock_request.headers = {"x-api-key": "wrong-key"}

        with patch.dict(os.environ, {'API_KEY': 'test-key'}):
            with pytest.raises(Exception) as exc_info:
                await send_now_action(mock_request)

            assert "Invalid or missing API key" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_now_action_failure(self):
        """Test send now action failure handling."""
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch("app.routes.actions._handle_send") as mock_handle:
            mock_handle.side_effect = Exception("Send failed")

            with patch.dict(os.environ, {'API_KEY': ''}):
                response = await send_now_action(mock_request)

                assert response.status_code == 500
                response_data = json.loads(response.body.decode())
                assert response_data["ok"] is False
                assert "Failed to send digest" in response_data["message"]

    @pytest.mark.asyncio
    async def test_send_now_redirect_success(self):
        """Test successful send now redirect."""
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch("app.routes.actions._handle_send") as mock_handle:
            mock_response = MagicMock()
            mock_response.body.decode.return_value = json.dumps({
                "ok": True,
                "action": "sent",
                "recipients_count": 2,
                "driver": "console"
            })
            mock_handle.return_value = mock_response

            with patch.dict(os.environ, {'API_KEY': ''}):
                response = await send_now_redirect(mock_request)

                assert response.status_code == 302
                assert "sent=true" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_send_now_redirect_failure(self):
        """Test send now redirect failure handling."""
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch("app.routes.actions._handle_send") as mock_handle:
            mock_handle.side_effect = Exception("Send failed")

            with patch.dict(os.environ, {'API_KEY': ''}):
                response = await send_now_redirect(mock_request)

                assert response.status_code == 302
                assert "error=" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_preview_action(self):
        """Test preview action redirect."""
        mock_request = MagicMock()

        response = await preview_action(mock_request)

        assert response.status_code == 302
        assert response.headers["location"] == "/digest/preview?source=live"


class TestSlackSchedulerIntegration:
    """Test Slack integration with scheduler."""

    @pytest.mark.asyncio
    async def test_scheduler_with_slack_success(self):
        """Test scheduler with successful Slack posting."""
        with patch.dict(os.environ, {
            'SLACK_ENABLED': 'true',
            'SLACK_BOT_TOKEN': 'xoxb-test-token',
            'SLACK_CHANNEL_ID': 'C1234567890',
            'BASE_URL': 'http://localhost:8000'
        }):
            with patch("app.scheduler.service._build_digest_context") as mock_context:
                mock_context.return_value = {
                    "meetings": [{"id": 1}, {"id": 2}, {"id": 3}],
                    "exec_name": "Test User"
                }

                with patch("app.scheduler.service._get_default_recipients") as mock_recipients:
                    mock_recipients.return_value = ["test@example.com"]

                    with patch("app.scheduler.service._get_sender") as mock_sender:
                        mock_sender.return_value = "gary-asst@rpck.com"

                        with patch("app.scheduler.service._default_subject") as mock_subject:
                            mock_subject.return_value = "Test Subject"

                            with patch("app.scheduler.service.select_emailer_from_env") as mock_emailer:
                                mock_emailer_instance = MagicMock()
                                mock_emailer_instance.driver = "console"
                                mock_emailer_instance.send.return_value = "MSG-123"
                                mock_emailer.return_value = mock_emailer_instance

                                with patch("app.scheduler.service.post_digest_to_slack") as mock_slack:
                                    mock_slack.return_value = True

                                    scheduler = SchedulerService()
                                    await scheduler._send_digest()

                                    # Verify Slack was called
                                    mock_slack.assert_called_once_with(
                                        subject="Test Subject",
                                        meeting_count=3,
                                        base_url="http://localhost:8000"
                                    )

    @pytest.mark.asyncio
    async def test_scheduler_with_slack_failure(self):
        """Test scheduler with Slack posting failure."""
        with patch.dict(os.environ, {
            'SLACK_ENABLED': 'true',
            'SLACK_BOT_TOKEN': 'xoxb-test-token',
            'SLACK_CHANNEL_ID': 'C1234567890'
        }):
            with patch("app.scheduler.service._build_digest_context") as mock_context:
                mock_context.return_value = {
                    "meetings": [{"id": 1}],
                    "exec_name": "Test User"
                }

                with patch("app.scheduler.service._get_default_recipients") as mock_recipients:
                    mock_recipients.return_value = ["test@example.com"]

                    with patch("app.scheduler.service._get_sender") as mock_sender:
                        mock_sender.return_value = "gary-asst@rpck.com"

                        with patch("app.scheduler.service._default_subject") as mock_subject:
                            mock_subject.return_value = "Test Subject"

                            with patch("app.scheduler.service.select_emailer_from_env") as mock_emailer:
                                mock_emailer_instance = MagicMock()
                                mock_emailer_instance.driver = "console"
                                mock_emailer_instance.send.return_value = "MSG-123"
                                mock_emailer.return_value = mock_emailer_instance

                                with patch("app.scheduler.service.post_digest_to_slack") as mock_slack:
                                    mock_slack.side_effect = Exception("Slack API Error")

                                    with patch("app.scheduler.service.logger") as mock_logger:
                                        scheduler = SchedulerService()
                                        await scheduler._send_digest()

                                        # Verify Slack was called and error was logged
                                        mock_slack.assert_called_once()
                                        mock_logger.warning.assert_called()
                                        warning_call = mock_logger.warning.call_args[0][0]
                                        assert "Slack notification failed" in warning_call
