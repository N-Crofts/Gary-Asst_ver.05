from __future__ import annotations

import os
from typing import List, Optional

from fastapi import HTTPException


class Emailer:
    driver: str

    def send(self, subject: str, html: str, recipients: List[str], sender: str) -> Optional[str]:
        raise NotImplementedError


class ConsoleEmailer(Emailer):
    driver = "console"

    def send(self, subject: str, html: str, recipients: List[str], sender: str) -> Optional[str]:
        # Simulate a send. Avoid printing secrets or full HTML in logs.
        preview_len = min(len(html), 200)
        print(f"[console-email] from={sender} to={','.join(recipients)} subject={subject} html_preview={html[:preview_len]!r}...")
        return None


class SmtpEmailer(Emailer):
    driver = "smtp"

    def __init__(self, host: str, port: int, username: str, password: str, use_tls: bool):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls

    def send(self, subject: str, html: str, recipients: List[str], sender: str) -> Optional[str]:
        try:
            import smtplib
            from email.mime.text import MIMEText
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"SMTP not available: {exc}")

        message = MIMEText(html, "html")
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = ", ".join(recipients)

        try:
            if self.use_tls:
                server = smtplib.SMTP(self.host, self.port)
                server.starttls()
            else:
                server = smtplib.SMTP(self.host, self.port)
            if self.username:
                server.login(self.username, self.password)
            server.sendmail(sender, recipients, message.as_string())
            server.quit()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"SMTP send failed: {exc}")
        return None


class SendgridEmailer(Emailer):
    driver = "sendgrid"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def send(self, subject: str, html: str, recipients: List[str], sender: str) -> Optional[str]:
        import httpx

        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        data = {
            "personalizations": [{"to": [{"email": r} for r in recipients]}],
            "from": {"email": sender},
            "subject": subject,
            "content": [{"type": "text/html", "value": html}],
        }
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(url, headers=headers, json=data)
            if resp.status_code not in (200, 202):
                raise HTTPException(status_code=503, detail=f"SendGrid send failed: {resp.status_code} {resp.text}")
            return resp.headers.get("X-Message-Id") or None
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"SendGrid send failed: {exc}")


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


