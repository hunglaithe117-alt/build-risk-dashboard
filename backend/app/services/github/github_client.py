from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional, Callable

from bson import ObjectId
import httpx
from pymongo.database import Database

from app.services.github.redis_token_pool import RedisTokenPool
from app.config import settings
from app.services.github.exceptions import (
    GithubConfigurationError,
    GithubRateLimitError,
    GithubRetryableError,
    GithubAllRateLimitError,
    GithubSecondaryRateLimitError,
)
from app.services.github.github_app import (
    github_app_configured,
    get_installation_token,
)


API_PREVIEW_HEADERS = {
    "Accept": "application/vnd.github+json",
}

logger = logging.getLogger(__name__)


class GitHubClient:
    def __init__(
        self,
        token: str,
        api_url: str | None = None,
        redis_pool: RedisTokenPool | None = None,
        current_token_hash: str | None = None,
    ) -> None:
        """
        Initialize GitHubClient.

        Args:
            token: Raw GitHub token for authentication
            api_url: GitHub API URL (defaults to api.github.com)
            redis_pool: Redis pool for rate limit tracking
            current_token_hash: Hash of current token for Redis tracking
        """
        self._token = token
        self._redis_pool = redis_pool
        self._current_token_key: str | None = current_token_hash

        if not self._token:
            raise GithubConfigurationError("GitHub token is required to call the API")

        self._api_url = (api_url or settings.GITHUB_API_URL).rstrip("/")
        transport = httpx.HTTPTransport(retries=3)
        self._rest = httpx.Client(
            base_url=self._api_url, timeout=120, transport=transport
        )

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        headers.update(API_PREVIEW_HEADERS)
        return headers

    def _handle_response(self, response: httpx.Response) -> httpx.Response:
        # Update Redis pool if available
        if self._redis_pool and self._current_token_key:
            remaining = response.headers.get("X-RateLimit-Remaining")
            limit = response.headers.get("X-RateLimit-Limit")
            reset = response.headers.get("X-RateLimit-Reset")

            if remaining is not None:
                try:
                    from datetime import datetime, timezone

                    self._redis_pool.update_rate_limit(
                        self._current_token_key,
                        int(remaining),
                        int(limit) if limit else 5000,
                        (
                            datetime.fromtimestamp(int(reset), tz=timezone.utc)
                            if reset
                            else None
                        ),
                    )
                except (TypeError, ValueError):
                    pass

        if response.status_code == 403:
            text_lower = response.text.lower()
            if "secondary rate limit" in text_lower:
                self._handle_secondary_rate_limit(response)
            elif "rate limit" in text_lower:
                self._handle_rate_limit(response)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - passthrough for now
            raise GithubRetryableError(str(exc)) from exc
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

        # Mark rate limited in Redis pool
        if self._redis_pool and self._current_token_key:
            try:
                reset_dt = None
                if reset_header:
                    reset_dt = datetime.fromtimestamp(
                        float(reset_header), tz=timezone.utc
                    )
                self._redis_pool.mark_rate_limited(self._current_token_key, reset_dt)
            except (TypeError, ValueError):
                pass

        raise GithubRateLimitError(
            "GitHub rate limit reached", retry_after=wait_seconds
        )

    def _handle_secondary_rate_limit(self, response: httpx.Response) -> None:
        """
        Handle GitHub secondary rate limit (abuse detection).

        Secondary rate limits require longer backoff (typically 60s+).
        """
        import logging

        logger = logging.getLogger(__name__)

        retry_after_header = response.headers.get("Retry-After")
        wait_seconds = 120.0  # Default 2 minutes for secondary

        if retry_after_header:
            try:
                wait_seconds = max(float(retry_after_header), 60.0)
            except ValueError:
                pass

        logger.warning(
            f"GitHub secondary rate limit (abuse detection) hit, "
            f"waiting {wait_seconds}s before retry"
        )

        # Mark token as rate limited with longer cooldown
        reset_at = datetime.now(timezone.utc) + timedelta(seconds=wait_seconds)

        # Mark rate limited in Redis pool
        if self._redis_pool and self._current_token_key:
            self._redis_pool.mark_rate_limited(self._current_token_key, reset_at)

        raise GithubSecondaryRateLimitError(
            "GitHub secondary rate limit (abuse detection) hit",
            retry_after=wait_seconds,
        )

    def _retry_on_rate_limit(
        self, request_func: Callable[[], httpx.Response]
    ) -> httpx.Response:
        """Execute request. Rate limit errors are raised to caller."""
        response = request_func()
        return self._handle_response(response)

    def _rest_request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        def _do_request():
            return self._rest.request(method, path, headers=self._headers(), **kwargs)

        response = self._retry_on_rate_limit(_do_request)
        return response.json()

    def _get_with_cache(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        ttl: int = 3600,
    ) -> Dict[str, Any]:
        """
        GET request with ETag-based caching.

        Conditional requests (304 Not Modified) don't count against rate limits,
        potentially reducing API quota usage by up to 90%.

        Args:
            path: API endpoint path
            params: Query parameters
            ttl: Cache TTL in seconds

        Returns:
            Response data (from cache or fresh)
        """
        from app.services.github.github_cache import get_github_cache

        cache = get_github_cache()
        url = f"{self._api_url}{path}"

        # Get cached ETag
        etag, last_modified, cached_data = cache.get_cached(url)

        # Build headers with conditional request
        headers = self._headers()
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        # Make request directly (not via _retry_on_rate_limit) to handle 304
        try:
            response = self._rest.get(path, headers=headers, params=params)
        except httpx.RequestError as exc:
            # Network error - return cached data if available
            if cached_data:
                return cached_data
            raise GithubRetryableError(str(exc)) from exc

        # Handle 304 Not Modified - return cached data (FREE - doesn't count against rate limit!)
        if response.status_code == 304 and cached_data:
            return cached_data

        # Update rate limit info from headers
        if self._redis_pool and self._current_token_key:
            self._redis_pool.update_rate_limit_from_headers(
                self._current_token_key,
                response.headers,
            )

        # Handle rate limits
        if response.status_code == 403:
            text_lower = response.text.lower()
            if "secondary rate limit" in text_lower:
                self._handle_secondary_rate_limit(response)
            elif "rate limit" in text_lower:
                self._handle_rate_limit(response)

        # Check for other errors
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GithubRetryableError(str(exc)) from exc

        # Fresh response - cache it
        data = response.json()
        new_etag = response.headers.get("ETag")
        new_last_modified = response.headers.get("Last-Modified")

        if new_etag or new_last_modified:
            cache.set_cached(url, data, new_etag, new_last_modified, ttl)

        return data

    def _throttled_request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Make a throttled request to avoid secondary rate limits.

        Uses sliding window rate limiter to spread requests over time.
        """
        from app.services.github.rate_limiter import get_rate_limiter

        # Wait if needed to respect rate limit
        get_rate_limiter().wait()

        return self._rest_request(method, path, **kwargs)

    def _paginate(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Iterator[Dict[str, Any]]:
        url = path
        query = params or {}
        while url:

            def _do_request():
                return self._rest.get(url, headers=self._headers(), params=query)

            response = self._retry_on_rate_limit(_do_request)
            items = response.json()
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

    def get_repository(self, full_name: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Get repository information.

        Args:
            full_name: Repository full name (owner/repo)
            use_cache: Whether to use ETag caching (default True)
        """
        if use_cache:
            return self._get_with_cache(f"/repos/{full_name}", ttl=3600)
        return self._rest_request("GET", f"/repos/{full_name}")

    def list_languages(self, full_name: str, use_cache: bool = True) -> Dict[str, int]:
        """
        Return language usage statistics for a repository (bytes of code per language).

        Args:
            full_name: Repository full name (owner/repo)
            use_cache: Whether to use ETag caching (default True)
        """
        if use_cache:
            return self._get_with_cache(f"/repos/{full_name}/languages", ttl=86400)
        return self._rest_request("GET", f"/repos/{full_name}/languages")

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

    def list_user_installations(self) -> List[Dict[str, Any]]:
        """List installations accessible to the user access token."""
        response = self._rest_request("GET", "/user/installations")
        installations = (
            response.get("installations", []) if isinstance(response, dict) else []
        )
        return installations

    def search_repositories(
        self, query: str, per_page: int = 10
    ) -> List[Dict[str, Any]]:
        params = {"q": query, "per_page": per_page}
        response = self._rest_request("GET", "/search/repositories", params=params)
        items = response.get("items", []) if isinstance(response, dict) else []
        return items

    def paginate_workflow_runs(
        self, full_name: str, params: Optional[Dict[str, Any]] = None
    ) -> Iterator[Dict[str, Any]]:
        url = f"/repos/{full_name}/actions/runs"
        query = params or {}

        while url:

            def _do_request():
                return self._rest.get(url, headers=self._headers(), params=query)

            response = self._retry_on_rate_limit(_do_request)
            data = response.json()

            runs = data.get("workflow_runs", [])
            for run in runs:
                yield run

            # Pagination
            url = None
            query = None  # Clear query params as next link has them
            link_header = response.headers.get("Link")
            if link_header:
                for part in link_header.split(","):
                    segment = part.strip()
                    if segment.endswith('rel="next"'):
                        url = segment[segment.find("<") + 1 : segment.find(">")]
                        break

    def paginate_pull_requests(
        self, full_name: str, params: Optional[Dict[str, Any]] = None
    ) -> Iterator[Dict[str, Any]]:
        url = f"/repos/{full_name}/pulls"
        query = params or {}

        while url:

            def _do_request():
                return self._rest.get(url, headers=self._headers(), params=query)

            response = self._retry_on_rate_limit(_do_request)
            prs = response.json()

            for pr in prs:
                yield pr

            # Pagination
            url = None
            query = None
            link_header = response.headers.get("Link")
            if link_header:
                for part in link_header.split(","):
                    segment = part.strip()
                    if segment.endswith('rel="next"'):
                        url = segment[segment.find("<") + 1 : segment.find(">")]
                        break

    def get_workflow_run(self, full_name: str, run_id: int) -> Dict[str, Any]:
        return self._rest_request("GET", f"/repos/{full_name}/actions/runs/{run_id}")

    def list_workflow_jobs(self, full_name: str, run_id: int) -> List[Dict[str, Any]]:
        jobs = self._rest_request(
            "GET", f"/repos/{full_name}/actions/runs/{run_id}/jobs"
        )
        return jobs.get("jobs", [])

    def get_pull_request(self, full_name: str, pr_number: int) -> Dict[str, Any]:
        return self._rest_request("GET", f"/repos/{full_name}/pulls/{pr_number}")

    def get_pulls(self, full_name: str) -> List[Dict[str, Any]]:
        return self._rest_request("GET", f"/repos/{full_name}/pulls")

    def get_commit(self, full_name: str, sha: str) -> Dict[str, Any]:
        return self._rest_request("GET", f"/repos/{full_name}/commits/{sha}")

    def get_commit_patch(self, full_name: str, sha: str) -> str:
        """Download commit as a patch file."""

        def _do_request():
            headers = self._headers()
            headers["Accept"] = "application/vnd.github.v3.patch"
            return self._rest.get(
                f"/repos/{full_name}/commits/{sha}",
                headers=headers,
            )

        response = self._retry_on_rate_limit(_do_request)
        return response.text

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
        """
        Download logs for a specific job.

        Raises:
            GithubLogsUnavailableError: When logs cannot be retrieved due to
                permissions, expiration, or job not found.
            GithubRateLimitError: When rate limited (retryable).
            GithubRetryableError: For other transient errors.
        """
        from app.services.github.exceptions import (
            GithubLogsUnavailableError,
            LogUnavailableReason,
        )

        def _do_request():
            return self._rest.get(
                f"/repos/{full_name}/actions/jobs/{job_id}/logs",
                headers=self._headers(),
                follow_redirects=True,
            )

        try:
            response = self._retry_on_rate_limit(_do_request)
            return response.content
        except GithubRetryableError as exc:
            # Parse the underlying HTTP error to determine the reason
            original_error = str(exc)
            error_lower = original_error.lower()

            # Check for 403 - Permission denied or rate limit
            if "403" in original_error:
                if "rate limit" in error_lower:
                    # Already handled by _retry_on_rate_limit, but re-raise just in case
                    raise
                # Permission denied - user doesn't have admin rights
                if "admin" in error_lower or "permission" in error_lower:
                    raise GithubLogsUnavailableError(
                        f"Permission denied: admin rights required to download logs for job {job_id}",
                        reason=LogUnavailableReason.PERMISSION_DENIED,
                        job_id=job_id,
                    ) from exc
                # Resource not accessible by integration (GitHub App permission issue)
                if "resource not accessible" in error_lower:
                    raise GithubLogsUnavailableError(
                        f"Resource not accessible: missing actions:read permission for job {job_id}",
                        reason=LogUnavailableReason.PERMISSION_DENIED,
                        job_id=job_id,
                    ) from exc

            # Check for 404 - Logs expired, job not found, or run in progress
            if "404" in original_error:
                raise GithubLogsUnavailableError(
                    f"Logs not found for job {job_id} (expired or job doesn't exist)",
                    reason=LogUnavailableReason.LOGS_EXPIRED,
                    job_id=job_id,
                ) from exc

            # Check for 410 - Gone (explicitly deleted/expired)
            if "410" in original_error:
                raise GithubLogsUnavailableError(
                    f"Logs have been deleted for job {job_id}",
                    reason=LogUnavailableReason.LOGS_EXPIRED,
                    job_id=job_id,
                ) from exc

            raise

    def logs_available(self, full_name: str, run_id: int) -> bool:
        """Return True if the workflow run log archive is still retrievable."""

        try:

            def _do_request():
                return self._rest.head(
                    f"/repos/{full_name}/actions/runs/{run_id}/logs",
                    headers=self._headers(),
                )

            while True:
                try:
                    response = self._rest.head(
                        f"/repos/{full_name}/actions/runs/{run_id}/logs",
                        headers=self._headers(),
                    )
                    if (
                        response.status_code == 403
                        and "rate limit" in response.text.lower()
                    ):
                        self._handle_rate_limit(response)
                    break
                except GithubRateLimitError:
                    if not self._redis_pool:
                        raise
                    self._current_token_key = self._redis_pool.acquire_token()
                    self._token = self._redis_pool.get_raw_token(
                        self._current_token_key
                    )
                    continue

        except httpx.RequestError:  # pragma: no cover - network hiccup
            return False

        if response.status_code in {200, 302, 301}:
            return True
        if response.status_code in {404, 410}:
            return False
        if response.status_code == 405:
            # GitHub may not support HEAD in some environments; fall back to assuming logs exist.
            return True

        return response.is_success

    def close(self) -> None:
        self._rest.close()

    def __enter__(self) -> "GitHubClient":  # pragma: no cover - convenience
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - convenience
        self.close()


def get_user_github_client(db: Database, user_id: str) -> GitHubClient:
    """
    Get a GitHub client using the user's OAuth token.
    Used for querying repositories the user has access to.
    """
    if not user_id:
        raise GithubConfigurationError("user_id is required for user auth")

    identity = db.oauth_identities.find_one(
        {"user_id": ObjectId(user_id), "provider": "github"}
    )
    if not identity or not identity.get("access_token"):
        raise GithubConfigurationError(
            f"No GitHub OAuth token found for user {user_id}"
        )
    return GitHubClient(token=identity["access_token"])


def get_app_github_client(db: Database, installation_id: str) -> GitHubClient:
    """
    Get a GitHub client using the GitHub App installation token.
    Used for backfilling past retained workflows and commits.
    """
    if not installation_id:
        raise GithubConfigurationError("installation_id is required for app auth")

    if not github_app_configured():
        raise GithubConfigurationError("GitHub App is not configured")

    token = get_installation_token(installation_id, db=db)
    return GitHubClient(token=token)


def get_public_github_client() -> GitHubClient:
    """
    Get a GitHub client using public tokens.

    Token sources (in priority order):
    1. Redis pool (recommended - supports multi-worker coordination)
    2. Environment variable GITHUB_TOKENS (fallback for single token)

    Used for public data or when no specific auth is needed.
    """
    # Try Redis-backed pool first
    try:
        from app.services.github.redis_token_pool import get_redis_token_pool

        redis_pool = get_redis_token_pool()
        token_hash, raw_token = redis_pool.acquire_token()

        # Create client with Redis pool for rate limit tracking
        return GitHubClient(
            token=raw_token,
            redis_pool=redis_pool,
            current_token_hash=token_hash,
        )
    except GithubAllRateLimitError:
        # Re-raise rate limit errors
        raise
    except Exception as e:
        # Redis not available or no tokens in pool, fall back to env vars
        logger.warning(f"Redis pool unavailable: {e}, falling back to env vars")

    # Fallback to environment variable tokens
    tokens = settings.GITHUB_TOKENS or []
    tokens = [t.strip() for t in tokens if t and t.strip()]

    if not tokens:
        raise GithubConfigurationError(
            "No GitHub tokens configured. Set GITHUB_TOKENS environment variable."
        )

    # Use first available token (no rotation in fallback mode)
    return GitHubClient(token=tokens[0])
