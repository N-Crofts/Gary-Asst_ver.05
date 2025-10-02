import os
from typing import Optional

from pydantic import BaseModel


class AppConfig(BaseModel):
    mail_driver: str = "console"
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: bool = True
    sendgrid_api_key: Optional[str] = None
    default_sender: str = "gary-asst@rpck.com"
    default_recipients: list[str] = []
    allow_recipient_override: bool = False
    timezone: str = "America/New_York"
    api_key: Optional[str] = None
    slack_enabled: bool = False
    slack_bot_token: Optional[str] = None
    slack_channel_id: Optional[str] = None


def load_config() -> AppConfig:
    recipients_raw = os.getenv("DEFAULT_RECIPIENTS", "")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    smtp_port_str = os.getenv("SMTP_PORT")
    smtp_port = int(smtp_port_str) if smtp_port_str and smtp_port_str.isdigit() else None
    return AppConfig(
        mail_driver=os.getenv("MAIL_DRIVER", "console").lower(),
        smtp_host=os.getenv("SMTP_HOST"),
        smtp_port=smtp_port,
        smtp_username=os.getenv("SMTP_USERNAME"),
        smtp_password=os.getenv("SMTP_PASSWORD"),
        smtp_use_tls=os.getenv("SMTP_USE_TLS", "true").lower() == "true",
        sendgrid_api_key=os.getenv("SENDGRID_API_KEY"),
        default_sender=os.getenv("DEFAULT_SENDER", "gary-asst@rpck.com"),
        default_recipients=recipients,
        allow_recipient_override=os.getenv("ALLOW_RECIPIENT_OVERRIDE", "false").lower() == "true",
        timezone=os.getenv("TIMEZONE", "America/New_York"),
        api_key=os.getenv("API_KEY"),
        slack_enabled=os.getenv("SLACK_ENABLED", "false").lower() == "true",
        slack_bot_token=os.getenv("SLACK_BOT_TOKEN"),
        slack_channel_id=os.getenv("SLACK_CHANNEL_ID"),
    )


