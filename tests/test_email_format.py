import os
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException

from app.services.emailer import (
    ConsoleEmailer, SmtpEmailer, SendgridEmailer,
    _include_plaintext, _preview_subject_suffix
)
from app.rendering.plaintext import render_plaintext


class TestEmailFormatConfiguration:
    """Test email format configuration functions."""

    def test_include_plaintext_default(self):
        """Test default plaintext inclusion setting."""
        with patch.dict(os.environ, {}, clear=True):
            assert _include_plaintext() is True

    def test_include_plaintext_enabled(self):
        """Test plaintext inclusion when enabled."""
        with patch.dict(os.environ, {"INCLUDE_PLAINTEXT": "true"}):
            assert _include_plaintext() is True

    def test_include_plaintext_disabled(self):
        """Test plaintext inclusion when disabled."""
        with patch.dict(os.environ, {"INCLUDE_PLAINTEXT": "false"}):
            assert _include_plaintext() is False

    def test_preview_subject_suffix_default(self):
        """Test default preview subject suffix."""
        with patch.dict(os.environ, {}, clear=True):
            assert _preview_subject_suffix() == " [Preview]"

    def test_preview_subject_suffix_custom(self):
        """Test custom preview subject suffix."""
        with patch.dict(os.environ, {"PREVIEW_SUBJECT_SUFFIX": " [Test]"}):
            assert _preview_subject_suffix() == " [Test]"


class TestConsoleEmailerFormat:
    """Test console emailer format functionality."""

    def test_console_emailer_adds_subject_suffix(self):
        """Test that console emailer adds preview suffix to subject."""
        emailer = ConsoleEmailer()

        with patch.dict(os.environ, {"PREVIEW_SUBJECT_SUFFIX": " [Preview]"}):
            with patch('builtins.print') as mock_print:
                message_id = emailer.send(
                    subject="Test Subject",
                    html="<p>Test HTML</p>",
                    recipients=["test@example.com"],
                    sender="sender@example.com"
                )

                # Check that print was called with subject containing suffix
                print_calls = mock_print.call_args_list
                assert len(print_calls) >= 1
                print_content = str(print_calls[0])
                assert "Test Subject [Preview]" in print_content
                assert message_id.startswith("MSG-LOCAL-")

    def test_console_emailer_includes_plaintext_when_enabled(self):
        """Test that console emailer includes plaintext when enabled."""
        emailer = ConsoleEmailer()

        with patch.dict(os.environ, {"INCLUDE_PLAINTEXT": "true"}):
            with patch('builtins.print') as mock_print:
                emailer.send(
                    subject="Test Subject",
                    html="<p>Test HTML</p>",
                    recipients=["test@example.com"],
                    sender="sender@example.com",
                    plaintext="Test plaintext content"
                )

                # Check that both HTML and plaintext previews were printed
                print_calls = mock_print.call_args_list
                assert len(print_calls) >= 2

                html_call = str(print_calls[0])
                plaintext_call = str(print_calls[1])

                assert "html_preview" in html_call
                assert "plaintext_preview" in plaintext_call
                assert "Test plaintext content" in plaintext_call

    def test_console_emailer_skips_plaintext_when_disabled(self):
        """Test that console emailer skips plaintext when disabled."""
        emailer = ConsoleEmailer()

        with patch.dict(os.environ, {"INCLUDE_PLAINTEXT": "false"}):
            with patch('builtins.print') as mock_print:
                emailer.send(
                    subject="Test Subject",
                    html="<p>Test HTML</p>",
                    recipients=["test@example.com"],
                    sender="sender@example.com",
                    plaintext="Test plaintext content"
                )

                # Check that only HTML preview was printed
                print_calls = mock_print.call_args_list
                assert len(print_calls) == 1

                html_call = str(print_calls[0])
                assert "html_preview" in html_call
                assert "plaintext_preview" not in html_call


class TestSmtpEmailerFormat:
    """Test SMTP emailer format functionality."""

    def test_smtp_emailer_single_html_when_no_plaintext(self):
        """Test that SMTP emailer sends single HTML when no plaintext provided."""
        emailer = SmtpEmailer("localhost", 587, "user", "pass", True)

        with patch('smtplib.SMTP') as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value = mock_server

            emailer.send(
                subject="Test Subject",
                html="<p>Test HTML</p>",
                recipients=["test@example.com"],
                sender="sender@example.com"
            )

            # Verify SMTP was called
            mock_smtp.assert_called_once_with("localhost", 587)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("user", "pass")
            mock_server.sendmail.assert_called_once()
            mock_server.quit.assert_called_once()

            # Check that sendmail was called with proper arguments
            sendmail_args = mock_server.sendmail.call_args
            assert sendmail_args[0][0] == "sender@example.com"  # sender
            assert sendmail_args[0][1] == ["test@example.com"]  # recipients

    def test_smtp_emailer_multipart_when_plaintext_enabled(self):
        """Test that SMTP emailer sends multipart/alternative when plaintext enabled."""
        emailer = SmtpEmailer("localhost", 587, "user", "pass", True)

        with patch.dict(os.environ, {"INCLUDE_PLAINTEXT": "true"}):
            with patch('smtplib.SMTP') as mock_smtp:
                mock_server = MagicMock()
                mock_smtp.return_value = mock_server

                emailer.send(
                    subject="Test Subject",
                    html="<p>Test HTML</p>",
                    recipients=["test@example.com"],
                    sender="sender@example.com",
                    plaintext="Test plaintext content"
                )

                # Verify SMTP was called
                mock_smtp.assert_called_once_with("localhost", 587)
                mock_server.starttls.assert_called_once()
                mock_server.login.assert_called_once_with("user", "pass")
                mock_server.sendmail.assert_called_once()
                mock_server.quit.assert_called_once()

    def test_smtp_emailer_single_html_when_plaintext_disabled(self):
        """Test that SMTP emailer sends single HTML when plaintext disabled."""
        emailer = SmtpEmailer("localhost", 587, "user", "pass", True)

        with patch.dict(os.environ, {"INCLUDE_PLAINTEXT": "false"}):
            with patch('smtplib.SMTP') as mock_smtp:
                mock_server = MagicMock()
                mock_smtp.return_value = mock_server

                emailer.send(
                    subject="Test Subject",
                    html="<p>Test HTML</p>",
                    recipients=["test@example.com"],
                    sender="sender@example.com",
                    plaintext="Test plaintext content"
                )

                # Verify SMTP was called
                mock_smtp.assert_called_once_with("localhost", 587)
                mock_server.starttls.assert_called_once()
                mock_server.login.assert_called_once_with("user", "pass")
                mock_server.sendmail.assert_called_once()
                mock_server.quit.assert_called_once()


class TestSendgridEmailerFormat:
    """Test SendGrid emailer format functionality."""

    def test_sendgrid_emailer_single_html_when_no_plaintext(self):
        """Test that SendGrid emailer sends single HTML when no plaintext provided."""
        emailer = SendgridEmailer("test-api-key")

        with patch('httpx.Client') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 202
            mock_response.headers = {"X-Message-Id": "test-message-id"}

            mock_client.return_value.__enter__.return_value.post.return_value = mock_response

            message_id = emailer.send(
                subject="Test Subject",
                html="<p>Test HTML</p>",
                recipients=["test@example.com"],
                sender="sender@example.com"
            )

            assert message_id == "test-message-id"

            # Verify the request was made with correct data
            mock_client.return_value.__enter__.return_value.post.assert_called_once()
            call_args = mock_client.return_value.__enter__.return_value.post.call_args

            # Check the JSON data
            json_data = call_args[1]["json"]
            assert json_data["subject"] == "Test Subject"
            assert len(json_data["content"]) == 1
            assert json_data["content"][0]["type"] == "text/html"
            assert json_data["content"][0]["value"] == "<p>Test HTML</p>"

    def test_sendgrid_emailer_multipart_when_plaintext_enabled(self):
        """Test that SendGrid emailer sends multipart when plaintext enabled."""
        emailer = SendgridEmailer("test-api-key")

        with patch.dict(os.environ, {"INCLUDE_PLAINTEXT": "true"}):
            with patch('httpx.Client') as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 202
                mock_response.headers = {"X-Message-Id": "test-message-id"}

                mock_client.return_value.__enter__.return_value.post.return_value = mock_response

                message_id = emailer.send(
                    subject="Test Subject",
                    html="<p>Test HTML</p>",
                    recipients=["test@example.com"],
                    sender="sender@example.com",
                    plaintext="Test plaintext content"
                )

                assert message_id == "test-message-id"

                # Verify the request was made with correct data
                mock_client.return_value.__enter__.return_value.post.assert_called_once()
                call_args = mock_client.return_value.__enter__.return_value.post.call_args

                # Check the JSON data
                json_data = call_args[1]["json"]
                assert json_data["subject"] == "Test Subject"
                assert len(json_data["content"]) == 2

                # Plaintext should be first
                assert json_data["content"][0]["type"] == "text/plain"
                assert json_data["content"][0]["value"] == "Test plaintext content"

                # HTML should be second
                assert json_data["content"][1]["type"] == "text/html"
                assert json_data["content"][1]["value"] == "<p>Test HTML</p>"

    def test_sendgrid_emailer_single_html_when_plaintext_disabled(self):
        """Test that SendGrid emailer sends single HTML when plaintext disabled."""
        emailer = SendgridEmailer("test-api-key")

        with patch.dict(os.environ, {"INCLUDE_PLAINTEXT": "false"}):
            with patch('httpx.Client') as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 202
                mock_response.headers = {"X-Message-Id": "test-message-id"}

                mock_client.return_value.__enter__.return_value.post.return_value = mock_response

                message_id = emailer.send(
                    subject="Test Subject",
                    html="<p>Test HTML</p>",
                    recipients=["test@example.com"],
                    sender="sender@example.com",
                    plaintext="Test plaintext content"
                )

                assert message_id == "test-message-id"

                # Verify the request was made with correct data
                mock_client.return_value.__enter__.return_value.post.assert_called_once()
                call_args = mock_client.return_value.__enter__.return_value.post.call_args

                # Check the JSON data
                json_data = call_args[1]["json"]
                assert json_data["subject"] == "Test Subject"
                assert len(json_data["content"]) == 1
                assert json_data["content"][0]["type"] == "text/html"
                assert json_data["content"][0]["value"] == "<p>Test HTML</p>"


class TestPlaintextRenderer:
    """Test plaintext renderer functionality."""

    def test_render_plaintext_basic_structure(self):
        """Test that plaintext renderer produces basic structure."""
        context = {
            "exec_name": "Test Exec",
            "date_human": "Dec 15, 2024",
            "current_year": "2024",
            "meetings": [
                {
                    "subject": "Test Meeting",
                    "start_time": "10:00 AM ET",
                    "location": "Zoom",
                    "attendees": [
                        {"name": "John Doe", "title": "Manager", "company": "Test Corp"}
                    ],
                    "company": {"name": "Test Corp", "one_liner": "Test company"},
                    "news": [
                        {"title": "Test News", "url": "https://example.com/news"}
                    ],
                    "talking_points": ["Point 1", "Point 2"],
                    "smart_questions": ["Question 1", "Question 2"],
                    "memory": {
                        "previous_meetings": [
                            {"date": "Dec 10, 2024", "subject": "Previous Meeting", "key_attendees": ["John Doe"]}
                        ]
                    }
                }
            ]
        }

        plaintext = render_plaintext(context)

        # Check basic structure
        assert "RPCK – Morning Briefing" in plaintext
        assert "Prepared for Test Exec" in plaintext
        assert "Date: Dec 15, 2024" in plaintext
        assert "Test Meeting" in plaintext
        assert "10:00 AM ET" in plaintext
        assert "Zoom" in plaintext
        assert "John Doe, Manager (Test Corp)" in plaintext
        assert "Test Corp" in plaintext
        assert "Test company" in plaintext
        assert "Test News (https://example.com/news)" in plaintext
        assert "Point 1" in plaintext
        assert "Question 1" in plaintext
        assert "Previous Meeting" in plaintext
        assert "Recent with them:" in plaintext

    def test_render_plaintext_empty_meetings(self):
        """Test that plaintext renderer handles empty meetings."""
        context = {
            "exec_name": "Test Exec",
            "date_human": "Dec 15, 2024",
            "current_year": "2024",
            "meetings": []
        }

        plaintext = render_plaintext(context)

        assert "RPCK – Morning Briefing" in plaintext
        assert "No meetings scheduled for today." in plaintext

    def test_render_plaintext_contains_required_markers(self):
        """Test that plaintext contains required markers for deliverability."""
        context = {
            "exec_name": "Test Exec",
            "date_human": "Dec 15, 2024",
            "current_year": "2024",
            "meetings": [
                {
                    "subject": "Test Meeting",
                    "start_time": "10:00 AM ET",
                    "attendees": [],
                    "news": [
                        {"title": "News 1", "url": "https://example.com/1"},
                        {"title": "News 2", "url": "https://example.com/2"},
                        {"title": "News 3", "url": "https://example.com/3"}
                    ],
                    "talking_points": [],
                    "smart_questions": []
                }
            ]
        }

        plaintext = render_plaintext(context)

        # Check for required markers
        assert "RPCK – Morning Briefing" in plaintext  # Header
        assert "Test Meeting" in plaintext  # Meeting subject
        assert "News 1 (https://example.com/1)" in plaintext  # At least 3 links as Title (URL)
        assert "News 2 (https://example.com/2)" in plaintext
        assert "News 3 (https://example.com/3)" in plaintext
        assert "© 2024 RPCK Rastegar Panchal LLP" in plaintext  # Footer
