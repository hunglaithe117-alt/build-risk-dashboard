"""Dashboard DTOs for analytics and metrics"""

from typing import List

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


class DashboardSummaryResponse(BaseModel):
    metrics: DashboardMetrics
    trends: List[DashboardTrendPoint]
    repo_distribution: List[RepoDistributionEntry]
    dataset_count: int = 0


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
