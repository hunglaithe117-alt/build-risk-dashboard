from typing import Optional

from .base import PyObjectId
from .base_build import BaseBuildSample, ExtractionStatus


class EnrichmentBuild(BaseBuildSample):
    enrichment_repo_id: PyObjectId
    dataset_id: PyObjectId
    version_id: Optional[PyObjectId] = None
    build_id_from_csv: str

    class Config:
        collection = "enrichment_builds"
        use_enum_values = True


__all__ = ["EnrichmentBuild", "ExtractionStatus"]
