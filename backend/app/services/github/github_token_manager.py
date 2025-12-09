from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import httpx
from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.database import Database

from app.config import settings
from app.entities.github_token import GithubToken

GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_RATE_LIMIT_URL = "https://api.github.com/rate_limit"


# ============================================================================
# Token Status Constants
# ============================================================================


class GitHubTokenStatus:
    """GitHub token status indicators."""

    VALID = "valid"
    EXPIRED = "expired"
    REVOKED = "revoked"
    MISSING = "missing"
    INVALID = "invalid"


class PublicTokenStatus:
    """Public token status for pool management."""

    ACTIVE = "active"
    RATE_LIMITED = "rate_limited"
    INVALID = "invalid"
    DISABLED = "disabled"


# ============================================================================
# Token Hashing & Masking Utilities
# ============================================================================


def hash_token(token: str) -> str:
    """Create SHA-256 hash of a token for secure storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def mask_token(token: str) -> str:
    """Mask token to show only last 4 characters."""
    if len(token) <= 4:
        return "****"
    return f"****{token[-4:]}"


# In-memory cache mapping token_hash -> raw_token
# This is populated at startup from env vars and allows DB-backed pool to work
_token_cache: Dict[str, str] = {}


def get_raw_token_from_cache(token_hash: str) -> Optional[str]:
    """Get raw token from in-memory cache by hash."""
    return _token_cache.get(token_hash)


def populate_token_cache_from_env() -> int:
    """
    Populate in-memory token cache from environment variables.

    Returns:
        Number of tokens cached.
    """
    global _token_cache
    from app.config import settings

    tokens = settings.GITHUB_TOKENS or []
    tokens = [t.strip() for t in tokens if t and t.strip()]

    for token in tokens:
        token_hash_value = hash_token(token)
        _token_cache[token_hash_value] = token

    return len(tokens)


def seed_tokens_from_env(db: Database) -> int:
    """
    Seed tokens from environment variable GITHUB_TOKENS into database.

    Only adds tokens that don't already exist (checked by hash).
    Called on application startup to ensure env tokens are in DB.
    Also populates the in-memory token cache.

    Returns:
        Number of new tokens added.
    """
    global _token_cache
    from app.config import settings

    tokens = settings.GITHUB_TOKENS or []
    tokens = [t.strip() for t in tokens if t and t.strip()]

    if not tokens:
        return 0

    added = 0
    for i, token in enumerate(tokens):
        token_hash_value = hash_token(token)

        # Always add to cache for lookup
        _token_cache[token_hash_value] = token

        # Check if already exists in DB
        existing = db.github_tokens.find_one({"token_hash": token_hash_value})
        if existing:
            continue

        # Create token entity
        github_token = GithubToken(
            token_hash=token_hash_value,
            masked_token=mask_token(token),
            label=f"Env Token {i + 1}",
            status=PublicTokenStatus.ACTIVE,
        )

        db.github_tokens.insert_one(github_token.to_mongo())
        added += 1

    return added


# ============================================================================
# Token Validation Functions
# ============================================================================


async def verify_github_token(access_token: str) -> Tuple[bool, Optional[dict]]:
    """
    Verify a GitHub token and get rate limit info.

    Returns:
        Tuple of (is_valid, rate_limit_info)
        rate_limit_info contains: remaining, limit, reset_at
    """
    if not access_token:
        return False, None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                GITHUB_USER_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                },
            )

            rate_limit_info = None
            remaining = response.headers.get("X-RateLimit-Remaining")
            limit = response.headers.get("X-RateLimit-Limit")
            reset = response.headers.get("X-RateLimit-Reset")

            if remaining is not None:
                rate_limit_info = {
                    "remaining": int(remaining),
                    "limit": int(limit) if limit else 5000,
                    "reset_at": (
                        datetime.fromtimestamp(int(reset), tz=timezone.utc)
                        if reset
                        else None
                    ),
                }

            return response.status_code == 200, rate_limit_info
    except Exception:
        return False, None


async def get_token_rate_limit(access_token: str) -> Optional[dict]:
    """Get rate limit info for a token without making an authenticated request."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                GITHUB_RATE_LIMIT_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                },
            )
            if response.status_code == 200:
                data = response.json()
                core = data.get("resources", {}).get("core", {})
                return {
                    "remaining": core.get("remaining", 0),
                    "limit": core.get("limit", 5000),
                    "reset_at": datetime.fromtimestamp(
                        core.get("reset", 0), tz=timezone.utc
                    ),
                }
    except Exception:
        pass
    return None


# ============================================================================
# Public Token CRUD Operations (MongoDB)
# ============================================================================


def add_public_token(
    db: Database,
    token: str,
    label: str = "",
    validate: bool = True,
) -> Tuple[bool, str, Optional[str]]:
    """
    Add a new public token to the database.

    Args:
        db: MongoDB database instance
        token: The GitHub personal access token
        label: User-friendly label for this token
        validate: Whether to validate the token before adding

    Returns:
        Tuple of (success, token_id or error_message, error_type)
    """
    global _token_cache

    token = token.strip()
    if not token:
        return False, "Token cannot be empty", "validation_error"

    # Check if token already exists
    token_hash_value = hash_token(token)
    existing = db.github_tokens.find_one({"token_hash": token_hash_value})
    if existing:
        # Even if exists in DB, add to cache for this session
        _token_cache[token_hash_value] = token
        return False, "Token already exists", "duplicate_error"

    # Add to in-memory cache for API calls
    _token_cache[token_hash_value] = token

    # Create token entity
    github_token = GithubToken(
        token_hash=token_hash_value,
        masked_token=mask_token(token),
        label=label or f"Token {mask_token(token)}",
        status=PublicTokenStatus.ACTIVE,
    )

    result = db.github_tokens.insert_one(github_token.to_mongo())
    return True, str(result.inserted_id), None


def remove_public_token(db: Database, token_id: str) -> bool:
    """Remove a public token from the database."""
    result = db.github_tokens.delete_one({"_id": ObjectId(token_id)})
    return result.deleted_count > 0


def update_public_token(
    db: Database,
    token_id: str,
    label: Optional[str] = None,
    status: Optional[str] = None,
) -> bool:
    """Update a public token's label or status."""
    update_fields = {"updated_at": datetime.now(timezone.utc)}

    if label is not None:
        update_fields["label"] = label
    if status is not None:
        if status not in [
            PublicTokenStatus.ACTIVE,
            PublicTokenStatus.DISABLED,
        ]:
            return False
        update_fields["status"] = status

    result = db.github_tokens.update_one(
        {"_id": ObjectId(token_id)},
        {"$set": update_fields},
    )
    return result.modified_count > 0


def list_public_tokens(db: Database, include_disabled: bool = False) -> List[dict]:
    """
    List all public tokens (masked, without actual token values).

    Returns list of token info dictionaries.
    """
    query = {}
    if not include_disabled:
        query["status"] = {"$ne": PublicTokenStatus.DISABLED}

    tokens = db.github_tokens.find(query).sort("created_at", -1)
    result = []

    for token in tokens:
        result.append(
            {
                "id": str(token["_id"]),
                "masked_token": token.get("masked_token", "****"),
                "label": token.get("label", ""),
                "status": token.get("status", PublicTokenStatus.ACTIVE),
                "rate_limit_remaining": token.get("rate_limit_remaining"),
                "rate_limit_limit": token.get("rate_limit_limit"),
                "rate_limit_reset_at": token.get("rate_limit_reset_at"),
                "last_used_at": token.get("last_used_at"),
                "total_requests": token.get("total_requests", 0),
                "created_at": token.get("created_at"),
                "last_validated_at": token.get("last_validated_at"),
                "validation_error": token.get("validation_error"),
            }
        )

    return result


def get_public_token_by_id(db: Database, token_id: str) -> Optional[dict]:
    """Get a single public token by ID."""
    token = db.github_tokens.find_one({"_id": ObjectId(token_id)})
    if not token:
        return None

    return {
        "id": str(token["_id"]),
        "masked_token": token.get("masked_token", "****"),
        "label": token.get("label", ""),
        "status": token.get("status", PublicTokenStatus.ACTIVE),
        "rate_limit_remaining": token.get("rate_limit_remaining"),
        "rate_limit_limit": token.get("rate_limit_limit"),
        "rate_limit_reset_at": token.get("rate_limit_reset_at"),
        "last_used_at": token.get("last_used_at"),
        "total_requests": token.get("total_requests", 0),
        "created_at": token.get("created_at"),
    }


def get_tokens_pool_status(db: Database) -> dict:
    """
    Get overall status of the token pool.

    Returns:
        Dictionary with pool statistics and health info.
    """
    all_tokens = list(db.github_tokens.find({}))

    now = datetime.now(timezone.utc)

    total = len(all_tokens)
    active = 0
    rate_limited = 0
    invalid = 0
    disabled = 0
    total_remaining = 0
    next_reset = None

    for token in all_tokens:
        status = token.get("status", PublicTokenStatus.ACTIVE)

        if status == PublicTokenStatus.DISABLED:
            disabled += 1
            continue

        if status == PublicTokenStatus.INVALID:
            invalid += 1
            continue

        # Check if rate limited
        reset_at = token.get("rate_limit_reset_at")
        remaining = token.get("rate_limit_remaining", 5000)

        if status == PublicTokenStatus.RATE_LIMITED:
            if reset_at and reset_at <= now:
                # Rate limit has reset, token should be active
                active += 1
                total_remaining += 5000  # Assume full reset
            else:
                rate_limited += 1
                if reset_at and (next_reset is None or reset_at < next_reset):
                    next_reset = reset_at
        else:
            active += 1
            total_remaining += remaining if remaining is not None else 5000

    return {
        "total_tokens": total,
        "active_tokens": active,
        "rate_limited_tokens": rate_limited,
        "invalid_tokens": invalid,
        "disabled_tokens": disabled,
        "estimated_requests_available": total_remaining,
        "next_reset_at": next_reset.isoformat() if next_reset else None,
        "pool_healthy": active > 0,
    }


def update_token_rate_limit(
    db: Database,
    token_hash: str,
    remaining: int,
    limit: int,
    reset_at: datetime,
) -> None:
    """Update rate limit info for a token after an API request."""
    now = datetime.now(timezone.utc)

    update_data = {
        "rate_limit_remaining": remaining,
        "rate_limit_limit": limit,
        "rate_limit_reset_at": reset_at,
        "last_used_at": now,
        "updated_at": now,
    }

    # If remaining is 0, mark as rate limited
    if remaining == 0:
        update_data["status"] = PublicTokenStatus.RATE_LIMITED
    elif remaining > 0:
        # Token is usable again
        update_data["status"] = PublicTokenStatus.ACTIVE

    db.github_tokens.update_one(
        {"token_hash": token_hash},
        {
            "$set": update_data,
            "$inc": {"total_requests": 1},
        },
    )


def mark_token_rate_limited(
    db: Database,
    token_hash: str,
    reset_at: Optional[datetime] = None,
) -> None:
    """Mark a token as rate limited."""
    if reset_at is None:
        reset_at = datetime.now(timezone.utc) + timedelta(minutes=60)

    db.github_tokens.update_one(
        {"token_hash": token_hash},
        {
            "$set": {
                "status": PublicTokenStatus.RATE_LIMITED,
                "rate_limit_remaining": 0,
                "rate_limit_reset_at": reset_at,
                "updated_at": datetime.now(timezone.utc),
            },
        },
    )


def mark_token_invalid(
    db: Database,
    token_hash: str,
    error: str = "Token validation failed",
) -> None:
    """Mark a token as invalid (revoked or expired)."""
    db.github_tokens.update_one(
        {"token_hash": token_hash},
        {
            "$set": {
                "status": PublicTokenStatus.INVALID,
                "validation_error": error,
                "last_validated_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
        },
    )


def get_available_tokens(db: Database) -> List[dict]:
    """
    Get list of tokens available for use (active or rate limit expired).

    Returns tokens sorted by remaining quota (highest first).
    """
    now = datetime.now(timezone.utc)

    # Find active tokens or rate-limited tokens whose reset time has passed
    tokens = db.github_tokens.find(
        {
            "$or": [
                {"status": PublicTokenStatus.ACTIVE},
                {
                    "status": PublicTokenStatus.RATE_LIMITED,
                    "rate_limit_reset_at": {"$lte": now},
                },
            ],
        }
    ).sort("rate_limit_remaining", -1)

    result = []
    for token in tokens:
        result.append(
            {
                "token_hash": token["token_hash"],
                "remaining": token.get("rate_limit_remaining"),
                "reset_at": token.get("rate_limit_reset_at"),
            }
        )

    return result


async def validate_and_update_token(
    db: Database,
    token_id: str,
    raw_token: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validate a token against GitHub API and update its status.

    Args:
        db: Database instance
        token_id: Token ID in database
        raw_token: The actual token value (needed for validation)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not raw_token:
        return False, "Raw token value is required for validation"

    is_valid, rate_limit_info = await verify_github_token(raw_token)
    now = datetime.now(timezone.utc)

    if is_valid:
        update_data = {
            "status": PublicTokenStatus.ACTIVE,
            "last_validated_at": now,
            "validation_error": None,
            "updated_at": now,
        }

        if rate_limit_info:
            update_data.update(
                {
                    "rate_limit_remaining": rate_limit_info["remaining"],
                    "rate_limit_limit": rate_limit_info["limit"],
                    "rate_limit_reset_at": rate_limit_info["reset_at"],
                }
            )

        db.github_tokens.update_one(
            {"_id": ObjectId(token_id)},
            {"$set": update_data},
        )
        return True, None
    else:
        db.github_tokens.update_one(
            {"_id": ObjectId(token_id)},
            {
                "$set": {
                    "status": PublicTokenStatus.INVALID,
                    "validation_error": "Token is invalid or revoked",
                    "last_validated_at": now,
                    "updated_at": now,
                },
            },
        )
        return False, "Token is invalid or revoked"


# ============================================================================
# User OAuth Token Management (existing functionality)
# ============================================================================


async def check_github_token_status(
    db: Database, user_id: ObjectId, verify_with_api: bool = False
) -> Tuple[str, Optional[dict]]:
    identity = db.oauth_identities.find_one({"user_id": user_id, "provider": "github"})

    if not identity:
        return GitHubTokenStatus.MISSING, None

    access_token = identity.get("access_token")
    if not access_token:
        return GitHubTokenStatus.MISSING, identity

    # Check if token has explicit expiration time
    token_expires_at = identity.get("token_expires_at")
    if token_expires_at:
        if datetime.now(timezone.utc) >= token_expires_at:
            return GitHubTokenStatus.EXPIRED, identity

    # Optionally verify with GitHub API
    if verify_with_api:
        is_valid, _ = await verify_github_token(access_token)
        if not is_valid:
            return GitHubTokenStatus.REVOKED, identity

    return GitHubTokenStatus.VALID, identity


async def get_valid_github_token(
    db: Database, user_id: ObjectId, verify_with_api: bool = False
) -> str:
    status_code, identity = await check_github_token_status(
        db, user_id, verify_with_api
    )

    if status_code == GitHubTokenStatus.MISSING:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub account not connected. Please connect your GitHub account.",
            headers={"X-Auth-Error": "github_not_connected"},
        )

    if status_code == GitHubTokenStatus.EXPIRED:
        # Mark token as invalid in database
        await mark_github_oauth_token_invalid(db, identity["_id"], reason="expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub token has expired. Please re-authenticate with GitHub.",
            headers={"X-Auth-Error": "github_token_expired"},
        )

    if status_code == GitHubTokenStatus.REVOKED:
        # Mark token as invalid in database
        await mark_github_oauth_token_invalid(db, identity["_id"], reason="revoked")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub token has been revoked. Please re-authenticate with GitHub.",
            headers={"X-Auth-Error": "github_token_revoked"},
        )

    return identity["access_token"]


async def mark_github_oauth_token_invalid(
    db: Database, identity_id: ObjectId, reason: str = "invalid"
) -> None:
    db.oauth_identities.update_one(
        {"_id": identity_id},
        {
            "$set": {
                "token_status": "invalid",
                "token_invalid_reason": reason,
                "token_invalidated_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )


async def refresh_github_token_if_needed(
    db: Database, user_id: ObjectId
) -> Optional[str]:
    identity = db.oauth_identities.find_one({"user_id": user_id, "provider": "github"})

    if not identity:
        return None

    refresh_token = identity.get("refresh_token")
    if not refresh_token:
        # No refresh token available - user needs to re-authenticate
        return None

    # Check if token is expired
    token_expires_at = identity.get("token_expires_at")
    if not token_expires_at or datetime.now(timezone.utc) < token_expires_at:
        # Token not expired yet
        return identity.get("access_token")

    # Attempt to refresh token
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
            token_data = response.json()

            new_access_token = token_data.get("access_token")
            new_refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")

            if not new_access_token:
                return None

            # Calculate new expiration time
            new_expires_at = None
            if expires_in:
                new_expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=expires_in
                )

            # Update token in database
            db.oauth_identities.update_one(
                {"_id": identity["_id"]},
                {
                    "$set": {
                        "access_token": new_access_token,
                        "refresh_token": new_refresh_token or refresh_token,
                        "token_expires_at": new_expires_at,
                        "token_status": "valid",
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )

            return new_access_token

    except Exception:
        # Refresh failed - mark token as invalid
        await mark_github_oauth_token_invalid(
            db, identity["_id"], reason="refresh_failed"
        )
        return None


def requires_github_token(verify_with_api: bool = False):
    async def dependency(user_id: str, db: Database) -> str:
        """Get valid GitHub token or raise exception."""
        return await get_valid_github_token(
            db, ObjectId(user_id), verify_with_api=verify_with_api
        )

    return dependency
