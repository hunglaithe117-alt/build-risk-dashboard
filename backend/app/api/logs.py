from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

LOKI_URL = "http://loki:3100"


@router.get("/logs")
async def get_logs(
    query: str = Query('{container_name=~".+"}', description="LogQL query"),
    limit: int = Query(100, description="Number of logs to return"),
    start: Optional[int] = Query(None, description="Start time in nanoseconds"),
    end: Optional[int] = Query(None, description="End time in nanoseconds"),
    direction: str = Query(
        "backward", description="Direction of logs (forward/backward)"
    ),
) -> Dict[str, Any]:
    """
    Proxy log queries to Loki.
    """
    params = {
        "query": query,
        "limit": limit,
        "direction": direction,
    }
    if start:
        params["start"] = start
    if end:
        params["end"] = end

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{LOKI_URL}/loki/api/v1/query_range", params=params
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Loki query failed: {response.text}",
                )

            return response.json()

    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503, detail=f"Failed to connect to Loki: {str(e)}"
        )
