"""GitHub API helpers shared by ingestion workers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, Iterator, List, Optional

from bson import ObjectId
import httpx
from pymongo.database import Database

from app.config import settings
from app.services.pipeline_exceptions import (
    PipelineConfigurationError,
    PipelineRateLimitError,
    PipelineRetryableError,
)
from app.services.github.github_app import (
    github_app_configured,
    get_installation_token,
)


API_PREVIEW_HEADERS = {
    "Accept": "application/vnd.github+json",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GitHubTokenPool:
    """Thread-safe pool that rotates tokens to avoid rate limiting."""

    def __init__(self, tokens: List[str]):
        normalized = [token.strip() for token in tokens if token and token.strip()]
        if not normalized:
            raise PipelineConfigurationError("No GitHub tokens configured for pool")
        self._tokens = normalized
        self._index = 0
        self._lock = Lock()
        self._cooldowns: Dict[str, datetime] = {}

    @property
    def snapshot(self) -> tuple:
        return tuple(self._tokens)

    def acquire_token(self) -> str:
        now = _now()
        with self._lock:
            total = len(self._tokens)
            for _ in range(total):
                token = self._tokens[self._index]
                self._index = (self._index + 1) % total
                cooldown_until = self._cooldowns.get(token)
                if cooldown_until and cooldown_until > now:
                    continue
                return token
        raise PipelineRateLimitError(
            "All GitHub tokens hit rate limits. Please wait before retrying."
        )

    def mark_rate_limited(self, token: str, reset_epoch: Optional[str]) -> None:
        cooldown = _now() + timedelta(minutes=2)
        if reset_epoch:
            try:
                cooldown = datetime.fromtimestamp(int(reset_epoch), tz=timezone.utc)
            except (TypeError, ValueError):
                pass
        with self._lock:
            self._cooldowns[token] = cooldown


class GitHubClient:
    """Lightweight wrapper around GitHub's REST + GraphQL APIs."""

    def __init__(
        self,
        token: str | None = None,
        token_pool: GitHubTokenPool | None = None,
        api_url: str | None = None,
        graphql_url: str | None = None,
    ) -> None:
        self._token_pool = token_pool
        self._token = token or (token_pool.acquire_token() if token_pool else None)
        if not self._token:
            raise PipelineConfigurationError("GitHub token is required to call the API")
        self._api_url = (api_url or settings.GITHUB_API_URL).rstrip("/")
        self._graphql_url = (graphql_url or settings.GITHUB_GRAPHQL_URL).rstrip("/")
        self._rest = httpx.Client(base_url=self._api_url, timeout=20)
        self._graphql = httpx.Client(base_url=self._graphql_url, timeout=20)

    # --- Internal helpers -------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        headers.update(API_PREVIEW_HEADERS)
        return headers

    def _handle_response(self, response: httpx.Response) -> httpx.Response:
        if response.status_code == 403 and "rate limit" in response.text.lower():
            self._handle_rate_limit(response)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - passthrough for now
            raise PipelineRetryableError(str(exc)) from exc
        return response

    def _handle_rate_limit(self, response: httpx.Response) -> None:
        reset_header = response.headers.get("X-RateLimit-Reset")
        retry_after_header = response.headers.get("Retry-After")
        wait_seconds = 60.0

        if retry_after_header:
            try:
                wait_seconds = float(retry_after_header)
            except ValueError:
                pass
        elif reset_header:
            try:
                reset_epoch = float(reset_header)
                now_epoch = datetime.now(timezone.utc).timestamp()
                wait_seconds = max(reset_epoch - now_epoch, 1.0)
            except ValueError:
                pass

        if self._token_pool and self._token:
            self._token_pool.mark_rate_limited(self._token, reset_epoch=reset_header)

        raise PipelineRateLimitError(
            "GitHub rate limit reached", retry_after=wait_seconds
        )

    def _rest_request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        response = self._rest.request(method, path, headers=self._headers(), **kwargs)
        data = self._handle_response(response).json()
        return data

    def _paginate(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Iterator[Dict[str, Any]]:
        url = path
        query = params or {}
        while url:
            response = self._rest.get(url, headers=self._headers(), params=query)
            data = self._handle_response(response)
            items = data.json()
            if isinstance(items, list):
                yield from items
            else:
                yield items
                break
            url = None
            link_header = response.headers.get("Link")
            if link_header:
                for part in link_header.split(","):
                    segment = part.strip()
                    if segment.endswith('rel="next"'):
                        url = segment[segment.find("<") + 1 : segment.find(">")]
                        query = None  # GitHub link already contains query params
                        break

    def graphql(
        self, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        payload = {"query": query, "variables": variables or {}}
        response = self._graphql.post("", headers=self._headers(), json=payload)
        self._handle_response(response)
        payload = response.json()
        if payload.get("errors"):
            raise PipelineRetryableError(str(payload["errors"]))
        return payload.get("data", {})

    # --- Public REST helpers ----------------------------------------------
    def get_repository(self, full_name: str) -> Dict[str, Any]:
        return self._rest_request("GET", f"/repos/{full_name}")

    def list_authenticated_repositories(
        self, per_page: int = 10
    ) -> List[Dict[str, Any]]:
        params = {
            "per_page": per_page,
            "sort": "updated",
            "affiliation": "owner,collaborator,organization_member",
        }
        repos = self._rest_request("GET", "/user/repos", params=params)
        return repos if isinstance(repos, list) else []

    def search_repositories(
        self, query: str, per_page: int = 10
    ) -> List[Dict[str, Any]]:
        params = {"q": query, "per_page": per_page}
        response = self._rest_request("GET", "/search/repositories", params=params)
        items = response.get("items", []) if isinstance(response, dict) else []
        return items

    def list_workflow_runs(
        self, full_name: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        repo_runs = self._rest_request(
            "GET", f"/repos/{full_name}/actions/runs", params=params
        )
        return repo_runs.get("workflow_runs", [])

    def get_workflow_run(self, full_name: str, run_id: int) -> Dict[str, Any]:
        return self._rest_request("GET", f"/repos/{full_name}/actions/runs/{run_id}")

    def list_workflow_jobs(self, full_name: str, run_id: int) -> List[Dict[str, Any]]:
        jobs = self._rest_request(
            "GET", f"/repos/{full_name}/actions/runs/{run_id}/jobs"
        )
        return jobs.get("jobs", [])

    def get_pull_request(self, full_name: str, pr_number: int) -> Dict[str, Any]:
        return self._rest_request("GET", f"/repos/{full_name}/pulls/{pr_number}")

    def get_commit(self, full_name: str, sha: str) -> Dict[str, Any]:
        return self._rest_request("GET", f"/repos/{full_name}/commits/{sha}")

    def list_commit_comments(self, full_name: str, sha: str) -> List[Dict[str, Any]]:
        comments = self._rest_request(
            "GET", f"/repos/{full_name}/commits/{sha}/comments"
        )
        return comments or []

    def list_issue_comments(
        self, full_name: str, issue_number: int
    ) -> List[Dict[str, Any]]:
        return self._rest_request(
            "GET", f"/repos/{full_name}/issues/{issue_number}/comments"
        )

    def list_review_comments(
        self, full_name: str, pr_number: int
    ) -> List[Dict[str, Any]]:
        reviews = self._rest_request(
            "GET", f"/repos/{full_name}/pulls/{pr_number}/comments"
        )
        return reviews or []

    def compare_commits(self, full_name: str, base: str, head: str) -> Dict[str, Any]:
        return self._rest_request("GET", f"/repos/{full_name}/compare/{base}...{head}")

    def download_job_logs(self, full_name: str, job_id: int) -> bytes:
        response = self._rest.get(
            f"/repos/{full_name}/actions/jobs/{job_id}/logs", headers=self._headers()
        )
        self._handle_response(response)
        return response.content

    def logs_available(self, full_name: str, run_id: int) -> bool:
        """Return True if the workflow run log archive is still retrievable."""

        try:
            response = self._rest.head(
                f"/repos/{full_name}/actions/runs/{run_id}/logs",
                headers=self._headers(),
            )
        except httpx.RequestError:  # pragma: no cover - network hiccup
            return False

        if response.status_code in {200, 302, 301}:
            return True
        if response.status_code in {404, 410}:
            return False
        if response.status_code == 405:
            # GitHub may not support HEAD in some environments; fall back to assuming logs exist.
            return True
        if response.status_code == 403 and "rate limit" in response.text.lower():
            self._handle_rate_limit(response)
        return response.is_success

    # --- Derived helpers ---------------------------------------------------
    def get_recent_contributors(self, full_name: str, since: datetime) -> List[str]:
        query = """
        query($fullName: String!, $since: GitTimestamp!) {
          repository(nameWithOwner: $fullName) {
            defaultBranchRef {
              target {
                ... on Commit {
                  history(since: $since, first: 100) {
                    edges {
                      node {
                        oid
                        author { user { login } }
                        committer { user { login } }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        data = self.graphql(
            query,
            {
                "fullName": full_name,
                "since": since.isoformat(),
            },
        )
        repository = data.get("repository") or {}
        default_branch = repository.get("defaultBranchRef") or {}
        history = ((default_branch.get("target") or {}).get("history") or {}).get(
            "edges", []
        )
        contributors = {
            edge["node"].get("author", {}).get("user", {}).get("login")
            or edge["node"].get("committer", {}).get("user", {}).get("login")
            for edge in history
            if edge.get("node")
        }
        return [c for c in contributors if c]

    def get_repository_history(self, full_name: str) -> Dict[str, Any]:
        query = """
        query($fullName: String!) {
          repository(nameWithOwner: $fullName) {
            createdAt
            pushedAt
            defaultBranchRef {
              name
              target {
                ... on Commit {
                  history {
                    totalCount
                  }
                }
              }
            }
            languages(first: 5, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                node { name }
                size
              }
            }
          }
        }
        """
        data = self.graphql(query, {"fullName": full_name})
        return data.get("repository", {})

    def close(self) -> None:
        self._rest.close()
        self._graphql.close()

    def __enter__(self) -> "GitHubClient":  # pragma: no cover - convenience
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - convenience
        self.close()


_token_pool: GitHubTokenPool | None = None


def get_user_github_client(db: Database, user_id: str) -> GitHubClient:
    """
    Get a GitHub client using the user's OAuth token.
    Used for querying repositories the user has access to.
    """
    if not user_id:
        raise PipelineConfigurationError("user_id is required for user auth")

    identity = db.oauth_identities.find_one(
        {"user_id": ObjectId(user_id), "provider": "github"}
    )
    if not identity or not identity.get("access_token"):
        raise PipelineConfigurationError(
            f"No GitHub OAuth token found for user {user_id}"
        )
    return GitHubClient(token=identity["access_token"])


def get_app_github_client(db: Database, installation_id: str) -> GitHubClient:
    """
    Get a GitHub client using the GitHub App installation token.
    Used for backfilling past retained workflows and commits.
    """
    if not installation_id:
        raise PipelineConfigurationError("installation_id is required for app auth")

    if not github_app_configured():
        raise PipelineConfigurationError("GitHub App is not configured")

    token = get_installation_token(installation_id, db=db)
    return GitHubClient(token=token)


def get_public_github_client() -> GitHubClient:
    """
    Get a GitHub client using public tokens from config.
    Used for public data or when no specific auth is needed.
    """
    global _token_pool

    tokens = settings.GITHUB_TOKENS or []
    # Filter empty tokens
    tokens = [t for t in tokens if t and t.strip()]

    if not tokens:
        raise PipelineConfigurationError(
            "No public GitHub tokens configured in settings"
        )

    if len(tokens) == 1:
        return GitHubClient(token=tokens[0])

    snapshot = tuple(tokens)
    if _token_pool is None or _token_pool.snapshot != snapshot:
        _token_pool = GitHubTokenPool(tokens)

    return GitHubClient(token_pool=_token_pool)


def get_pipeline_github_client(
    db: Database,
    auth_type: str = "public",  # "user", "app", "public"
    user_id: Optional[str] = None,
    installation_id: Optional[str] = None,
) -> GitHubClient:
    """
    DEPRECATED: Use specific get_*_github_client functions instead.
    Wrapper for backward compatibility.
    """
    if auth_type == "user":
        if not user_id:
            raise PipelineConfigurationError("user_id is required for 'user' auth type")
        return get_user_github_client(db, user_id)
    elif auth_type == "app":
        if not installation_id:
            raise PipelineConfigurationError(
                "installation_id is required for 'app' auth type"
            )
        return get_app_github_client(db, installation_id)
    elif auth_type == "public":
        return get_public_github_client()
    else:
        raise PipelineConfigurationError(f"Invalid auth_type: {auth_type}")
