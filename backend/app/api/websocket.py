"""
WebSocket API for real-time updates.

This module provides WebSocket endpoints for:
- Real-time enrichment job progress updates
- Row-by-row processing events
- General broadcast events
"""

import asyncio
import json
import logging
from typing import List, Set

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings

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
        await websocket.send_json(
            {
                "type": "connected",
                "job_id": job_id,
                "message": "Connected to enrichment progress stream",
            }
        )

        # Subscribe to Redis channel for this job
        redis = await get_async_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"{REDIS_CHANNEL_PREFIX}{job_id}")

        # Listen for messages
        while True:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=30.0,  # Heartbeat every 30s
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
            await websocket.send_json(
                {
                    "type": "error",
                    "message": str(e),
                }
            )
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


class ConnectionManager:
    """Manages WebSocket connections for general event broadcasts."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._redis_client = None

    @property
    def redis_client(self):
        if self._redis_client is None:
            self._redis_client = aioredis.from_url(settings.REDIS_URL)
        return self._redis_client

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error sending message to websocket: {e}")

    async def subscribe_to_redis(self):
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe("events")
        async for message in pubsub.listen():
            if message["type"] == "message":
                await self.broadcast(message["data"].decode("utf-8"))


manager = ConnectionManager()


@router.websocket("/ws/events")
async def events_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for general event broadcasts.

    Connect to receive server-wide events published to Redis 'events' channel.
    """
    await manager.connect(websocket)

    # Create Redis subscription for this connection
    redis_client = await get_async_redis()
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("events")

    async def listen_redis():
        """Listen for Redis events and broadcast to this websocket."""
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    try:
                        await websocket.send_text(data)
                    except Exception:
                        break
        except Exception as e:
            logger.error(f"Redis listener error: {e}")

    async def receive_client():
        """Keep connection alive by receiving client messages."""
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    try:
        # Run both tasks concurrently
        redis_task = asyncio.create_task(listen_redis())
        receive_task = asyncio.create_task(receive_client())

        # Wait for either task to complete (disconnect or error)
        done, pending = await asyncio.wait(
            [redis_task, receive_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        manager.disconnect(websocket)
        try:
            await pubsub.unsubscribe("events")
            await redis_client.close()
        except Exception:
            pass
