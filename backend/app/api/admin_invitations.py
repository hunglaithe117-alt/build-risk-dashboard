"""
Admin Invitations API - Endpoints for managing user invitations.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Path, Query, status
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos.invitation import (
    InvitationCreateRequest,
    InvitationListResponse,
    InvitationResponse,
)
from app.middleware.rbac import Permission, RequirePermission
from app.services.invitation_service import InvitationService

router = APIRouter(prefix="/admin/invitations", tags=["Admin - Invitations"])


@router.get(
    "/",
    response_model=InvitationListResponse,
    response_model_by_alias=False,
)
def list_invitations(
    status: Optional[str] = Query(
        None, description="Filter by status: pending, accepted, expired, revoked"
    ),
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.MANAGE_USERS)),
):
    """List all invitations (Admin only)."""
    service = InvitationService(db)
    return service.list_invitations(status_filter=status)


@router.post(
    "/",
    response_model=InvitationResponse,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    payload: InvitationCreateRequest,
    db: Database = Depends(get_db),
    admin: dict = Depends(RequirePermission(Permission.MANAGE_USERS)),
):
    """
    Create a new invitation (Admin only).

    Sends an email to the invited user with a link to accept the invitation.
    The invitation expires after 7 days.
    """
    from bson import ObjectId

    admin_id = ObjectId(admin["_id"]) if isinstance(admin["_id"], str) else admin["_id"]
    service = InvitationService(db)
    return service.create_invitation(payload, admin_id)


@router.get(
    "/{invitation_id}",
    response_model=InvitationResponse,
    response_model_by_alias=False,
)
def get_invitation(
    invitation_id: str = Path(..., description="Invitation ID"),
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.MANAGE_USERS)),
):
    """Get invitation details (Admin only)."""
    service = InvitationService(db)
    return service.get_invitation(invitation_id)


@router.delete(
    "/{invitation_id}",
    response_model=InvitationResponse,
    response_model_by_alias=False,
)
def revoke_invitation(
    invitation_id: str = Path(..., description="Invitation ID"),
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.MANAGE_USERS)),
):
    """
    Revoke a pending invitation (Admin only).

    Only pending invitations can be revoked.
    """
    service = InvitationService(db)
    return service.revoke_invitation(invitation_id)
