"""
Slack client for posting digest notifications.

This module provides a simple wrapper around the Slack Web API for posting
digest notifications to Slack channels.
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)


class SlackClient:
    """Simple Slack client for posting messages."""

    def __init__(self, bot_token: str, channel_id: str):
        """
        Initialize Slack client.

        Args:
            bot_token: Slack bot token (xoxb-...)
            channel_id: Slack channel ID to post to
        """
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.base_url = "https://slack.com/api"
        self.timeout = 15.0

    async def post_message(
        self,
        text: str,
        blocks: Optional[list] = None,
        attachments: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Post a message to the configured Slack channel.

        Args:
            text: Fallback text for the message
            blocks: Slack blocks for rich formatting
            attachments: Legacy attachments (deprecated)

        Returns:
            Dict containing the API response

        Raises:
            Exception: If the API call fails
        """
        url = f"{self.base_url}/chat.postMessage"
        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "channel": self.channel_id,
            "text": text
        }

        if blocks:
            payload["blocks"] = blocks
        if attachments:
            payload["attachments"] = attachments

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()

                result = await response.json()

                if not result.get("ok"):
                    error = result.get("error", "Unknown error")
                    raise Exception(f"Slack API error: {error}")

                return result

        except httpx.TimeoutException:
            raise Exception("Slack API request timed out")
        except httpx.HTTPStatusError as e:
            raise Exception(f"Slack API HTTP error: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Slack API error: {str(e)}")

    async def post_digest_notification(
        self,
        subject: str,
        meeting_count: int,
        preview_url: str,
        send_now_url: str
    ) -> Dict[str, Any]:
        """
        Post a digest notification with preview link and send now action.

        Args:
            subject: Email subject line
            meeting_count: Number of meetings in the digest
            preview_url: URL to preview the digest
            send_now_url: URL to trigger immediate send

        Returns:
            Dict containing the API response
        """
        # Create rich message blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📧 Daily Briefing Ready"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{subject}*\n\n📅 {meeting_count} meetings scheduled"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Preview Digest"
                        },
                        "url": preview_url,
                        "action_id": "preview_digest"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Send to Inbox Now"
                        },
                        "url": send_now_url,
                        "action_id": "send_now",
                        "style": "primary"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Posted at {datetime.now(ZoneInfo('America/New_York')).strftime('%I:%M %p ET')}"
                    }
                ]
            }
        ]

        # Fallback text for notifications
        fallback_text = f"Daily Briefing: {subject} ({meeting_count} meetings) - Preview: {preview_url}"

        return await self.post_message(
            text=fallback_text,
            blocks=blocks
        )

    async def test_connection(self) -> bool:
        """
        Test the Slack connection by calling auth.test.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            url = f"{self.base_url}/auth.test"
            headers = {
                "Authorization": f"Bearer {self.bot_token}",
                "Content-Type": "application/json"
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=headers)
                response.raise_for_status()

                result = await response.json()
                return result.get("ok", False)

        except Exception as e:
            logger.error(f"Slack connection test failed: {e}")
            return False


def create_slack_client() -> Optional[SlackClient]:
    """
    Create a Slack client from environment variables.

    Returns:
        SlackClient instance if properly configured, None otherwise
    """
    bot_token = os.getenv("SLACK_BOT_TOKEN")
    channel_id = os.getenv("SLACK_CHANNEL_ID")

    if not bot_token or not channel_id:
        logger.warning("Slack not configured: SLACK_BOT_TOKEN or SLACK_CHANNEL_ID missing")
        return None

    return SlackClient(bot_token=bot_token, channel_id=channel_id)


async def post_digest_to_slack(
    subject: str,
    meeting_count: int,
    base_url: str = "http://localhost:8000"
) -> bool:
    """
    Post digest notification to Slack.

    Args:
        subject: Email subject line
        meeting_count: Number of meetings
        base_url: Base URL for the application

    Returns:
        True if posted successfully, False otherwise
    """
    client = create_slack_client()
    if not client:
        logger.info("Slack not enabled or not configured")
        return False

    try:
        preview_url = f"{base_url}/digest/preview?source=live"
        send_now_url = f"{base_url}/digest/send?send=true&source=live"

        result = await client.post_digest_notification(
            subject=subject,
            meeting_count=meeting_count,
            preview_url=preview_url,
            send_now_url=send_now_url
        )

        logger.info(f"Slack notification posted successfully: {result.get('ts')}")
        return True

    except Exception as e:
        logger.error(f"Failed to post to Slack: {e}")
        return False
