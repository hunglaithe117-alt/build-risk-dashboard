from typing import List

from fastapi import HTTPException, status
from pymongo.database import Database

from app.dtos import (
    DatasetTemplateListResponse,
    DatasetTemplateResponse,
)
from app.repositories.dataset_template_repository import DatasetTemplateRepository


class DatasetTemplateService:
    def __init__(self, db: Database):
        self.db = db
        self.template_repo = DatasetTemplateRepository(db)

    def _serialize_template(self, template) -> DatasetTemplateResponse:
        payload = (
            template.model_dump(by_alias=True) if hasattr(template, "model_dump") else template
        )
        return DatasetTemplateResponse.model_validate(payload)

    def list_templates(self) -> DatasetTemplateListResponse:
        """List all available dataset templates."""
        templates = self.template_repo.find_many({}, sort=[("created_at", -1)])
        return DatasetTemplateListResponse(
            total=len(templates),
            items=[self._serialize_template(template) for template in templates],
        )

    def get_template(self, template_id: str) -> DatasetTemplateResponse:
        """Get a single template by ID."""
        template = self.template_repo.find_by_id(template_id)
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
        return self._serialize_template(template)

    def get_template_by_name(self, name: str) -> DatasetTemplateResponse:
        """Get a single template by name."""
        template = self.template_repo.find_by_name(name)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template '{name}' not found",
            )
        return self._serialize_template(template)

    def get_template_features(self, template_id: str) -> List[str]:
        """Get the list of features from a template."""
        template = self.template_repo.find_by_id(template_id)
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
        return getattr(template, "feature_names", []) or []

    def get_required_resources_for_template(self, template_name: str = "Risk Prediction") -> set:
        """Get required resources based on dataset template.

        Args:
            template_name: Template name to look up (default: "Risk Prediction")

        Returns:
            Set of required resource names for feature extraction
        """
        from app.tasks.pipeline.feature_dag._metadata import get_required_resources_for_features
        from app.tasks.pipeline.shared.resources import FeatureResource

        template = self.template_repo.find_by_name(template_name)
        if template and template.feature_names:
            feature_set = set(template.feature_names)
            return get_required_resources_for_features(feature_set)
        return {r.value for r in FeatureResource}
