"""Dashboard DTOs for analytics and metrics"""

from typing import List, Optional

from pydantic import BaseModel


class DashboardMetrics(BaseModel):
    total_builds: int
    success_rate: float
    average_duration_minutes: float


class DashboardTrendPoint(BaseModel):
    date: str
    builds: int
    failures: int


class RepoDistributionEntry(BaseModel):
    id: str
    repository: str
    builds: int


# Admin-only DTOs


class DatasetEnrichmentStats(BaseModel):
    """Stats for Dataset Enrichment pipeline (Admin only)."""

    active_projects: int = 0
    processing_versions: int = 0
    total_enriched_builds: int = 0


class MonitoringSummary(BaseModel):
    """Summary of system monitoring metrics (Admin only)."""

    celery_workers: int = 0
    queue_depth: int = 0
    error_count_24h: int = 0


class AdminDashboardExtras(BaseModel):
    """Extra metrics only visible to Admin."""

    dataset_enrichment: DatasetEnrichmentStats
    monitoring: MonitoringSummary
    total_users: int = 0


class DashboardSummaryResponse(BaseModel):
    metrics: DashboardMetrics
    trends: List[DashboardTrendPoint]
    repo_distribution: List[RepoDistributionEntry]
    dataset_count: int = 0
    # Admin-only extras (None for regular users)
    admin_extras: Optional[AdminDashboardExtras] = None


# Dashboard Layout DTOs


class WidgetConfigDto(BaseModel):
    """DTO for widget configuration."""

    widget_id: str
    widget_type: str
    title: str
    enabled: bool = True
    x: int = 0
    y: int = 0
    w: int = 1
    h: int = 1


class DashboardLayoutResponse(BaseModel):
    """Response containing user's dashboard layout."""

    widgets: list[WidgetConfigDto]


class DashboardLayoutUpdateRequest(BaseModel):
    """Request to update dashboard layout."""

    widgets: list[WidgetConfigDto]


class WidgetDefinition(BaseModel):
    """Definition of an available widget."""

    widget_id: str
    widget_type: str
    title: str
    description: str
    default_w: int = 1
    default_h: int = 1
