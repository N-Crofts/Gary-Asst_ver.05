"""
Test SMTP email configuration and functionality.

This test verifies that:
1. SMTP configuration works with proper credentials
2. Multipart emails are sent correctly
3. Preview suffix is omitted for SMTP driver (unlike console driver)
4. Retry/backoff behavior is maintained
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.services.emailer import SmtpEmailer, ConsoleEmailer, select_emailer_from_env
from app.routes.digest import _handle_send
from app.schemas.digest import DigestSendRequest


class TestSmtpConfiguration:
    """Test SMTP email configuration and behavior."""

    def test_smtp_emailer_creation_with_credentials(self):
        """Test that SmtpEmailer can be created with proper credentials."""
        emailer = SmtpEmailer(
            host="smtp.office365.com",
            port=587,
            username="gary-asst@rpck.com",
            password="test-password",
            use_tls=True
        )

        assert emailer.driver == "smtp"
        assert emailer.host == "smtp.office365.com"
        assert emailer.port == 587
        assert emailer.username == "gary-asst@rpck.com"
        assert emailer.password == "test-password"
        assert emailer.use_tls is True

    def test_smtp_send_multipart_email(self):
        """Test that SMTP sends multipart emails correctly."""
        with patch("smtplib.SMTP") as mock_smtp:
            # Mock SMTP server
            mock_server = MagicMock()
            mock_smtp.return_value = mock_server
            mock_server.starttls.return_value = None
            mock_server.login.return_value = None
            mock_server.sendmail.return_value = None
            mock_server.quit.return_value = None

            emailer = SmtpEmailer(
                host="smtp.office365.com",
                port=587,
                username="gary-asst@rpck.com",
                password="test-password",
                use_tls=True
            )

            # Send email with both HTML and plaintext
            result = emailer.send(
                subject="Test Subject",
                html="<h1>Test HTML</h1>",
                recipients=["test@example.com"],
                sender="gary-asst@rpck.com",
                plaintext="Test Plain Text"
            )

            # Verify SMTP calls
            mock_smtp.assert_called_once_with("smtp.office365.com", 587)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("gary-asst@rpck.com", "test-password")
            mock_server.quit.assert_called_once()

            # Verify sendmail was called
            assert mock_server.sendmail.call_count == 1
            sendmail_args = mock_server.sendmail.call_args
            assert sendmail_args[0][0] == "gary-asst@rpck.com"  # sender
            assert sendmail_args[0][1] == ["test@example.com"]  # recipients

            # Verify the message content is multipart
            message_content = sendmail_args[0][2]  # message content
            assert "multipart/alternative" in message_content
            # Content is base64 encoded, so check for encoded versions
            import base64
            encoded_html = base64.b64encode("<h1>Test HTML</h1>".encode()).decode()
            encoded_plaintext = base64.b64encode("Test Plain Text".encode()).decode()
            assert encoded_html in message_content
            assert encoded_plaintext in message_content

    def test_smtp_send_html_only_email(self):
        """Test that SMTP sends HTML-only emails correctly."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value = mock_server
            mock_server.starttls.return_value = None
            mock_server.login.return_value = None
            mock_server.sendmail.return_value = None
            mock_server.quit.return_value = None

            emailer = SmtpEmailer(
                host="smtp.office365.com",
                port=587,
                username="gary-asst@rpck.com",
                password="test-password",
                use_tls=True
            )

            # Send email with HTML only (no plaintext)
            result = emailer.send(
                subject="Test Subject",
                html="<h1>Test HTML</h1>",
                recipients=["test@example.com"],
                sender="gary-asst@rpck.com"
                # No plaintext parameter
            )

            # Verify sendmail was called
            sendmail_args = mock_server.sendmail.call_args
            message_content = sendmail_args[0][2]

            # Should be single HTML message, not multipart
            assert "multipart/alternative" not in message_content
            assert "text/html" in message_content
            # Content is base64 encoded
            import base64
            encoded_html = base64.b64encode("<h1>Test HTML</h1>".encode()).decode()
            assert encoded_html in message_content

    def test_smtp_no_preview_suffix(self):
        """Test that SMTP driver does not add preview suffix to subject."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value = mock_server
            mock_server.starttls.return_value = None
            mock_server.login.return_value = None
            mock_server.sendmail.return_value = None
            mock_server.quit.return_value = None

            emailer = SmtpEmailer(
                host="smtp.office365.com",
                port=587,
                username="gary-asst@rpck.com",
                password="test-password",
                use_tls=True
            )

            original_subject = "RPCK – Morning Briefing: Mon, Jan 1, 2024"
            emailer.send(
                subject=original_subject,
                html="<h1>Test</h1>",
                recipients=["test@example.com"],
                sender="gary-asst@rpck.com"
            )

            # Verify subject was not modified
            sendmail_args = mock_server.sendmail.call_args
            message_content = sendmail_args[0][2]
            # Subject is MIME encoded, so check for the encoded version
            assert "Subject: " in message_content
            assert "[Preview]" not in message_content
            # The subject should be MIME encoded but not contain [Preview]
            assert "RPCK" in message_content  # Part of the original subject

    def test_console_has_preview_suffix(self):
        """Test that console driver adds preview suffix (for comparison)."""
        emailer = ConsoleEmailer()

        # Capture print output
        with patch('builtins.print') as mock_print:
            emailer.send(
                subject="Test Subject",
                html="<h1>Test</h1>",
                recipients=["test@example.com"],
                sender="gary-asst@rpck.com"
            )

            # Check that preview suffix was added
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            subject_line = next((line for line in print_calls if "subject=" in line), "")
            assert "[Preview]" in subject_line

    def test_smtp_retry_behavior(self):
        """Test that SMTP retries on failure with backoff."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value = mock_server
            mock_server.starttls.return_value = None
            mock_server.login.return_value = None

            # First two calls fail, third succeeds
            mock_server.sendmail.side_effect = [
                Exception("Connection failed"),
                Exception("Connection failed"),
                None
            ]
            mock_server.quit.return_value = None

            emailer = SmtpEmailer(
                host="smtp.office365.com",
                port=587,
                username="gary-asst@rpck.com",
                password="test-password",
                use_tls=True
            )

            # Should succeed after retries
            result = emailer.send(
                subject="Test Subject",
                html="<h1>Test</h1>",
                recipients=["test@example.com"],
                sender="gary-asst@rpck.com"
            )

            # Verify multiple attempts were made
            assert mock_server.sendmail.call_count == 3

    def test_smtp_final_failure_raises_exception(self):
        """Test that SMTP raises exception after all retries fail."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value = mock_server
            mock_server.starttls.return_value = None
            mock_server.login.return_value = None
            mock_server.sendmail.side_effect = Exception("Persistent failure")
            mock_server.quit.return_value = None

            emailer = SmtpEmailer(
                host="smtp.office365.com",
                port=587,
                username="gary-asst@rpck.com",
                password="test-password",
                use_tls=True
            )

            # Should raise HTTPException after all retries
            with pytest.raises(Exception) as exc_info:
                emailer.send(
                    subject="Test Subject",
                    html="<h1>Test</h1>",
                    recipients=["test@example.com"],
                    sender="gary-asst@rpck.com"
                )

            assert "SMTP send failed after retries" in str(exc_info.value)

    def test_smtp_configuration_from_env(self):
        """Test that SMTP emailer is selected from environment variables."""
        with patch.dict(os.environ, {
            'MAIL_DRIVER': 'smtp',
            'SMTP_HOST': 'smtp.office365.com',
            'SMTP_PORT': '587',
            'SMTP_USERNAME': 'gary-asst@rpck.com',
            'SMTP_PASSWORD': 'test-password',
            'SMTP_USE_TLS': 'true'
        }):
            emailer = select_emailer_from_env()
            assert isinstance(emailer, SmtpEmailer)
            assert emailer.host == "smtp.office365.com"
            assert emailer.port == 587
            assert emailer.username == "gary-asst@rpck.com"
            assert emailer.password == "test-password"
            assert emailer.use_tls is True

    def test_smtp_missing_config_raises_exception(self):
        """Test that missing SMTP configuration raises appropriate exception."""
        with patch.dict(os.environ, {
            'MAIL_DRIVER': 'smtp',
            # Missing SMTP_HOST and SMTP_PORT
        }, clear=True):
            with pytest.raises(Exception) as exc_info:
                select_emailer_from_env()
            assert "SMTP configuration missing" in str(exc_info.value)

    def test_smtp_invalid_port_raises_exception(self):
        """Test that invalid SMTP port raises appropriate exception."""
        with patch.dict(os.environ, {
            'MAIL_DRIVER': 'smtp',
            'SMTP_HOST': 'smtp.office365.com',
            'SMTP_PORT': 'invalid',
            'SMTP_USERNAME': 'gary-asst@rpck.com',
            'SMTP_PASSWORD': 'test-password'
        }):
            with pytest.raises(Exception) as exc_info:
                select_emailer_from_env()
            assert "SMTP_PORT must be an integer" in str(exc_info.value)


class TestSmtpIntegration:
    """Test SMTP integration with the digest send endpoint."""

    @pytest.mark.asyncio
    async def test_digest_send_with_smtp_driver(self):
        """Test that digest send works with SMTP driver."""
        with patch.dict(os.environ, {
            'MAIL_DRIVER': 'smtp',
            'SMTP_HOST': 'smtp.office365.com',
            'SMTP_PORT': '587',
            'SMTP_USERNAME': 'gary-asst@rpck.com',
            'SMTP_PASSWORD': 'test-password',
            'SMTP_USE_TLS': 'true',
            'DEFAULT_RECIPIENTS': 'test@example.com',
            'DEFAULT_SENDER': 'gary-asst@rpck.com'
        }):
            with patch("smtplib.SMTP") as mock_smtp:
                mock_server = MagicMock()
                mock_smtp.return_value = mock_server
                mock_server.starttls.return_value = None
                mock_server.login.return_value = None
                mock_server.sendmail.return_value = None
                mock_server.quit.return_value = None

                # Mock the request object
                mock_request = MagicMock()
                mock_request.headers = {}

                # Create send request
                send_request = DigestSendRequest(
                    send=True,
                    source="live"
                )

                # Call the handler
                response = await _handle_send(mock_request, send_request)

                # Verify response (response is a JSONResponse, so we need to access the body)
                response_data = response.body.decode()
                import json
                response_dict = json.loads(response_data)
                assert response_dict["ok"] is True
                assert response_dict["action"] == "sent"
                assert response_dict["driver"] == "smtp"
                assert response_dict["source"] == "live"
                assert "test@example.com" in response_dict["recipients"]

                # Verify SMTP was called
                mock_smtp.assert_called_once()
                mock_server.sendmail.assert_called_once()

                # Verify the email was sent from gary-asst@rpck.com
                sendmail_args = mock_server.sendmail.call_args
                assert sendmail_args[0][0] == "gary-asst@rpck.com"
