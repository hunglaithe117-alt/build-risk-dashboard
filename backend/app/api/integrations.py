import json

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
)
from pymongo.database import Database

from app.database.mongo import get_db
from app.services.sonar_webhook_service import SonarWebhookService

router = APIRouter(prefix="/integrations", tags=["Integrations"])


@router.post("/webhooks/sonarqube/pipeline")
async def sonarqube_pipeline_webhook(
    request: Request,
    db: Database = Depends(get_db),
    x_sonar_webhook_hmac_sha256: str = Header(default=None),
    x_sonar_secret: str = Header(default=None),
):
    body = await request.body()

    service = SonarWebhookService(db)
    service.validate_signature(body, x_sonar_webhook_hmac_sha256, x_sonar_secret)

    payload = json.loads(body.decode("utf-8") or "{}")

    component_key = payload.get("project", {}).get("key")
    if not component_key:
        raise HTTPException(status_code=400, detail="project key missing")

    task_status = payload.get("status")

    return service.handle_pipeline_webhook(component_key, task_status)
