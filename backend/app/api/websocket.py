"""
WebSocket API for real-time enrichment progress.

This module provides WebSocket endpoints for:
- Real-time enrichment job progress updates
- Row-by-row processing events
"""

import asyncio
import json
import logging
from typing import Set

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from pymongo.database import Database

from app.config import settings
from app.database.mongo import get_db
from app.repositories.enrichment_job import EnrichmentJobRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])

# Track active connections per job
active_connections: dict[str, Set[WebSocket]] = {}

REDIS_CHANNEL_PREFIX = "enrichment:progress:"


async def get_async_redis():
    """Get async Redis client."""
    return await aioredis.from_url(settings.REDIS_URL)


@router.websocket("/ws/enrichment/{job_id}")
async def enrichment_progress_websocket(
    websocket: WebSocket,
    job_id: str,
):
    """
    WebSocket endpoint for real-time enrichment progress.

    Connect to receive live updates about enrichment job progress.

    Events received:
    - {"type": "connected", "job_id": "..."}
    - {"type": "progress", "processed_rows": 50, "total_rows": 100, ...}
    - {"type": "row_complete", "row_index": 42, "success": true, ...}
    - {"type": "complete", "status": "completed", ...}
    - {"type": "error", "message": "..."}

    The connection will automatically close when the job completes.
    """
    await websocket.accept()

    # Track connection
    if job_id not in active_connections:
        active_connections[job_id] = set()
    active_connections[job_id].add(websocket)

    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "job_id": job_id,
            "message": "Connected to enrichment progress stream",
        })

        # Subscribe to Redis channel for this job
        redis = await get_async_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"{REDIS_CHANNEL_PREFIX}{job_id}")

        # Listen for messages
        while True:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=30.0  # Heartbeat every 30s
                )

                if message:
                    data = message.get("data")
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    if data:
                        event = json.loads(data)
                        await websocket.send_json(event)

                        # Close on completion
                        if event.get("type") in ("complete", "error"):
                            break
                else:
                    # Send heartbeat
                    await websocket.send_json({"type": "heartbeat"})

            except asyncio.TimeoutError:
                # Send heartbeat on timeout
                await websocket.send_json({"type": "heartbeat"})
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for job {job_id}")
    except Exception as e:
        logger.error(f"WebSocket error for job {job_id}: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except Exception:
            pass
    finally:
        # Cleanup
        if job_id in active_connections:
            active_connections[job_id].discard(websocket)
            if not active_connections[job_id]:
                del active_connections[job_id]
        
        try:
            await pubsub.unsubscribe(f"{REDIS_CHANNEL_PREFIX}{job_id}")
            await redis.close()
        except Exception:
            pass


@router.websocket("/ws/enrichment/{job_id}/polling")
async def enrichment_polling_websocket(
    websocket: WebSocket,
    job_id: str,
):
    """
    Simpler WebSocket that polls database for progress.
    
    Use this as fallback if Redis pub/sub is not available.
    Polls every 2 seconds.
    """
    await websocket.accept()

    try:
        # Get database connection (sync)
        from app.database.mongo import get_database
        db = get_database()
        job_repo = EnrichmentJobRepository(db)

        await websocket.send_json({
            "type": "connected",
            "job_id": job_id,
            "message": "Connected (polling mode)",
        })

        last_processed = -1

        while True:
            # Poll database
            job = job_repo.find_by_id(job_id)
            
            if not job:
                await websocket.send_json({
                    "type": "error",
                    "message": "Job not found",
                })
                break

            # Send update if changed
            if job.processed_rows != last_processed:
                last_processed = job.processed_rows
                await websocket.send_json({
                    "type": "progress",
                    "job_id": job_id,
                    "status": job.status,
                    "processed_rows": job.processed_rows,
                    "total_rows": job.total_rows,
                    "enriched_rows": job.enriched_rows,
                    "failed_rows": job.failed_rows,
                    "progress_percent": job.progress_percent,
                })

            # Check if complete
            if job.is_complete:
                await websocket.send_json({
                    "type": "complete",
                    "job_id": job_id,
                    "status": job.status,
                    "total_rows": job.total_rows,
                    "enriched_rows": job.enriched_rows,
                    "failed_rows": job.failed_rows,
                    "output_file": job.output_file,
                    "error": job.error,
                })
                break

            # Wait before next poll
            await asyncio.sleep(2)

    except WebSocketDisconnect:
        logger.info(f"Polling WebSocket disconnected for job {job_id}")
    except Exception as e:
        logger.error(f"Polling WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
