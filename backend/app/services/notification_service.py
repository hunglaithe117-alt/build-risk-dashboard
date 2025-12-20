"""
Unified Notification Service - In-app and Gmail API notifications.

Channels:
- In-app: Always sent, stored in MongoDB for UI display
- Gmail: Gmail API (OAuth2) for critical alerts only

Gmail API Setup:
1. Create a project in Google Cloud Console
2. Enable Gmail API
3. Create OAuth 2.0 credentials (Desktop app)
4. Run: python -m app.services.gmail_api_service --setup
5. Set environment variables:
   - GOOGLE_CLIENT_ID: OAuth client ID
   - GOOGLE_CLIENT_SECRET: OAuth client secret
   - GMAIL_TOKEN_JSON: Token JSON from setup script

Channel Usage Guidelines:
┌─────────────────────────────────┬─────────┬─────────┐
│ Event Type                      │ In-App  │ Gmail   │
├─────────────────────────────────┼─────────┼─────────┤
│ Pipeline completed              │ ✓       │         │
│ Pipeline failed                 │ ✓       │         │
│ Dataset validation completed    │ ✓       │         │
│ Dataset enrichment completed    │ ✓       │         │
│ Scan vulnerabilities found      │ ✓       │         │
│ Rate limit WARNING              │ ✓       │         │
│ Rate limit EXHAUSTED (all)      │ ✓       │ ✓ *     │
│ System alerts                   │ ✓       │         │
└─────────────────────────────────┴─────────┴─────────┘
* Gmail only for critical alerts when all tokens are exhausted
"""

import logging
from datetime import datetime
from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.entities.notification import Notification, NotificationType
from app.repositories.notification import NotificationRepository
from app.services.email_templates import render_email

logger = logging.getLogger(__name__)


# =============================================================================
# NotificationService - CRUD operations for API Layer
# =============================================================================


class NotificationService:
    """
    Service for notification CRUD operations.

    Used by API layer following the layered architecture pattern:
    API -> Service -> Repository -> Database
    """

    def __init__(self, db: Database):
        self.db = db
        self.notification_repo = NotificationRepository(db)

    def list_notifications(
        self,
        user_id: ObjectId,
        skip: int = 0,
        limit: int = 20,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int, int]:
        """
        List notifications for a user.

        Returns: (items, total, unread_count)
        """
        items, total = self.notification_repo.find_by_user(
            user_id, skip=skip, limit=limit, unread_only=unread_only
        )
        unread_count = self.notification_repo.count_unread(user_id)
        return items, total, unread_count

    def get_unread_count(self, user_id: ObjectId) -> int:
        """Get the count of unread notifications for a user."""
        return self.notification_repo.count_unread(user_id)

    def mark_as_read(self, user_id: ObjectId, notification_id: str) -> bool:
        """
        Mark a single notification as read.

        Raises HTTPException if notification not found or not owned by user.
        """
        from fastapi import HTTPException

        notification = self.notification_repo.find_by_id(notification_id)
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")

        if notification.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        return self.notification_repo.mark_as_read(ObjectId(notification_id))

    def mark_all_as_read(self, user_id: ObjectId) -> int:
        """Mark all notifications as read for a user."""
        return self.notification_repo.mark_all_as_read(user_id)

    def create_notification(
        self,
        user_id: ObjectId,
        notification_type: NotificationType,
        title: str,
        message: str,
        link: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Notification:
        """Create a new notification."""
        notification = Notification(
            user_id=user_id,
            type=notification_type,
            title=title,
            message=message,
            link=link,
            metadata=metadata,
        )
        return self.notification_repo.insert_one(notification)


# =============================================================================
# Multi-Channel Notification Manager
# =============================================================================


class NotificationManager:
    """
    Unified notification manager that sends to multiple channels.

    Channels:
    - In-app: MongoDB stored notifications (always)
    - Gmail: Gmail API (OAuth2) for critical alerts (optional)
    """

    def __init__(
        self,
        db: Optional[Database] = None,
    ):
        self.db = db

    # -------------------------------------------------------------------------
    # In-App Notifications (MongoDB)
    # -------------------------------------------------------------------------

    def create_in_app(
        self,
        user_id: ObjectId,
        type: NotificationType,
        title: str,
        message: str,
        link: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[Notification]:
        """Create an in-app notification stored in MongoDB."""
        if not self.db:
            logger.warning("Database not configured for in-app notifications")
            return None

        repo = NotificationRepository(self.db)
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            link=link,
            metadata=metadata,
        )
        return repo.insert_one(notification)

    # -------------------------------------------------------------------------
    # Gmail Notifications
    # -------------------------------------------------------------------------

    def send_gmail(
        self,
        subject: str,
        body: str,
        to_recipients: List[str],
        html_body: Optional[str] = None,
    ) -> bool:
        """
        Send an email via Gmail API (OAuth2).

        Args:
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            to_recipients: List of email addresses to send to.

        Returns:
            True if sent successfully, False otherwise
        """
        if len(to_recipients) == 0:
            logger.debug("No Gmail recipients specified")
            return False

        try:
            from app.services.gmail_api_service import (
                is_gmail_api_available,
                send_email_via_gmail_api,
            )

            if not is_gmail_api_available():
                logger.warning("Gmail API is not configured or available")
                return False

            return send_email_via_gmail_api(
                to=to_recipients,
                subject=subject,
                body=body,
                html_body=html_body,
            )
        except ImportError:
            logger.error(
                "Gmail API dependencies not installed. "
                "Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )
            return False
        except Exception as e:
            logger.error(f"Gmail API error: {e}")
            return False


_manager: Optional[NotificationManager] = None


def get_notification_manager(db: Optional[Database] = None) -> NotificationManager:
    """Get or create the global notification manager."""
    global _manager
    if _manager is None or (db and _manager.db is None):
        _manager = NotificationManager(db=db)
    return _manager


# =============================================================================
# In-App Only Helpers (Backward Compatible)
# =============================================================================


def create_notification(
    db: Database,
    user_id: ObjectId,
    type: NotificationType,
    title: str,
    message: str,
    link: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Notification:
    """Create an in-app notification for a user."""
    repo = NotificationRepository(db)
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        link=link,
        metadata=metadata,
    )
    return repo.insert_one(notification)


# =============================================================================
# Event-Specific Notification Functions
# =============================================================================


def notify_pipeline_completed(
    db: Database,
    user_id: ObjectId,
    repo_name: str,
    build_id: str,
    feature_count: int,
) -> Notification:
    """Pipeline completed - in-app only (not urgent)."""
    return create_notification(
        db=db,
        user_id=user_id,
        type=NotificationType.PIPELINE_COMPLETED,
        title="Pipeline Completed",
        message=f"Feature extraction for {repo_name} build #{build_id} completed. {feature_count} features extracted.",
        link="/admin/repos",
        metadata={
            "repo_name": repo_name,
            "build_id": build_id,
            "feature_count": feature_count,
        },
    )


def notify_pipeline_failed(
    db: Database,
    user_id: ObjectId,
    repo_name: str,
    build_id: str,
    error: str,
) -> Notification:
    """Pipeline failed - in-app only."""
    return create_notification(
        db=db,
        user_id=user_id,
        type=NotificationType.PIPELINE_FAILED,
        title="Pipeline Failed",
        message=f"Feature extraction for {repo_name} build #{build_id} failed: {error}",
        link="/admin/repos",
        metadata={"repo_name": repo_name, "build_id": build_id, "error": error},
    )


def notify_dataset_validation_completed(
    db: Database,
    user_id: ObjectId,
    dataset_name: str,
    dataset_id: str,
    repos_valid: int,
    repos_invalid: int,
) -> Notification:
    """Dataset validation completed - in-app only."""
    return create_notification(
        db=db,
        user_id=user_id,
        type=NotificationType.DATASET_VALIDATION_COMPLETED,
        title="Dataset Validation Completed",
        message=f"Validation for '{dataset_name}' completed. {repos_valid} valid, {repos_invalid} invalid repos.",
        link=f"/admin/datasets/{dataset_id}",
        metadata={
            "dataset_id": dataset_id,
            "repos_valid": repos_valid,
            "repos_invalid": repos_invalid,
        },
    )


def notify_dataset_enrichment_completed(
    db: Database,
    user_id: ObjectId,
    dataset_name: str,
    dataset_id: str,
    enriched_rows: int,
    total_rows: int,
) -> Notification:
    """Dataset enrichment completed - in-app only."""
    return create_notification(
        db=db,
        user_id=user_id,
        type=NotificationType.DATASET_ENRICHMENT_COMPLETED,
        title="Dataset Enrichment Completed",
        message=f"Enrichment for '{dataset_name}' completed. {enriched_rows}/{total_rows} rows enriched.",
        link=f"/admin/datasets/{dataset_id}",
        metadata={
            "dataset_id": dataset_id,
            "enriched_rows": enriched_rows,
            "total_rows": total_rows,
        },
    )


def notify_scan_vulnerabilities_found(
    db: Database,
    user_id: ObjectId,
    repo_name: str,
    scan_type: str,
    issues_count: int,
) -> Notification:
    """Scan found vulnerabilities - in-app only."""
    return create_notification(
        db=db,
        user_id=user_id,
        type=NotificationType.SCAN_VULNERABILITIES_FOUND,
        title=f"{scan_type.capitalize()} Scan: Issues Found",
        message=f"{scan_type.capitalize()} scan for {repo_name} found {issues_count} issues.",
        link="/admin/repos",
        metadata={
            "repo_name": repo_name,
            "scan_type": scan_type,
            "issues_count": issues_count,
        },
    )


# =============================================================================
# GitHub Token Rate Limit Notifications
# =============================================================================


def notify_rate_limit_warning(
    db: Database,
    user_id: ObjectId,
    token_label: str,
    remaining: int,
    reset_at: datetime,
) -> Notification:
    """
    Single token rate limit warning - in-app only.

    Use when a token is running low but not exhausted.
    """
    reset_str = reset_at.strftime("%H:%M UTC") if reset_at else "soon"

    return create_notification(
        db=db,
        user_id=user_id,
        type=NotificationType.RATE_LIMIT_WARNING,
        title="GitHub Rate Limit Warning",
        message=f"Token '{token_label}' has only {remaining} requests remaining. Resets at {reset_str}.",
        link="/admin/settings",
        metadata={
            "token_label": token_label,
            "remaining": remaining,
            "reset_at": reset_str,
        },
    )


def notify_rate_limit_exhausted(
    db: Database,
    user_id: ObjectId,
    exhausted_tokens: int,
    total_tokens: int,
    next_reset_at: Optional[datetime] = None,
    send_gmail: bool = True,
) -> Notification:
    """
    All tokens exhausted - CRITICAL - in-app + Gmail.

    Use when ALL tokens are rate limited and the system cannot make GitHub API calls.
    This is critical because it blocks all data ingestion.
    """
    reset_str = next_reset_at.strftime("%H:%M UTC") if next_reset_at else "unknown"

    notification = create_notification(
        db=db,
        user_id=user_id,
        type=NotificationType.RATE_LIMIT_EXHAUSTED,
        title="🚨 All GitHub Tokens Exhausted",
        message=f"All {exhausted_tokens}/{total_tokens} tokens are rate limited. GitHub API calls blocked until {reset_str}.",
        link="/admin/settings",
        metadata={
            "exhausted_tokens": exhausted_tokens,
            "total_tokens": total_tokens,
            "next_reset_at": reset_str,
        },
    )

    # Gmail - for critical alerts using Handlebars template
    if send_gmail:
        manager = get_notification_manager()
        html_body = render_email(
            "rate_limit_exhausted",
            {
                "exhausted_tokens": exhausted_tokens,
                "total_tokens": total_tokens,
                "next_reset_at": reset_str,
            },
            subject="🚨 CRITICAL: All GitHub Tokens Exhausted",
        )
        manager.send_gmail(
            subject="🚨 CRITICAL: All GitHub Tokens Exhausted",
            body="",  # HTML only
            html_body=html_body,
        )

    return notification


def notify_system_alert(
    db: Database,
    user_id: ObjectId,
    title: str,
    message: str,
) -> Notification:
    """Generic system alert - in-app only."""
    return create_notification(
        db=db,
        user_id=user_id,
        type=NotificationType.SYSTEM,
        title=title,
        message=message,
        link=None,
        metadata=None,
    )
