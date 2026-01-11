from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from app.database.mongo import get_db
from app.dtos.training_scenario import (
    TrainingScenarioCreate,
    TrainingScenarioResponse,
    TrainingScenarioUpdate,
)
from app.entities.training_scenario import ScenarioStatus
from app.entities.user import User
from app.middleware.auth import get_current_user
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.services.training_scenario_service import TrainingScenarioService

router = APIRouter()


# ============================================================================
# Preview Builds (Wizard Step 1)
# ============================================================================


@router.get("/preview-builds")
def preview_builds(
    date_start: Optional[datetime] = None,
    date_end: Optional[datetime] = None,
    languages: Optional[str] = Query(None, description="Comma-separated languages"),
    conclusions: Optional[str] = Query(
        None, description="Comma-separated conclusions (success,failure)"
    ),
    ci_provider: Optional[str] = Query(None, description="CI provider filter"),
    exclude_bots: bool = Query(True, description="Exclude bot commits"),
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
) -> Dict[str, Any]:
    """
    Preview builds matching filter criteria.

    Used by Training Scenario wizard to preview available builds before creating a scenario.
    Returns paginated builds and aggregate stats.
    """
    raw_repo_repo = RawRepositoryRepository(db)
    raw_build_run_repo = RawBuildRunRepository(db)

    # Parse comma-separated values
    conclusions_list = conclusions.split(",") if conclusions else None
    languages_list = languages.split(",") if languages else None

    # Get repo IDs filtered by language
    repo_ids = None
    if languages_list:
        # Find repos matching the languages
        language_query = {
            "main_lang": {"$in": [lang.lower() for lang in languages_list]}
        }
        matching_repos = list(raw_repo_repo.collection.find(language_query, {"_id": 1}))
        repo_ids = [r["_id"] for r in matching_repos]

        # If no repos match language, return empty result
        if not repo_ids:
            return {
                "builds": [],
                "stats": {
                    "total_builds": 0,
                    "total_repos": 0,
                    "outcome_distribution": {"success": 0, "failure": 0},
                },
                "pagination": {"skip": skip, "limit": limit, "total": 0},
            }

    # Get builds with filters
    builds, stats = raw_build_run_repo.find_with_filters(
        date_start=date_start,
        date_end=date_end,
        conclusions=conclusions_list,
        ci_provider=ci_provider,
        exclude_bots=exclude_bots,
        repo_ids=repo_ids,
        skip=skip,
        limit=limit,
    )

    # Serialize builds
    builds_data = []
    unique_repos: dict = {}  # repo_id -> repo_info
    for build in builds:
        # Collect unique repos
        repo_id_str = str(build.raw_repo_id)
        if repo_id_str not in unique_repos:
            unique_repos[repo_id_str] = {
                "id": repo_id_str,
                "full_name": build.repo_name or "",
            }

        builds_data.append(
            {
                "id": str(build.id),
                "raw_repo_id": repo_id_str,
                "repo_name": build.repo_name,
                "branch": build.branch,
                "commit_sha": build.commit_sha[:8] if build.commit_sha else "",
                "conclusion": (
                    build.conclusion.value
                    if hasattr(build.conclusion, "value")
                    else build.conclusion
                ),
                "run_started_at": (
                    build.run_started_at.isoformat() if build.run_started_at else None
                ),
                "duration_seconds": build.duration_seconds,
            }
        )

    # Add repos to stats
    stats["repos"] = list(unique_repos.values())

    return {
        "builds": builds_data,
        "stats": stats,
        "pagination": {
            "skip": skip,
            "limit": limit,
            "total": stats.get("total_builds", 0),
        },
    }


@router.get("/", response_model=List[TrainingScenarioResponse])
def list_scenarios(
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    q: Optional[str] = None,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
) -> List[TrainingScenarioResponse]:
    """List training scenarios."""
    service = TrainingScenarioService(db)

    # Validate status enum if provided
    status_enum = None
    if status:
        try:
            status_enum = ScenarioStatus(status)
        except ValueError:
            pass  # Ignore invalid status or handle error

    scenarios, _ = service.list_scenarios(
        user_id=str(current_user.id),
        skip=skip,
        limit=limit,
        status_filter=status_enum,
        q=q,
    )
    return scenarios


@router.post("/", response_model=TrainingScenarioResponse)
def create_scenario(
    data: TrainingScenarioCreate,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
) -> TrainingScenarioResponse:
    """Create a new training scenario."""
    service = TrainingScenarioService(db)
    return service.create_scenario(str(current_user.id), data)


@router.get("/{scenario_id}", response_model=TrainingScenarioResponse)
def get_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
) -> TrainingScenarioResponse:
    """Get training scenario details."""
    service = TrainingScenarioService(db)
    return service.get_scenario(scenario_id, str(current_user.id))


@router.put("/{scenario_id}", response_model=TrainingScenarioResponse)
def update_scenario(
    scenario_id: str,
    data: TrainingScenarioUpdate,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
) -> TrainingScenarioResponse:
    """Update training scenario."""
    service = TrainingScenarioService(db)
    return service.update_scenario(scenario_id, str(current_user.id), data)


@router.delete("/{scenario_id}")
def delete_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
) -> Dict[str, bool]:
    """Delete training scenario."""
    service = TrainingScenarioService(db)
    service.delete_scenario(scenario_id, str(current_user.id))
    return {"deleted": True}


# ============================================================================
# Pipeline Actions
# ============================================================================


@router.post("/{scenario_id}/ingest")
def start_ingestion(
    scenario_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
) -> Dict[str, Any]:
    """Start ingestion phase (Phase 1)."""
    service = TrainingScenarioService(db)
    return service.start_ingestion(scenario_id, str(current_user.id))


@router.post("/{scenario_id}/process")
def start_processing(
    scenario_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
) -> Dict[str, Any]:
    """Start processing phase (Phase 2)."""
    service = TrainingScenarioService(db)
    return service.start_processing(scenario_id, str(current_user.id))


@router.post("/{scenario_id}/generate")
def generate_dataset(
    scenario_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
) -> Dict[str, Any]:
    """Generate dataset (Phase 3 - Split & Export)."""
    service = TrainingScenarioService(db)
    return service.generate_dataset(scenario_id, str(current_user.id))


# ============================================================================
# Artifacts
# ============================================================================


@router.get("/{scenario_id}/splits")
def get_scenario_splits(
    scenario_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
):
    """Get generated split files."""
    service = TrainingScenarioService(db)
    return service.get_scenario_splits(scenario_id, str(current_user.id))


# ============================================================================
# Build Listing
# ============================================================================


@router.get("/{scenario_id}/ingestion-builds")
def get_ingestion_builds(
    scenario_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(
        None,
        description="Filter by status: pending, ingesting, ingested, missing_resource",
    ),
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
):
    """
    List ingestion builds for a scenario (Phase 1).

    Shows TrainingIngestionBuild data with resource status breakdown.
    """
    service = TrainingScenarioService(db)
    return service.get_ingestion_builds(
        scenario_id=scenario_id,
        user_id=str(current_user.id),
        skip=skip,
        limit=limit,
        status_filter=status,
    )


@router.get("/{scenario_id}/enrichment-builds")
def get_enrichment_builds(
    scenario_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    extraction_status: Optional[str] = Query(
        None,
        description="Filter by status: pending, completed, failed, partial",
    ),
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
):
    """
    List enrichment builds for a scenario (Phase 2).

    Shows TrainingEnrichmentBuild data with extraction status and features.
    """
    service = TrainingScenarioService(db)
    return service.get_enrichment_builds(
        scenario_id=scenario_id,
        user_id=str(current_user.id),
        skip=skip,
        limit=limit,
        extraction_status=extraction_status,
    )


@router.get("/{scenario_id}/scan-status")
def get_scan_status(
    scenario_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
):
    """
    Get scan status summary for a scenario.

    Returns counts of scans completed/pending/failed.
    """
    service = TrainingScenarioService(db)
    return service.get_scan_status(
        scenario_id=scenario_id,
        user_id=str(current_user.id),
    )


# ============================================================================
# Retry Actions
# ============================================================================


@router.post("/{scenario_id}/retry-ingestion")
def retry_ingestion(
    scenario_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
):
    """Retry failed ingestion builds."""
    service = TrainingScenarioService(db)
    return service.retry_ingestion(scenario_id, str(current_user.id))


@router.post("/{scenario_id}/retry-processing")
def retry_processing(
    scenario_id: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
):
    """Retry failed processing builds."""
    service = TrainingScenarioService(db)
    return service.retry_processing(scenario_id, str(current_user.id))


# ============================================================================
# Commit Scans
# ============================================================================


@router.get("/{scenario_id}/commit-scans")
def get_commit_scans(
    scenario_id: str,
    tool_type: Optional[str] = Query(
        None, description="Filter by tool: trivy or sonarqube"
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
) -> Dict[str, Any]:
    """
    List commit scans for a scenario.

    Returns paginated list of scans for Trivy and/or SonarQube.
    """
    from bson import ObjectId
    from app.repositories.trivy_commit_scan import TrivyCommitScanRepository
    from app.repositories.sonar_commit_scan import SonarCommitScanRepository

    # Verify scenario access
    service = TrainingScenarioService(db)
    service.get_scenario(scenario_id, str(current_user.id))

    scenario_oid = ObjectId(scenario_id)
    result = {}

    # Fetch Trivy scans
    if tool_type is None or tool_type == "trivy":
        trivy_repo = TrivyCommitScanRepository(db)
        trivy_items, trivy_total = trivy_repo.list_by_scenario(
            scenario_oid, skip, limit
        )
        result["trivy"] = {
            "items": [
                {
                    "id": str(scan.id),
                    "commit_sha": scan.commit_sha,
                    "repo_full_name": scan.repo_full_name,
                    "status": (
                        scan.status.value
                        if hasattr(scan.status, "value")
                        else scan.status
                    ),
                    "error_message": scan.error_message,
                    "builds_affected": scan.builds_affected,
                    "retry_count": scan.retry_count,
                    "started_at": (
                        scan.started_at.isoformat() if scan.started_at else None
                    ),
                    "completed_at": (
                        scan.completed_at.isoformat() if scan.completed_at else None
                    ),
                }
                for scan in trivy_items
            ],
            "total": trivy_total,
            "skip": skip,
            "limit": limit,
        }

    # Fetch SonarQube scans
    if tool_type is None or tool_type == "sonarqube":
        sonar_repo = SonarCommitScanRepository(db)
        sonar_items, sonar_total = sonar_repo.list_by_scenario(
            scenario_oid, skip, limit
        )
        result["sonarqube"] = {
            "items": [
                {
                    "id": str(scan.id),
                    "commit_sha": scan.commit_sha,
                    "repo_full_name": scan.repo_full_name,
                    "status": (
                        scan.status.value
                        if hasattr(scan.status, "value")
                        else scan.status
                    ),
                    "error_message": scan.error_message,
                    "builds_affected": scan.builds_affected,
                    "retry_count": scan.retry_count,
                    "started_at": (
                        scan.started_at.isoformat() if scan.started_at else None
                    ),
                    "completed_at": (
                        scan.completed_at.isoformat() if scan.completed_at else None
                    ),
                }
                for scan in sonar_items
            ],
            "total": sonar_total,
            "skip": skip,
            "limit": limit,
        }

    return result


@router.post("/{scenario_id}/commit-scans/{commit_sha}/retry")
def retry_commit_scan(
    scenario_id: str,
    commit_sha: str,
    tool_type: str = Query(..., description="Tool to retry: trivy or sonarqube"),
    current_user: User = Depends(get_current_user),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
) -> Dict[str, Any]:
    """
    Retry a failed commit scan.
    """
    from bson import ObjectId
    from app.repositories.trivy_commit_scan import TrivyCommitScanRepository
    from app.repositories.sonar_commit_scan import SonarCommitScanRepository

    # Verify scenario access
    service = TrainingScenarioService(db)
    service.get_scenario(scenario_id, str(current_user.id))

    scenario_oid = ObjectId(scenario_id)

    if tool_type == "trivy":
        repo = TrivyCommitScanRepository(db)
        scan = repo.find_by_scenario_and_commit(scenario_oid, commit_sha)
        if not scan:
            return {"success": False, "message": "Scan not found"}
        repo.increment_retry(scan.id)
        # TODO: Dispatch scan task
        return {"success": True, "message": "Trivy scan queued for retry"}

    elif tool_type == "sonarqube":
        repo = SonarCommitScanRepository(db)
        scan = repo.find_by_scenario_and_commit(scenario_oid, commit_sha)
        if not scan:
            return {"success": False, "message": "Scan not found"}
        repo.increment_retry(scan.id)
        # TODO: Dispatch scan task
        return {"success": True, "message": "SonarQube scan queued for retry"}

    return {"success": False, "message": f"Unknown tool type: {tool_type}"}
