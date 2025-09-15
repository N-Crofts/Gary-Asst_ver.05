from __future__ import annotations

import os
import time
from typing import List, Optional

from fastapi import HTTPException


def _include_plaintext() -> bool:
    """Check if plaintext should be included in emails."""
    return os.getenv("INCLUDE_PLAINTEXT", "true").lower() == "true"


def _preview_subject_suffix() -> str:
    """Get the preview subject suffix for console driver."""
    return os.getenv("PREVIEW_SUBJECT_SUFFIX", " [Preview]")


class Emailer:
    driver: str

    def send(self, subject: str, html: str, recipients: List[str], sender: str, plaintext: Optional[str] = None) -> Optional[str]:
        raise NotImplementedError


class ConsoleEmailer(Emailer):
    driver = "console"

    def send(self, subject: str, html: str, recipients: List[str], sender: str, plaintext: Optional[str] = None) -> Optional[str]:
        # Add preview suffix to subject for console driver
        subject_with_suffix = subject + _preview_subject_suffix()

        # Simulate a send. Avoid printing secrets or full HTML in logs.
        preview_len = min(len(html), 200)
        print(f"[console-email] from={sender} to={','.join(recipients)} subject={subject_with_suffix} html_preview={html[:preview_len]!r}...")

        if plaintext and _include_plaintext():
            plaintext_preview_len = min(len(plaintext), 200)
            print(f"[console-email] plaintext_preview={plaintext[:plaintext_preview_len]!r}...")

        # Return synthetic message id for local debugging
        return f"MSG-LOCAL-{int(time.time()*1000)}"


class SmtpEmailer(Emailer):
    driver = "smtp"

    def __init__(self, host: str, port: int, username: str, password: str, use_tls: bool):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls

    def send(self, subject: str, html: str, recipients: List[str], sender: str, plaintext: Optional[str] = None) -> Optional[str]:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"SMTP not available: {exc}")

        # Create message
        if plaintext and _include_plaintext():
            # Multipart/alternative message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = sender
            message["To"] = ", ".join(recipients)

            # Add plaintext and HTML parts
            text_part = MIMEText(plaintext, "plain", "utf-8")
            html_part = MIMEText(html, "html", "utf-8")

            message.attach(text_part)
            message.attach(html_part)
        else:
            # Single HTML message
            message = MIMEText(html, "html", "utf-8")
            message["Subject"] = subject
            message["From"] = sender
            message["To"] = ", ".join(recipients)

        backoffs = [0.2, 0.4, 0.8]
        last_exc: Exception | None = None
        for attempt, delay in enumerate(backoffs, start=1):
            try:
                server = smtplib.SMTP(self.host, self.port)
                if self.use_tls:
                    server.starttls()
                if self.username:
                    server.login(self.username, self.password)
                server.sendmail(sender, recipients, message.as_string())
                server.quit()
                return None
            except Exception as exc:
                last_exc = exc
                time.sleep(delay)
        # Final attempt without sleeping after
        try:
            server = smtplib.SMTP(self.host, self.port)
            if self.use_tls:
                server.starttls()
            if self.username:
                server.login(self.username, self.password)
            server.sendmail(sender, recipients, message.as_string())
            server.quit()
            return None
        except Exception as exc:
            last_exc = exc
        raise HTTPException(status_code=503, detail=f"SMTP send failed after retries: {last_exc}")


class SendgridEmailer(Emailer):
    driver = "sendgrid"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def send(self, subject: str, html: str, recipients: List[str], sender: str, plaintext: Optional[str] = None) -> Optional[str]:
        import httpx

        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        # Build content array
        content = [{"type": "text/html", "value": html}]
        if plaintext and _include_plaintext():
            content.insert(0, {"type": "text/plain", "value": plaintext})

        data = {
            "personalizations": [{"to": [{"email": r} for r in recipients]}],
            "from": {"email": sender},
            "subject": subject,
            "content": content,
        }
        backoffs = [0.2, 0.4, 0.8]
        last_error: str | None = None
        for delay in backoffs:
            try:
                with httpx.Client(timeout=15) as client:
                    resp = client.post(url, headers=headers, json=data)
                if resp.status_code in (200, 202):
                    return resp.headers.get("X-Message-Id") or None
                last_error = f"{resp.status_code} {resp.text}"
            except Exception as exc:
                last_error = str(exc)
            time.sleep(delay)
        # Final attempt
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(url, headers=headers, json=data)
            if resp.status_code in (200, 202):
                return resp.headers.get("X-Message-Id") or None
            last_error = f"{resp.status_code} {resp.text}"
        except Exception as exc:
            last_error = str(exc)
        raise HTTPException(status_code=503, detail=f"SendGrid send failed after retries: {last_error}")


def select_emailer_from_env() -> Emailer:
    driver = os.getenv("MAIL_DRIVER", "console").lower()
    if driver == "console":
        return ConsoleEmailer()
    if driver == "smtp":
        host = os.getenv("SMTP_HOST")
        port_str = os.getenv("SMTP_PORT")
        username = os.getenv("SMTP_USERNAME", "")
        password = os.getenv("SMTP_PASSWORD", "")
        use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        if not host or not port_str:
            raise HTTPException(status_code=503, detail="SMTP configuration missing: SMTP_HOST/SMTP_PORT required")
        try:
            port = int(port_str)
        except ValueError:
            raise HTTPException(status_code=503, detail="SMTP_PORT must be an integer")
        return SmtpEmailer(host=host, port=port, username=username, password=password, use_tls=use_tls)
    if driver == "sendgrid":
        api_key = os.getenv("SENDGRID_API_KEY")
        if not api_key:
            raise HTTPException(status_code=503, detail="SENDGRID_API_KEY missing")
        return SendgridEmailer(api_key=api_key)
    raise HTTPException(status_code=400, detail=f"Unsupported MAIL_DRIVER: {driver}")


