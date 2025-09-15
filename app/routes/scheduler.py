from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any

from app.scheduler.service import get_scheduler

router = APIRouter()


@router.get("/scheduler/status")
async def get_scheduler_status() -> JSONResponse:
    """
    Get scheduler status and configuration.

    Returns:
        JSON response with scheduler status, cron expression, timezone, and run times
    """
    try:
        scheduler = get_scheduler()
        status = scheduler.get_status()

        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "scheduler": status
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get scheduler status: {str(e)}")


@router.post("/scheduler/start")
async def start_scheduler() -> JSONResponse:
    """
    Start the scheduler.

    Returns:
        JSON response confirming scheduler start
    """
    try:
        scheduler = get_scheduler()

        if scheduler._running:
            return JSONResponse(
                status_code=200,
                content={
                    "ok": True,
                    "message": "Scheduler is already running",
                    "scheduler": scheduler.get_status()
                }
            )

        await scheduler.start()

        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "message": "Scheduler started successfully",
                "scheduler": scheduler.get_status()
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start scheduler: {str(e)}")


@router.post("/scheduler/stop")
async def stop_scheduler() -> JSONResponse:
    """
    Stop the scheduler.

    Returns:
        JSON response confirming scheduler stop
    """
    try:
        scheduler = get_scheduler()

        if not scheduler._running:
            return JSONResponse(
                status_code=200,
                content={
                    "ok": True,
                    "message": "Scheduler is not running",
                    "scheduler": scheduler.get_status()
                }
            )

        await scheduler.stop()

        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "message": "Scheduler stopped successfully",
                "scheduler": scheduler.get_status()
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop scheduler: {str(e)}")


@router.post("/scheduler/restart")
async def restart_scheduler() -> JSONResponse:
    """
    Restart the scheduler.

    Returns:
        JSON response confirming scheduler restart
    """
    try:
        scheduler = get_scheduler()

        # Stop if running
        if scheduler._running:
            await scheduler.stop()

        # Start again
        await scheduler.start()

        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "message": "Scheduler restarted successfully",
                "scheduler": scheduler.get_status()
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restart scheduler: {str(e)}")


@router.post("/scheduler/test")
async def test_scheduler() -> JSONResponse:
    """
    Test the scheduler by sending a digest immediately.

    Returns:
        JSON response confirming test digest was sent
    """
    try:
        scheduler = get_scheduler()

        # Send test digest
        await scheduler._send_digest()

        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "message": "Test digest sent successfully",
                "scheduler": scheduler.get_status()
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send test digest: {str(e)}")
