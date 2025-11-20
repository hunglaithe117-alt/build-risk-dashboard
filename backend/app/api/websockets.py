"""WebSocket endpoints for real-time updates."""

import asyncio
import json
import logging
from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import redis.asyncio as redis

from app.config import settings

router = APIRouter(prefix="/ws", tags=["WebSockets"])
logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.redis_client = redis.from_url(settings.REDIS_URL)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error sending message to websocket: {e}")
                # Consider removing the connection if it's dead
                pass

    async def subscribe_to_redis(self):
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe("events")
        async for message in pubsub.listen():
            if message["type"] == "message":
                await self.broadcast(message["data"].decode("utf-8"))


manager = ConnectionManager()


@router.websocket("/events")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# Start Redis listener in background
@router.on_event("startup")
async def startup_event():
    asyncio.create_task(manager.subscribe_to_redis())
