from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.dtos import DashboardMetrics, DashboardSummaryResponse, RepoDistributionEntry
from app.dtos.dashboard import (
    AdminDashboardExtras,
    DashboardLayoutResponse,
    DatasetEnrichmentStats,
    MonitoringSummary,
    WidgetConfigDto,
)
from app.entities.user_dashboard_layout import (
    DEFAULT_WIDGETS,
    UserDashboardLayout,
    WidgetConfig,
)
from app.repositories.training_scenario import TrainingScenarioRepository
from app.repositories.user_dashboard_layout import UserDashboardLayoutRepository


class DashboardService:
    def __init__(self, db: Database):
        self.db = db
        self.build_collection = db["model_builds"]
        self.repo_collection = db["repositories"]
        self.layout_repo = UserDashboardLayoutRepository(db)
        self._scenario_repo = TrainingScenarioRepository(db)

    def get_summary(
        self, current_user: Optional[dict] = None
    ) -> DashboardSummaryResponse:
        """
        Get dashboard summary with RBAC filtering.

        - Admin: sees all repos and builds
        - User: sees only repos in their github_accessible_repos
        """
        user_role = current_user.get("role", "user") if current_user else "admin"
        accessible_repos = (
            current_user.get("github_accessible_repos", []) if current_user else []
        )

        # Base repo filter
        repo_filter: dict = {"status": "imported"}

        # For non-admin users, filter by accessible repos
        if user_role != "admin" and accessible_repos:
            repo_filter["full_name"] = {"$in": accessible_repos}

        # 1. Get repos based on filter
        repos = list(self.repo_collection.find(repo_filter))
        repo_ids = [repo["_id"] for repo in repos]

        # Build filter for RBAC (admin sees all, users see filtered)
        build_filter = {"repo_id": {"$in": repo_ids}} if user_role != "admin" else {}

        # 2. Calculate total builds
        total_builds = self.build_collection.count_documents(build_filter)

        # 3. Success rate
        success_filter = {**build_filter, "tr_status": "passed"}
        successful_builds = self.build_collection.count_documents(success_filter)
        success_rate = (
            (successful_builds / total_builds * 100) if total_builds > 0 else 0.0
        )

        # 4. Average duration
        pipeline = [
            {"$match": {**build_filter, "tr_duration": {"$ne": None}}},
            {"$group": {"_id": None, "avg_duration": {"$avg": "$tr_duration"}}},
        ]
        avg_duration_result = list(self.build_collection.aggregate(pipeline))
        avg_duration_seconds = (
            avg_duration_result[0]["avg_duration"] if avg_duration_result else 0
        )
        avg_duration_minutes = avg_duration_seconds / 60 if avg_duration_seconds else 0

        # 5. Repo distribution (already filtered)
        repo_distribution = []
        for repo in repos:
            repo_id = repo["_id"]
            build_count = self.build_collection.count_documents({"repo_id": repo_id})
            repo_distribution.append(
                RepoDistributionEntry(
                    id=str(repo_id), repository=repo["full_name"], builds=build_count
                )
            )

        # Sort by builds desc
        repo_distribution.sort(key=lambda x: x.builds, reverse=True)

        # 6. Count build sources (shared resource - all users see total count)
        # Per RBAC: only admins manage build_sources, users don't have VIEW_DATASETS permission
        dataset_count = self.db["build_sources"].count_documents({})

        # 7. Admin extras (only for admin role)
        admin_extras = None
        if user_role == "admin":
            admin_extras = self._get_admin_extras()

        return DashboardSummaryResponse(
            metrics=DashboardMetrics(
                total_builds=total_builds,
                success_rate=success_rate,
                average_duration_minutes=avg_duration_minutes,
            ),
            trends=[],  # Can be implemented later
            repo_distribution=repo_distribution,
            dataset_count=dataset_count,
            admin_extras=admin_extras,
        )

    # TODO: Update implement it not meaningful
    def _get_admin_extras(self) -> AdminDashboardExtras:
        """Get admin-only dashboard extras: dataset enrichment stats and monitoring."""
        # Dataset Enrichment stats (Now mapped to Training Scenarios)
        scenario_collection = self.db["training_scenarios"]
        source_build_collection = self.db["source_builds"]

        active_projects = scenario_collection.count_documents({})
        processing_versions = scenario_collection.count_documents(
            {
                "status": {
                    "$in": [
                        "queued",
                        "filtering",
                        "ingesting",
                        "processing",
                        "splitting",
                    ]
                }
            }
        )
        total_enriched_builds = source_build_collection.count_documents({})

        # Monitoring stats - queue depth and workers
        # We'll use simplified stats here, real stats come from monitoring API
        from datetime import datetime, timedelta

        logs_collection = self.db["system_logs"]
        now = datetime.utcnow()
        day_ago = now - timedelta(hours=24)

        error_count_24h = logs_collection.count_documents(
            {"level": "ERROR", "timestamp": {"$gte": day_ago}}
        )

        # Count users
        users_collection = self.db["users"]
        total_users = users_collection.count_documents({})

        return AdminDashboardExtras(
            dataset_enrichment=DatasetEnrichmentStats(
                active_projects=active_projects,
                processing_versions=processing_versions,
                total_enriched_builds=total_enriched_builds,
            ),
            monitoring=MonitoringSummary(
                celery_workers=0,  # Will be fetched separately if needed
                queue_depth=0,  # Will be fetched separately if needed
                error_count_24h=error_count_24h,
            ),
            total_users=total_users,
        )

    def _widget_config_to_dto(self, widget: WidgetConfig) -> WidgetConfigDto:
        """Convert WidgetConfig entity to DTO."""
        return WidgetConfigDto(
            widget_id=widget.widget_id,
            widget_type=widget.widget_type,
            title=widget.title,
            enabled=widget.enabled,
            x=widget.x,
            y=widget.y,
            w=widget.w,
            h=widget.h,
        )

    def get_layout(self, user_id: ObjectId) -> DashboardLayoutResponse:
        """Get dashboard layout for a user."""
        layout = self.layout_repo.find_by_user(user_id)

        if not layout:
            # Return default layout for new users
            return DashboardLayoutResponse(
                widgets=[self._widget_config_to_dto(w) for w in DEFAULT_WIDGETS]
            )

        return DashboardLayoutResponse(
            widgets=[self._widget_config_to_dto(w) for w in layout.widgets]
        )

    def save_layout(
        self, user_id: ObjectId, widgets: List[WidgetConfigDto]
    ) -> DashboardLayoutResponse:
        """Save dashboard layout for a user."""
        # Convert request widgets to entity widgets
        widget_configs = [
            WidgetConfig(
                widget_id=w.widget_id,
                widget_type=w.widget_type,
                title=w.title,
                enabled=w.enabled,
                x=w.x,
                y=w.y,
                w=w.w,
                h=w.h,
            )
            for w in widgets
        ]

        layout = UserDashboardLayout(user_id=user_id, widgets=widget_configs)
        saved = self.layout_repo.upsert_by_user(user_id, layout)

        return DashboardLayoutResponse(
            widgets=[self._widget_config_to_dto(w) for w in saved.widgets]
        )
