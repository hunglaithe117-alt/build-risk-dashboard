"""GitHub Token management API endpoints."""

from typing import Optional, List
from fastapi import APIRouter, Depends, Path, HTTPException, status, Body
from pymongo.database import Database
from pydantic import BaseModel

from app.database.mongo import get_db
from app.middleware.auth import get_current_user
from app.dtos.token import (
    TokenCreateRequest,
    TokenUpdateRequest,
    TokenResponse,
    TokenPoolStatusResponse,
    TokenVerifyResponse,
    TokenListResponse,
)
from app.services.github.github_token_manager import (
    add_public_token,
    remove_public_token,
    update_public_token,
    list_public_tokens,
    get_public_token_by_id,
    get_tokens_pool_status,
    verify_github_token,
    get_token_rate_limit,
    hash_token,
    mask_token,
    get_raw_token_from_cache,
    PublicTokenStatus,
)

router = APIRouter(prefix="/tokens", tags=["GitHub Tokens"])


class RefreshAllResponse(BaseModel):
    """Response for refresh all tokens."""

    refreshed: int
    failed: int
    results: List[dict]


@router.post("/refresh-all", response_model=RefreshAllResponse)
async def refresh_all_tokens(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Refresh rate limit info for all tokens by querying GitHub API.

    Uses tokens from in-memory cache (seeded from GITHUB_TOKENS env var).
    This is the recommended way to update token stats.
    """
    from datetime import datetime, timezone
    from bson import ObjectId

    tokens = list(
        db.github_tokens.find({"status": {"$ne": PublicTokenStatus.DISABLED}})
    )
    results = []
    refreshed = 0
    failed = 0

    for token_doc in tokens:
        token_id = str(token_doc["_id"])
        token_hash = token_doc.get("token_hash")

        if not token_hash:
            results.append({"id": token_id, "success": False, "error": "No token hash"})
            failed += 1
            continue

        # Get raw token from cache
        raw_token = get_raw_token_from_cache(token_hash)
        if not raw_token:
            results.append(
                {
                    "id": token_id,
                    "success": False,
                    "error": "Token not in cache (add to GITHUB_TOKENS env var)",
                }
            )
            failed += 1
            continue

        # Query GitHub API for rate limit
        rate_limit_info = await get_token_rate_limit(raw_token)

        if rate_limit_info:
            update_data = {
                "rate_limit_remaining": rate_limit_info["remaining"],
                "rate_limit_limit": rate_limit_info["limit"],
                "rate_limit_reset_at": rate_limit_info["reset_at"],
                "last_validated_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }

            # Update status based on remaining
            if rate_limit_info["remaining"] == 0:
                update_data["status"] = PublicTokenStatus.RATE_LIMITED
            else:
                update_data["status"] = PublicTokenStatus.ACTIVE
                update_data["validation_error"] = None

            db.github_tokens.update_one(
                {"_id": ObjectId(token_id)},
                {"$set": update_data},
            )

            results.append(
                {
                    "id": token_id,
                    "success": True,
                    "remaining": rate_limit_info["remaining"],
                    "limit": rate_limit_info["limit"],
                }
            )
            refreshed += 1
        else:
            # Token might be invalid
            db.github_tokens.update_one(
                {"_id": ObjectId(token_id)},
                {
                    "$set": {
                        "status": PublicTokenStatus.INVALID,
                        "validation_error": "Failed to get rate limit",
                        "last_validated_at": datetime.now(timezone.utc),
                    }
                },
            )
            results.append(
                {
                    "id": token_id,
                    "success": False,
                    "error": "Failed to get rate limit from GitHub API",
                }
            )
            failed += 1

    return RefreshAllResponse(refreshed=refreshed, failed=failed, results=results)


@router.get("/", response_model=TokenListResponse)
async def list_tokens(
    include_disabled: bool = False,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all GitHub tokens (masked, without actual token values)."""
    tokens = list_public_tokens(db, include_disabled=include_disabled)
    return TokenListResponse(
        items=[TokenResponse(**t) for t in tokens],
        total=len(tokens),
    )


@router.get("/status", response_model=TokenPoolStatusResponse)
async def get_pool_status(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get overall status of the token pool."""
    status_data = get_tokens_pool_status(db)
    return TokenPoolStatusResponse(**status_data)


@router.post("/", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def create_token(
    request: TokenCreateRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Add a new GitHub token to the pool.

    The token will be hashed for secure storage - we never store the plaintext.
    """
    success, result, error_type = add_public_token(
        db,
        token=request.token,
        label=request.label or "",
    )

    if not success:
        if error_type == "duplicate_error":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=result,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result,
        )

    # Get the created token info
    token_info = get_public_token_by_id(db, result)
    if not token_info:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve created token",
        )

    return TokenResponse(**token_info)


@router.get("/{token_id}", response_model=TokenResponse)
async def get_token(
    token_id: str = Path(..., description="Token ID"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get details of a specific token."""
    token_info = get_public_token_by_id(db, token_id)
    if not token_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )
    return TokenResponse(**token_info)


@router.patch("/{token_id}", response_model=TokenResponse)
async def update_token(
    token_id: str = Path(..., description="Token ID"),
    request: TokenUpdateRequest = Body(...),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update a token's label or status."""
    # Check token exists
    existing = get_public_token_by_id(db, token_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )

    # Validate status if provided
    if request.status is not None:
        if request.status not in [PublicTokenStatus.ACTIVE, PublicTokenStatus.DISABLED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be '{PublicTokenStatus.ACTIVE}' or '{PublicTokenStatus.DISABLED}'",
            )

    success = update_public_token(
        db,
        token_id=token_id,
        label=request.label,
        status=request.status,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update token",
        )

    # Return updated token
    token_info = get_public_token_by_id(db, token_id)
    return TokenResponse(**token_info)


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_token(
    token_id: str = Path(..., description="Token ID"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Remove a token from the pool."""
    success = remove_public_token(db, token_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )
    return None


@router.post("/{token_id}/verify", response_model=TokenVerifyResponse)
async def verify_token(
    token_id: str = Path(..., description="Token ID"),
    raw_token: Optional[str] = Body(
        None, embed=True, description="Raw token for verification"
    ),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Verify a token is still valid by calling GitHub API.

    Note: For security, we don't store raw tokens. To verify, you must provide
    the raw token value. This is typically used right after adding a new token.
    """
    # Check token exists in database
    existing = get_public_token_by_id(db, token_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="raw_token is required for verification",
        )

    # Verify the provided token matches the stored hash
    provided_hash = hash_token(raw_token)
    token_doc = db.github_tokens.find_one({"_id": token_id})

    # If we can't verify the hash matches (security), just validate the provided token
    is_valid, rate_limit_info = await verify_github_token(raw_token)

    if is_valid:
        # Update token status in database
        from datetime import datetime, timezone
        from bson import ObjectId

        update_data = {
            "status": PublicTokenStatus.ACTIVE,
            "last_validated_at": datetime.now(timezone.utc),
            "validation_error": None,
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

        return TokenVerifyResponse(
            valid=True,
            rate_limit_remaining=(
                rate_limit_info["remaining"] if rate_limit_info else None
            ),
            rate_limit_limit=rate_limit_info["limit"] if rate_limit_info else None,
        )
    else:
        # Mark as invalid
        from datetime import datetime, timezone
        from bson import ObjectId

        db.github_tokens.update_one(
            {"_id": ObjectId(token_id)},
            {
                "$set": {
                    "status": PublicTokenStatus.INVALID,
                    "validation_error": "Token is invalid or revoked",
                    "last_validated_at": datetime.now(timezone.utc),
                },
            },
        )

        return TokenVerifyResponse(
            valid=False,
            error="Token is invalid or revoked",
        )
