from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from pymongo.database import Database

from app.dtos import (
    DatasetTemplateListResponse,
    DatasetTemplateResponse,
    DatasetResponse,
)
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.dataset_template_repository import DatasetTemplateRepository


class DatasetTemplateService:
    def __init__(self, db: Database):
        self.db = db
        self.template_repo = DatasetTemplateRepository(db)
        self.dataset_repo = DatasetRepository(db)

    def _serialize_template(self, template) -> DatasetTemplateResponse:
        payload = (
            template.model_dump(by_alias=True)
            if hasattr(template, "model_dump")
            else template
        )
        return DatasetTemplateResponse.model_validate(payload)

    def list_templates(self) -> DatasetTemplateListResponse:
        templates = self.template_repo.find_many({}, sort=[("created_at", -1)])
        return DatasetTemplateListResponse(
            total=len(templates),
            items=[self._serialize_template(template) for template in templates],
        )

    def apply_template(
        self, dataset_id: str, template_id: str, user_id: Optional[str]
    ) -> DatasetResponse:
        dataset = self.dataset_repo.find_by_id(dataset_id)
        if not dataset or (dataset.user_id and str(dataset.user_id) != user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found"
            )

        template = self.template_repo.find_by_id(template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
            )

        template_features = getattr(template, "selected_features", []) or []
        current_features = getattr(dataset, "selected_features", []) or []
        combined = list(dict.fromkeys([*current_features, *template_features]))

        updates = {
            "selected_template": str(template.id) if getattr(template, "id", None) else template_id,
            "selected_features": combined,
            "updated_at": datetime.now(timezone.utc),
        }

        updated = self.dataset_repo.update_one(dataset_id, updates)
        final = updated or dataset
        if not updated:
            # ensure we return the merged features even if update failed silently
            final.selected_template = updates["selected_template"]
            final.selected_features = combined

        payload = (
            final.model_dump(by_alias=True) if hasattr(final, "model_dump") else final
        )
        return DatasetResponse.model_validate(payload)
