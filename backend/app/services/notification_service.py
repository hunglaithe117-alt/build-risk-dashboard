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
        cursor: str | None = None,
    ) -> tuple[list[Notification], int, int, str | None]:
        """
        List notifications for a user.

        Returns: (items, total, unread_count, next_cursor)
        """
        # If cursor is provided, we should typically ignore skip, but repo handles logic
        items, total = self.notification_repo.find_by_user(
            user_id, skip=skip, limit=limit, unread_only=unread_only, cursor_id=cursor
        )
        unread_count = self.notification_repo.count_unread(user_id)

        next_cursor = None
        if items and len(items) == limit:
            # We explicitly check against limit to determine if there might be more
            # The next cursor is the ID of the last item
            next_cursor = str(items[-1].id)

        return items, total, unread_count, next_cursor

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

    def notify_rate_limit_exhausted(
        self,
        retry_after: Optional[datetime] = None,
        task_name: Optional[str] = None,
    ) -> None:
        """
        Notify admins when all GitHub tokens are exhausted.

        Called from Celery tasks when GithubAllRateLimitError is raised after max retries.
        Sends in-app notifications to all admin users and Gmail alert.

        Args:
            retry_after: datetime when tokens will reset
            task_name: Name of the task that triggered the notification
        """
        from app.repositories.user import UserRepository
        from app.services.github.redis_token_pool import get_redis_token_pool

        # Get token pool status
        try:
            pool = get_redis_token_pool()
            pool_status = pool.get_pool_status()
            total_tokens = pool_status.get("total_tokens", 0)
            rate_limited = pool_status.get("rate_limited_tokens", 0)
        except Exception:
            total_tokens = 0
            rate_limited = 0

        reset_str = retry_after.strftime("%H:%M UTC") if retry_after else "unknown"

        # Find all admin users
        user_repo = UserRepository(self.db)
        admin_users = user_repo.find_by_role("admin")

        for admin in admin_users:
            try:
                self.create_notification(
                    user_id=admin.id,
                    notification_type=NotificationType.RATE_LIMIT_EXHAUSTED,
                    title="🚨 All GitHub Tokens Exhausted",
                    message=f"All {rate_limited}/{total_tokens} tokens are rate limited. "
                    f"Task '{task_name}' failed. Tokens reset at {reset_str}.",
                    link="/admin/settings",
                    metadata={
                        "rate_limited_tokens": rate_limited,
                        "total_tokens": total_tokens,
                        "next_reset_at": reset_str,
                        "task_name": task_name,
                    },
                )
            except Exception as e:
                logger.warning(
                    f"Failed to create notification for admin {admin.id}: {e}"
                )

        # Send Gmail alert to admins
        try:
            manager = get_notification_manager(self.db)
            admin_emails = [admin.email for admin in admin_users if admin.email]
            if admin_emails:
                html_body = render_email(
                    "rate_limit_exhausted",
                    {
                        "exhausted_tokens": rate_limited,
                        "total_tokens": total_tokens,
                        "next_reset_at": reset_str,
                        "task_name": task_name,
                    },
                    subject="🚨 CRITICAL: All GitHub Tokens Exhausted",
                )
                manager.send_gmail(
                    subject="🚨 CRITICAL: All GitHub Tokens Exhausted",
                    html_body=html_body,
                    to_recipients=admin_emails,
                )
        except Exception as e:
            logger.warning(f"Failed to send Gmail notification: {e}")


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
        result = repo.insert_one(notification)

        # Publish real-time event
        try:
            from app.tasks.shared.events import publish_event

            payload = {
                "user_id": str(user_id),
                "type": type.value,
                "title": title,
                "message": message,
                "link": link,
                "metadata": metadata,
                "created_at": (
                    result.created_at.isoformat() if result.created_at else None
                ),
            }
            publish_event("USER_NOTIFICATION", payload)
        except Exception as e:
            logger.warning(f"Failed to publish user notification event: {e}")

        return result

    # -------------------------------------------------------------------------
    # Gmail Notifications
    # -------------------------------------------------------------------------

    def send_gmail(
        self,
        subject: str,
        to_recipients: List[str],
        html_body: str,
    ) -> bool:
        """
        Send an email via Gmail API (OAuth2).

        Args:
            subject: Email subject
            html_body: HTML body
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
    result = repo.insert_one(notification)

    # Publish real-time event
    try:
        from app.tasks.shared.events import publish_event

        payload = {
            "user_id": str(user_id),
            "type": type.value,
            "title": title,
            "message": message,
            "link": link,
            "metadata": metadata,
            "created_at": result.created_at.isoformat() if result.created_at else None,
        }
        publish_event("USER_NOTIFICATION", payload)
    except Exception as e:
        logger.warning(f"Failed to publish user notification event: {e}")

    return result


def _send_admin_email(
    db: Database,
    notification_type: str,
    template_name: str,
    subject: str,
    context: dict,
) -> bool:
    """
    Send email to admin recipients if the notification type is enabled.

    Checks ApplicationSettings.notifications for:
    1. email_enabled (master toggle)
    2. email_recipients (list of emails)
    3. email_type_toggles[notification_type] (per-type toggle)

    Returns True if email was sent, False otherwise.
    """
    try:
        from app.repositories.settings import SettingsRepository

        settings_repo = SettingsRepository(db)
        settings = settings_repo.get_settings()

        # Check master toggle
        if not settings.notifications.email_enabled:
            logger.debug(f"Admin email disabled (master toggle off)")
            return False

        # Check per-type toggle
        toggles = settings.notifications.email_type_toggles
        toggle_key = notification_type.replace(
            "-", "_"
        )  # e.g. pipeline-failed -> pipeline_failed
        if not getattr(toggles, toggle_key, False):
            logger.debug(
                f"Admin email for {notification_type} disabled (type toggle off)"
            )
            return False

        # Get recipients
        recipients_str = settings.notifications.email_recipients or ""
        recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]
        if not recipients:
            logger.debug(f"No admin email recipients configured")
            return False

        # Render and send email
        manager = get_notification_manager()
        html_body = render_email(template_name, context, subject=subject)
        return manager.send_gmail(
            subject=subject,
            html_body=html_body,
            to_recipients=recipients,
        )
    except Exception as e:
        logger.warning(f"Failed to send admin email for {notification_type}: {e}")
        return False


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


def notify_dataset_enrichment_completed(
    db: Database,
    user_id: ObjectId,
    dataset_name: str,
    scenario_id: str,
    builds_features_extracted: int,
    builds_total: int,
) -> Notification:
    """Dataset enrichment completed - in-app only."""
    return create_notification(
        db=db,
        user_id=user_id,
        type=NotificationType.DATASET_ENRICHMENT_COMPLETED,
        title="Dataset Enrichment Completed",
        message=f"Enrichment for '{dataset_name}' completed. {builds_features_extracted}/{builds_total} builds processed.",
        link=f"/scenarios/{scenario_id}",
        metadata={
            "dataset_id": scenario_id,
            "builds_features_extracted": builds_features_extracted,
            "builds_total": builds_total,
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
            html_body=html_body,
            # TODO: Add to_recipients here
            to_recipients=["hunglaithe117@gmail.com"],
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


def notify_system_error_to_admins(
    db: Database,
    source: str,
    message: str,
    correlation_id: Optional[str] = None,
) -> None:
    """
    Notify all admins about a system error.

    Called from MongoDBLogHandler when ERROR/CRITICAL logs occur.
    Sends in-app notifications and optionally email if system_alerts toggle is enabled.

    Args:
        db: Database connection
        source: Log source/module name
        message: Error message (truncated to 500 chars)
        correlation_id: Correlation ID for Loki cross-reference
    """
    from app.repositories.user import UserRepository

    # Truncate message to avoid huge notifications
    truncated_message = message[:500] + "..." if len(message) > 500 else message

    # Find all admin users
    user_repo = UserRepository(db)
    admin_users = user_repo.find_by_role("admin")

    # In-app notifications
    for admin in admin_users:
        try:
            create_notification(
                db=db,
                user_id=admin.id,
                type=NotificationType.SYSTEM,
                title=f"⚠️ System Error: {source}",
                message=truncated_message,
                link="/admin/monitoring",
                metadata={
                    "source": source,
                    "correlation_id": correlation_id,
                },
            )
        except Exception as e:
            logger.warning(
                f"Failed to create error notification for admin {admin.id}: {e}"
            )

    # Email notification (if enabled via system_alerts toggle)
    _send_admin_email(
        db=db,
        notification_type="system_alerts",
        template_name="system_error",
        subject=f"⚠️ System Error: {source}",
        context={
            "source": source,
            "message": truncated_message,
            "correlation_id": correlation_id or "N/A",
        },
    )


# =============================================================================
# User-Facing Notifications
# =============================================================================


def notify_prediction_ready(
    db: Database,
    user_id: ObjectId,
    repo_name: str,
    repo_id: str,
    high_count: int = 0,
    medium_count: int = 0,
    low_count: int = 0,
) -> Notification:
    """
    Notify user when predictions complete for their repo.

    Summary notification sent after prediction phase finishes.
    """
    total = high_count + medium_count + low_count
    message = f"{repo_name}: {total} builds analyzed."
    if high_count > 0:
        message += f" {high_count} HIGH risk."
    if medium_count > 0:
        message += f" {medium_count} MEDIUM risk."

    return create_notification(
        db=db,
        user_id=user_id,
        type=NotificationType.BUILD_PREDICTION_READY,
        title="🎯 Predictions Ready",
        message=message,
        link=f"/my-repos/{repo_id}/builds",
        metadata={
            "repo_name": repo_name,
            "repo_id": repo_id,
            "high_count": high_count,
            "medium_count": medium_count,
            "low_count": low_count,
            "total": total,
        },
    )


def notify_high_risk_builds_batch(
    db: Database,
    user_id: ObjectId,
    repo_name: str,
    repo_id: str,
    ci_run_ids: List[str],
) -> Notification:
    """
    Aggregated notification for multiple HIGH risk builds in one processing batch.

    Instead of sending individual notifications per build, this combines
    all high-risk builds from the same processing run into a single alert.
    """
    count = len(ci_run_ids)
    if count == 0:
        return None

    # Format ci_run_ids for display (show first 5, then "and X more")
    if count <= 5:
        builds_str = ", ".join(ci_run_ids)
    else:
        first_five = ", ".join(ci_run_ids[:5])
        builds_str = f"{first_five} and {count - 5} more"

    return create_notification(
        db=db,
        user_id=user_id,
        type=NotificationType.HIGH_RISK_DETECTED,
        title=f"⚠️ {count} High Risk Build{'s' if count > 1 else ''} Detected",
        message=f"{repo_name}: Builds {builds_str} predicted as HIGH risk.",
        link=f"/repositories/{repo_id}/builds?risk=HIGH",
        metadata={
            "repo_name": repo_name,
            "repo_id": repo_id,
            "ci_run_ids": ci_run_ids,
            "count": count,
            "risk_level": "HIGH",
        },
    )


def notify_users_for_repo(
    db: Database,
    raw_repo_id: ObjectId,
    repo_name: str,
    repo_id: str,
    high_risk_builds: Optional[List[dict]] = None,
    prediction_summary: Optional[dict] = None,
) -> None:
    """
    Notify all users with access to a repository about predictions.

    Respects user subscription preferences for in-app and email notifications.

    Args:
        db: Database connection
        raw_repo_id: RawRepository ObjectId (for user access lookup)
        repo_name: Repository full name for display
        repo_id: ModelRepoConfig ID for links
        high_risk_builds: List of HIGH risk build dicts (aggregated into single notification)
        prediction_summary: Dict with high/medium/low counts
    """
    from app.repositories.user import UserRepository

    user_repo = UserRepository(db)
    users = user_repo.find_users_with_repo_access(raw_repo_id)

    for user in users:
        try:
            # Get user's subscription preferences
            subscriptions = getattr(user, "subscriptions", {}) or {}
            email_enabled = getattr(user, "email_notifications_enabled", False)
            user_email = getattr(user, "notification_email", None) or user.email

            # HIGH RISK DETECTED notifications
            if high_risk_builds and len(high_risk_builds) > 0:
                high_risk_sub = subscriptions.get("high_risk_detected", {})
                send_in_app = (
                    high_risk_sub.get("in_app", True) if high_risk_sub else True
                )
                send_email = (
                    high_risk_sub.get("email", False) if high_risk_sub else False
                )

                ci_run_ids = [b.get("ci_run_id", "") for b in high_risk_builds]
                count = len(ci_run_ids)

                # In-app notification
                if send_in_app:
                    notify_high_risk_builds_batch(
                        db=db,
                        user_id=user.id,
                        repo_name=repo_name,
                        repo_id=repo_id,
                        ci_run_ids=ci_run_ids,
                    )

                # Email notification (if user enabled and subscribed)
                if send_email and email_enabled and user_email:
                    _send_high_risk_email(
                        to_email=user_email,
                        repo_name=repo_name,
                        repo_id=repo_id,
                        ci_run_ids=ci_run_ids,
                        count=count,
                    )

            # BUILD PREDICTION READY notifications
            if prediction_summary:
                pred_sub = subscriptions.get("build_prediction_ready", {})
                send_in_app = pred_sub.get("in_app", True) if pred_sub else True

                if send_in_app:
                    notify_prediction_ready(
                        db=db,
                        user_id=user.id,
                        repo_name=repo_name,
                        repo_id=repo_id,
                        high_count=prediction_summary.get("high", 0),
                        medium_count=prediction_summary.get("medium", 0),
                        low_count=prediction_summary.get("low", 0),
                    )

        except Exception as e:
            logger.warning(f"Failed to notify user {user.id} for repo {repo_name}: {e}")


def _send_high_risk_email(
    to_email: str,
    repo_name: str,
    repo_id: str,
    ci_run_ids: List[str],
    count: int,
) -> bool:
    """Send email alert for high-risk builds to a user."""
    try:
        # Format builds for email
        if count <= 5:
            builds_str = ", ".join(ci_run_ids)
        else:
            first_five = ", ".join(ci_run_ids[:5])
            builds_str = f"{first_five} and {count - 5} more"

        manager = get_notification_manager()
        html_body = render_email(
            "high_risk_detected",
            {
                "repo_name": repo_name,
                "builds_str": builds_str,
                "count": count,
                "link": f"/repositories/{repo_id}/builds?risk=HIGH",
            },
            subject=f"⚠️ {count} High Risk Build{'s' if count > 1 else ''} Detected",
        )
        return manager.send_gmail(
            subject=f"⚠️ {count} High Risk Build{'s' if count > 1 else ''} in {repo_name}",
            html_body=html_body,
            to_recipients=[to_email],
        )
    except Exception as e:
        logger.warning(f"Failed to send high-risk email to {to_email}: {e}")
        return False


# =============================================================================
# Admin Notifications - Model Pipeline
# =============================================================================


def notify_pipeline_completed_to_admins(
    db: Database,
    repo_name: str,
    predicted_count: int,
    failed_count: int,
    high_count: int = 0,
    medium_count: int = 0,
    low_count: int = 0,
) -> None:
    """
    Notify all admins when Model Pipeline prediction phase completes.

    Called from finalize_prediction task.
    """
    from app.repositories.user import UserRepository

    user_repo = UserRepository(db)
    admin_users = user_repo.find_by_role("admin")

    total = high_count + medium_count + low_count
    message = f"{repo_name}: {predicted_count}/{total} predicted."
    if failed_count > 0:
        message += f" {failed_count} failed."
    if high_count > 0:
        message += f" {high_count} HIGH risk."

    for admin in admin_users:
        try:
            create_notification(
                db=db,
                user_id=admin.id,
                type=NotificationType.PIPELINE_COMPLETED,
                title="✅ Pipeline Complete",
                message=message,
                link="/repositories",
                metadata={
                    "repo_name": repo_name,
                    "predicted": predicted_count,
                    "failed": failed_count,
                    "high": high_count,
                    "medium": medium_count,
                    "low": low_count,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to notify admin {admin.id}: {e}")


def notify_pipeline_failed_to_admins(
    db: Database,
    repo_name: str,
    error_message: str,
) -> None:
    """
    Notify all admins when Model Pipeline fails completely.
    Sends in-app notification to all admins and optionally email if enabled.
    """
    from app.repositories.user import UserRepository

    user_repo = UserRepository(db)
    admin_users = user_repo.find_by_role("admin")

    # In-app notifications
    for admin in admin_users:
        try:
            create_notification(
                db=db,
                user_id=admin.id,
                type=NotificationType.PIPELINE_FAILED,
                title="❌ Pipeline Failed",
                message=f"{repo_name}: {error_message[:200]}",
                link="/repositories",
                metadata={
                    "repo_name": repo_name,
                    "error": error_message,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to notify admin {admin.id}: {e}")

    # Email notification (if enabled)
    _send_admin_email(
        db=db,
        notification_type="pipeline_failed",
        template_name="pipeline_failed",
        subject=f"❌ Pipeline Failed: {repo_name}",
        context={
            "repo_name": repo_name,
            "error_message": error_message[:500],
        },
    )


# =============================================================================
# Admin Notifications - Dataset Enrichment
# =============================================================================


def notify_dataset_enrichment_failed(
    db: Database,
    scenario_id: str,
    error_message: str,
    completed_count: int = 0,
    failed_count: int = 0,
) -> None:
    """
    Notify scenario creator when enrichment processing chain fails.
    """
    from app.repositories.training_scenario import TrainingScenarioRepository

    scenario_repo = TrainingScenarioRepository(db)
    scenario = scenario_repo.find_by_id(scenario_id)
    if not scenario:
        logger.warning(f"Scenario {scenario_id} not found for failure notification")
        return

    if not scenario.created_by:
        logger.warning(f"Scenario {scenario_id} has no creator to notify")
        return

    message = f"{scenario.name}: {completed_count} completed, {failed_count} failed."
    if error_message:
        # Truncate long error messages
        short_error = (
            error_message[:100] + "..." if len(error_message) > 100 else error_message
        )
        message += f" Error: {short_error}"

    create_notification(
        db=db,
        user_id=scenario.created_by,
        type=NotificationType.DATASET_ENRICHMENT_FAILED,
        title="⚠️ Enrichment Failed",
        message=message,
        link=f"/scenarios/{scenario_id}",
        metadata={
            "dataset_name": scenario.name,
            "dataset_id": scenario_id,
            "completed_count": completed_count,
            "failed_count": failed_count,
            "error": error_message,
            "status": "failed",
        },
    )


def check_and_notify_enrichment_completed(
    db: Database,
    scenario_id: str,
) -> bool:
    """
    Check if enrichment is fully complete (features + scan metrics) and send notification.

    Returns True if notification was sent, False if still pending.
    """
    from app.repositories.training_scenario import TrainingScenarioRepository

    scenario_repo = TrainingScenarioRepository(db)
    scenario = scenario_repo.find_by_id(scenario_id)

    if not scenario:
        logger.warning(f"Scenario {scenario_id} not found for completion check")
        return False

    # Check if all parts are done
    # 1. Feature extraction
    features_done = scenario.feature_extraction_completed

    # 2. Scans (if any configured)
    scans_done = scenario.scan_extraction_completed

    if features_done and scans_done:
        # Check if already notified/completed status to avoid spam if called multiple times?
        # The calling task usually handles state transitions.
        # But we can send the notification.

        notify_dataset_enrichment_completed(
            db=db,
            user_id=scenario.created_by,
            dataset_name=scenario.name,
            scenario_id=scenario_id,
            builds_features_extracted=scenario.builds_features_extracted,
            builds_total=scenario.builds_total,
        )
        return True

    return False
