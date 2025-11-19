from __future__ import annotations

from typing import List, Optional

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.database import Database

from app.dtos import RepoImportRequest, RepoResponse
from app.services.pipeline_store_service import PipelineStore
from app.services.github.github_client import get_app_github_client
from app.services.pipeline_exceptions import PipelineConfigurationError
from app.tasks.ingestion import trigger_initial_scan
from app.api.repos import (
    _serialize_repo,
)


class RepositoryService:
    def __init__(self, db: Database):
        self.db = db
        self.store = PipelineStore(db)

    def import_repository(self, user_id: str, payload: RepoImportRequest) -> dict:
        """
        Import a single repository.
        Returns the created repository document.
        """
        # Check if available
        available_repo = self.db.available_repositories.find_one(
            {"user_id": ObjectId(user_id), "full_name": payload.full_name}
        )

        installation_id = payload.installation_id
        if available_repo and available_repo.get("installation_id"):
            installation_id = available_repo.get("installation_id")

        if not installation_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This repository must be installed via the GitHub App to be imported. Please install the App for this repository first.",
            )

        try:
            with get_app_github_client(self.db, installation_id) as gh:
                repo_data = gh.get_repository(payload.full_name)
        except PipelineConfigurationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Authentication failed: {str(e)}. Please ensure you have connected installed the App.",
            )

        repo_doc = self.store.upsert_repository(
            user_id=user_id,
            provider=payload.provider,
            full_name=payload.full_name,
            default_branch=repo_data.get("default_branch", "main"),
            is_private=bool(repo_data.get("private")),
            main_lang=repo_data.get("language"),
            github_repo_id=repo_data.get("id"),
            metadata=repo_data,
            installation_id=installation_id,
            last_scanned_at=None,
        )

        trigger_initial_scan.delay(str(repo_doc["_id"]))

        self.db.available_repositories.update_one(
            {"user_id": ObjectId(user_id), "full_name": payload.full_name},
            {"$set": {"imported": True}},
        )

        return repo_doc

    def bulk_import_repositories(
        self, user_id: str, payloads: List[RepoImportRequest]
    ) -> List[dict]:
        """
        Import multiple repositories.
        Returns a list of created repository documents.
        """
        results = []

        # Pre-fetch available repos to check installation_ids
        full_names = [p.full_name for p in payloads]
        available_repos = list(
            self.db.available_repositories.find(
                {"user_id": ObjectId(user_id), "full_name": {"$in": full_names}}
            )
        )
        available_map = {r["full_name"]: r for r in available_repos}

        for payload in payloads:
            # Use payload user_id if provided (admin case), else current user
            target_user_id = payload.user_id or user_id

            available_repo = available_map.get(payload.full_name)
            installation_id = payload.installation_id

            if available_repo and available_repo.get("installation_id"):
                installation_id = available_repo.get("installation_id")

            if not installation_id:
                # Skip or log
                continue

            try:
                with get_app_github_client(self.db, installation_id) as gh:
                    repo_data = gh.get_repository(payload.full_name)

                repo_doc = self.store.upsert_repository(
                    user_id=target_user_id,
                    provider=payload.provider,
                    full_name=payload.full_name,
                    default_branch=repo_data.get("default_branch", "main"),
                    is_private=bool(repo_data.get("private")),
                    main_lang=repo_data.get("language"),
                    github_repo_id=repo_data.get("id"),
                    metadata=repo_data,
                    installation_id=installation_id,
                    last_scanned_at=None,
                )

                trigger_initial_scan.delay(str(repo_doc["_id"]))

                self.db.available_repositories.update_one(
                    {
                        "user_id": ObjectId(target_user_id),
                        "full_name": payload.full_name,
                    },
                    {"$set": {"imported": True}},
                )

                results.append(repo_doc)

            except Exception as e:
                # Log error and continue
                print(f"Failed to import {payload.full_name}: {e}")
                continue

        return results
