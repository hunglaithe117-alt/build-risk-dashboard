from fastapi import APIRouter, Depends

from app.middleware.auth import get_current_user
from app.services.data_source_service import DataSourceService
from app.dtos.data_source import (
    DataSourceResponse,
    DataSourceListResponse,
    DataSourceDetailResponse,
    DataSourceFeaturesResponse,
)

# Import sources to register them
from app.pipeline.sources import git, build_log, github_api, sonarqube, trivy

router = APIRouter(prefix="/data-sources", tags=["Data Sources"])
service = DataSourceService()


@router.get("", response_model=DataSourceListResponse)
async def list_data_sources(_current_user: dict = Depends(get_current_user)):
    sources = service.list_data_sources()
    return DataSourceListResponse(
        sources=[DataSourceResponse(**s) for s in sources],
        total=len(sources),
    )


@router.get("/{source_type}", response_model=DataSourceDetailResponse)
async def get_data_source(
    source_type: str,
    _current_user: dict = Depends(get_current_user),
):
    result = service.get_data_source(source_type)
    if "error" in result:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=result["error"])
    return DataSourceDetailResponse(**result)


@router.get("/{source_type}/features", response_model=DataSourceFeaturesResponse)
async def get_data_source_features(
    source_type: str,
    _current_user: dict = Depends(get_current_user),
):
    result = service.get_data_source_features(source_type)
    if "error" in result:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=result["error"])
    return DataSourceFeaturesResponse(**result)
