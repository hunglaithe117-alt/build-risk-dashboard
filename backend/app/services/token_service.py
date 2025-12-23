"""Service for GitHub token management using Redis pool."""

from typing import Optional

from fastapi import HTTPException, status

from app.services.github.github_token_manager import (
    get_token_rate_limit,
    hash_token,
    verify_github_token,
)
from app.services.github.redis_token_pool import (
    TOKEN_STATUS_ACTIVE,
    TOKEN_STATUS_DISABLED,
    get_redis_token_pool,
)


class TokenService:
    """Service for GitHub token management operations using Redis."""

    def __init__(self):
        self._pool = get_redis_token_pool()

    async def refresh_all_tokens(self) -> dict:
        """
        Refresh rate limit info for all tokens by querying GitHub API.
        """
        tokens = self._pool.get_all_tokens()
        results = []
        refreshed = 0
        failed = 0

        for token_info in tokens:
            token_hash = token_info["token_hash"]

            # Get raw token from Redis
            raw_token = self._pool._redis.hget("github_tokens:raw", token_hash)
            if not raw_token:
                results.append(
                    {
                        "id": token_info["id"],
                        "success": False,
                        "error": "Token not found in pool",
                    }
                )
                failed += 1
                continue

            if isinstance(raw_token, bytes):
                raw_token = raw_token.decode()

            # Query GitHub API for rate limit
            rate_limit_info = await get_token_rate_limit(raw_token)

            if rate_limit_info:
                self._pool.update_rate_limit(
                    token_hash,
                    remaining=rate_limit_info["remaining"],
                    limit=rate_limit_info["limit"],
                    reset_at=rate_limit_info["reset_at"],
                )

                results.append(
                    {
                        "id": token_info["id"],
                        "success": True,
                        "remaining": rate_limit_info["remaining"],
                        "limit": rate_limit_info["limit"],
                    }
                )
                refreshed += 1
            else:
                results.append(
                    {
                        "id": token_info["id"],
                        "success": False,
                        "error": "Failed to get rate limit from GitHub API",
                    }
                )
                failed += 1

        return {"refreshed": refreshed, "failed": failed, "results": results}

    def list_tokens(self, include_disabled: bool = False) -> dict:
        """List all GitHub tokens (masked, without actual token values)."""
        tokens = self._pool.get_all_tokens()

        if not include_disabled:
            tokens = [t for t in tokens if t.get("status") != TOKEN_STATUS_DISABLED]

        return {"items": tokens, "total": len(tokens)}

    def get_pool_status(self) -> dict:
        """Get overall status of the token pool."""
        return self._pool.get_pool_status()

    def create_token(self, token: str, label: str = "") -> dict:
        """Add a new GitHub token to the pool."""
        token_hash = hash_token(token)

        # Check if already exists
        if self._pool._redis.hexists("github_tokens:raw", token_hash):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Token already exists in pool",
            )

        # Add to pool
        self._pool.add_token(token, label)

        # Return token info
        tokens = self._pool.get_all_tokens()
        for t in tokens:
            if t["token_hash"] == token_hash:
                return t

        # Fallback
        return {
            "id": token_hash[:16],
            "token_hash": token_hash,
            "label": label,
            "status": TOKEN_STATUS_ACTIVE,
        }

    def get_token(self, token_id: str) -> dict:
        """Get details of a specific token."""
        tokens = self._pool.get_all_tokens()
        for t in tokens:
            if t["id"] == token_id or t["token_hash"].startswith(token_id):
                return t

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )

    def update_token(
        self,
        token_id: str,
        label: Optional[str] = None,
        token_status: Optional[str] = None,
    ) -> dict:
        """Update a token's label or status."""
        # Find token by ID
        tokens = self._pool.get_all_tokens()
        target = None
        for t in tokens:
            if t["id"] == token_id or t["token_hash"].startswith(token_id):
                target = t
                break

        if not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found",
            )

        token_hash = target["token_hash"]

        # Validate status if provided
        if token_status is not None:
            if token_status not in [TOKEN_STATUS_ACTIVE, TOKEN_STATUS_DISABLED]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status. Must be '{TOKEN_STATUS_ACTIVE}' or '{TOKEN_STATUS_DISABLED}'",
                )
            self._pool._redis.hset(
                f"github_tokens:stats:{token_hash}", "status", token_status
            )

        if label is not None:
            self._pool._redis.hset(f"github_tokens:stats:{token_hash}", "label", label)

        # Return updated token
        return self.get_token(token_id)

    def delete_token(self, token_id: str) -> bool:
        """Remove a token from the pool."""
        # Find token by ID
        tokens = self._pool.get_all_tokens()
        target = None
        for t in tokens:
            if t["id"] == token_id or t["token_hash"].startswith(token_id):
                target = t
                break

        if not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found",
            )

        success = self._pool.remove_token(target["token_hash"])
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found",
            )
        return True

    async def verify_token(self, token_id: str, raw_token: str) -> dict:
        """Verify a token is still valid by calling GitHub API."""
        # Find token
        tokens = self._pool.get_all_tokens()
        target = None
        for t in tokens:
            if t["id"] == token_id or t["token_hash"].startswith(token_id):
                target = t
                break

        if not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found",
            )

        if not raw_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="raw_token is required for verification",
            )

        # Validate the provided token
        is_valid, rate_limit_info = await verify_github_token(raw_token)

        if is_valid:
            if rate_limit_info:
                self._pool.update_rate_limit(
                    target["token_hash"],
                    remaining=rate_limit_info["remaining"],
                    limit=rate_limit_info["limit"],
                    reset_at=rate_limit_info["reset_at"],
                )

            return {
                "valid": True,
                "rate_limit_remaining": (
                    rate_limit_info["remaining"] if rate_limit_info else None
                ),
                "rate_limit_limit": (
                    rate_limit_info["limit"] if rate_limit_info else None
                ),
            }
        else:
            return {
                "valid": False,
                "error": "Token is invalid or revoked",
            }
