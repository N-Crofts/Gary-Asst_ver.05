from unittest.mock import patch, MagicMock

from app.services.emailer import ConsoleEmailer, SmtpEmailer, SendgridEmailer


def test_console_returns_message_id():
    msg_id = ConsoleEmailer().send("subj", "<b>hi</b>", ["a@example.com"], "me@example.com")
    assert isinstance(msg_id, str)
    assert msg_id.startswith("MSG-LOCAL-")


def test_smtp_retries_then_succeeds():
    smtp_mock = MagicMock()
    # First two calls raise, third call succeeds
    smtp_mock.sendmail.side_effect = [Exception("temp"), Exception("temp"), None]

    with patch("smtplib.SMTP") as SMTP:
        instance = SMTP.return_value
        instance.starttls.return_value = None
        instance.login.return_value = None
        instance.sendmail.side_effect = smtp_mock.sendmail.side_effect
        instance.quit.return_value = None

        m = SmtpEmailer(host="localhost", port=25, username="", password="", use_tls=False)
        m.send("s", "h", ["r@example.com"], "s@example.com")
        assert instance.sendmail.call_count >= 3


def test_sendgrid_retries_then_succeeds():
    class Resp:
        def __init__(self, status_code):
            self.status_code = status_code
            self.text = "err"
            self.headers = {"X-Message-Id": "abc123"}

    with patch("httpx.Client") as Client:
        inst = Client.return_value.__enter__.return_value
        inst.post.side_effect = [Resp(500), Resp(500), Resp(202)]
        sg = SendgridEmailer(api_key="k")
        msg_id = sg.send("s", "h", ["r@example.com"], "s@example.com")
        assert msg_id == "abc123"
        assert inst.post.call_count >= 3


