"""
Team Membership Node.

Extracts team membership metrics:
- gh_team_size: Number of unique contributors in last 90 days
- gh_by_core_team_member: Whether the build author is a core team member
"""

import logging
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Set

from app.pipeline.features import FeatureNode
from app.pipeline.core.registry import register_feature
from app.pipeline.core.context import ExecutionContext
from app.pipeline.resources import ResourceNames
from app.pipeline.resources.git_repo import GitRepoHandle

logger = logging.getLogger(__name__)


@register_feature(
    name="team_membership",
    requires_resources={ResourceNames.GIT_REPO},
    provides={
        "gh_team_size",
        "gh_by_core_team_member",
    },
    group="git",
    priority=5,
)
class TeamMembershipNode(FeatureNode):
    """
    Calculates team membership metrics.

    Core team = Direct committers (excluding PR merges) + PR mergers
    """

    LOOKBACK_DAYS = 90

    def extract(self, context: ExecutionContext) -> Dict[str, Any]:
        git_handle: GitRepoHandle = context.get_resource(ResourceNames.GIT_REPO)

        if not git_handle.is_commit_available:
            return {"gh_team_size": 0, "gh_by_core_team_member": False}

        repo = git_handle.repo
        effective_sha = git_handle.effective_sha
        build_sample = context.build_sample
        db = context.db

        # Get reference date
        try:
            current_commit = repo.commit(effective_sha)
        except Exception:
            return {"gh_team_size": 0, "gh_by_core_team_member": False}

        ref_date = getattr(build_sample, "created_at", None) or getattr(
            build_sample, "gh_build_started_at", None
        )
        if not ref_date:
            ref_date = datetime.fromtimestamp(
                current_commit.committed_date, tz=timezone.utc
            )
        if ref_date.tzinfo is None:
            ref_date = ref_date.replace(tzinfo=timezone.utc)

        start_date = ref_date - timedelta(days=self.LOOKBACK_DAYS)

        # 1. Direct committers (excluding PR merges)
        committer_names = self._get_direct_committers(
            git_handle.path, start_date, ref_date
        )

        # 2. PR mergers
        merger_logins = self._get_pr_mergers(
            db, str(build_sample.repo_id), start_date, ref_date
        )

        core_team = committer_names | merger_logins
        gh_team_size = len(core_team)

        # Check if build author is in core team
        is_core_member = False
        try:
            trigger_commit = repo.commit(effective_sha)
            author_name = trigger_commit.author.name
            committer_name = trigger_commit.committer.name
            if author_name in core_team or committer_name in core_team:
                is_core_member = True
        except Exception:
            pass

        return {
            "gh_team_size": gh_team_size,
            "gh_by_core_team_member": is_core_member,
        }

    def _get_direct_committers(
        self, repo_path: Path, start_date: datetime, end_date: datetime
    ) -> Set[str]:
        """Get names of users who pushed directly (not via PR)."""
        pr_pattern = re.compile(r"\s\(#\d+\)")

        try:
            cmd = [
                "git",
                "log",
                "--first-parent",
                "--no-merges",
                f"--since={start_date.isoformat()}",
                f"--until={end_date.isoformat()}",
                "--format=%H|%an|%s",
            ]
            result = subprocess.run(
                cmd, cwd=str(repo_path), capture_output=True, text=True, check=True
            )
            output = result.stdout.strip()
        except subprocess.CalledProcessError:
            return set()

        direct_committers = set()
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            name, message = parts[1], parts[2]
            if pr_pattern.search(message) or "Merge pull request" in message:
                continue
            direct_committers.add(name)

        return direct_committers

    def _get_pr_mergers(
        self, db, repo_id: str, start_date: datetime, end_date: datetime
    ) -> Set[str]:
        """Get logins of users who triggered PR workflow runs."""
        mergers = set()
        try:
            from bson import ObjectId

            try:
                oid = ObjectId(repo_id)
            except Exception:
                oid = repo_id

            cursor = db["workflow_runs"].find(
                {"repo_id": oid, "created_at": {"$gte": start_date, "$lte": end_date}}
            )

            for doc in cursor:
                payload = doc.get("raw_payload", {})
                pull_requests = payload.get("pull_requests", [])
                is_pr = len(pull_requests) > 0 or payload.get("event") == "pull_request"
                if is_pr:
                    actor = payload.get("triggering_actor", {})
                    login = actor.get("login")
                    if login:
                        mergers.add(login)
        except Exception as e:
            logger.warning(f"Failed to get workflow run actors: {e}")

        return mergers
