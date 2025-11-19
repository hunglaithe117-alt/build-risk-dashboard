from typing import List, Set

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.database import Database

from app.services.github.github_client import get_app_github_client
from app.services.pipeline_store_service import PipelineStore


def sync_user_available_repos(db: Database, user_id: str) -> List[str]:
    """
    Sync available repositories for a user from their GitHub App installations.
    Returns a list of full_names of repositories found.
    """
    store = PipelineStore(db)
    seen_repos: Set[str] = set()

    identity = db.oauth_identities.find_one(
        {"user_id": ObjectId(user_id), "provider": "github"}
    )

    if not identity:
        return []

    github_login = identity.get("profile", {}).get("login") or identity.get(
        "account_login"
    )

    if github_login:
        # Find installations for this user
        # We look for installations where the account_login matches the user's login
        # TODO: For Organization installations, we need a way to know if the user has access.
        # Currently, we only sync if the user is the "owner" of the installation account.
        installations = db.github_installations.find({"account_login": github_login})

        for inst in installations:
            inst_id = inst["installation_id"]
            try:
                with get_app_github_client(db, inst_id) as gh:
                    resp = gh._rest_request(
                        "GET", "/installation/repositories", params={"per_page": 100}
                    )
                    app_repos = resp.get("repositories", [])

                    for repo in app_repos:
                        full_name = repo.get("full_name")
                        if not full_name:
                            continue

                        # Check if already imported
                        is_imported = False
                        existing_imported = db.repositories.find_one(
                            {"full_name": full_name, "user_id": ObjectId(user_id)}
                        )
                        if existing_imported:
                            is_imported = True

                        repo_data = repo.copy()
                        repo_data["imported"] = is_imported

                        store.upsert_available_repository(
                            user_id=user_id,
                            repo_data=repo_data,
                            installation_id=inst_id,
                        )
                        seen_repos.add(full_name)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to sync app repositories for installation {inst_id}: {str(e)}",
                )

    store.delete_stale_available_repositories(user_id, list(seen_repos))

    return list(seen_repos)
