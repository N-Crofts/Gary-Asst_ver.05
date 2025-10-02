"""
Action routes for external integrations.

This module provides endpoints for actions triggered by external services
like Slack buttons or webhooks.
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from datetime import datetime
from zoneinfo import ZoneInfo

from app.schemas.digest import DigestSendRequest, DigestSendResponse
from app.routes.digest import _handle_send
from app.core.config import load_config

router = APIRouter()


@router.get("/send-now")
async def send_now_action(request: Request):
    """
    Handle 'Send Now' action from Slack or other external sources.

    This endpoint provides a simple way to trigger immediate digest sending
    from external integrations like Slack buttons.
    """
    config = load_config()

    # Check if API key is required
    if config.api_key:
        provided_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
        if provided_key != config.api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    # Create send request for live data
    send_request = DigestSendRequest(
        send=True,
        source="live"
    )

    try:
        # Handle the send request
        response = await _handle_send(request, send_request)

        # Extract response data
        response_data = response.body.decode()
        import json
        response_dict = json.loads(response_data)

        # Return success response
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "message": "Digest sent successfully",
                "action": response_dict.get("action"),
                "recipients_count": response_dict.get("recipients_count", 0),
                "driver": response_dict.get("driver"),
                "timestamp": datetime.now(ZoneInfo("America/New_York")).isoformat()
            }
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "message": f"Failed to send digest: {str(e)}",
                "timestamp": datetime.now(ZoneInfo("America/New_York")).isoformat()
            }
        )


@router.get("/send-now/redirect")
async def send_now_redirect(request: Request):
    """
    Handle 'Send Now' action with redirect response.

    This endpoint is useful for Slack buttons that need to redirect
    to a confirmation page after sending.
    """
    config = load_config()

    # Check if API key is required
    if config.api_key:
        provided_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
        if provided_key != config.api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    # Create send request for live data
    send_request = DigestSendRequest(
        send=True,
        source="live"
    )

    try:
        # Handle the send request
        response = await _handle_send(request, send_request)

        # Extract response data
        response_data = response.body.decode()
        import json
        response_dict = json.loads(response_data)

        # Redirect to success page
        success_url = f"/digest/preview?source=live&sent=true&recipients={response_dict.get('recipients_count', 0)}"
        return RedirectResponse(url=success_url, status_code=302)

    except Exception as e:
        # Redirect to error page
        error_url = f"/digest/preview?source=live&error={str(e).replace(' ', '%20')}"
        return RedirectResponse(url=error_url, status_code=302)


@router.get("/preview")
async def preview_action(request: Request):
    """
    Handle 'Preview' action from Slack or other external sources.

    This endpoint provides a simple way to preview the digest
    from external integrations like Slack buttons.
    """
    # Redirect to the preview endpoint
    return RedirectResponse(url="/digest/preview?source=live", status_code=302)
