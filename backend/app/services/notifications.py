"""
Notification Service - Send alerts via Slack, Webhook, or other channels.

Supports:
- Slack Incoming Webhooks
- Generic HTTP webhooks
- Pipeline failure alerts
- Build status notifications
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    """Types of notifications."""
    PIPELINE_FAILURE = "pipeline_failure"
    PIPELINE_SUCCESS = "pipeline_success"
    BUILD_FAILURE = "build_failure"
    IMPORT_COMPLETE = "import_complete"
    RATE_LIMIT_WARNING = "rate_limit_warning"


class NotificationService:
    """
    Service for sending notifications via various channels.

    Usage:
        service = NotificationService()
        await service.notify_pipeline_failure(
            repo_name="owner/repo",
            build_id="abc123",
            error="Connection timeout",
            pipeline_run_id="run_456"
        )
    """

    def __init__(
        self,
        slack_webhook_url: Optional[str] = None,
        custom_webhook_url: Optional[str] = None,
        enabled: bool = True,
    ):
        """
        Initialize the notification service.

        Args:
            slack_webhook_url: Slack Incoming Webhook URL
            custom_webhook_url: Custom HTTP webhook URL for other integrations
            enabled: Whether notifications are enabled
        """
        self.slack_webhook_url = slack_webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.custom_webhook_url = custom_webhook_url or os.getenv("NOTIFICATION_WEBHOOK_URL")
        self.enabled = enabled
        
        # Check if any notification channel is configured
        self.is_configured = bool(self.slack_webhook_url or self.custom_webhook_url)

    async def _send_slack_message(self, payload: Dict[str, Any]) -> bool:
        """
        Send a message to Slack via Incoming Webhook.

        Args:
            payload: Slack message payload (blocks, attachments, etc.)

        Returns:
            True if successful, False otherwise.
        """
        if not self.slack_webhook_url:
            logger.debug("Slack webhook not configured, skipping notification")
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.slack_webhook_url,
                    json=payload,
                )
                
                if response.status_code == 200:
                    logger.info("Slack notification sent successfully")
                    return True
                else:
                    logger.warning(
                        f"Slack notification failed: {response.status_code} - {response.text}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False

    async def _send_webhook(
        self, 
        url: str, 
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Send a payload to a generic HTTP webhook.

        Args:
            url: Webhook URL
            payload: JSON payload
            headers: Optional HTTP headers

        Returns:
            True if successful, False otherwise.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers or {},
                )
                return response.status_code < 400

        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")
            return False

    def _build_slack_failure_message(
        self,
        repo_name: str,
        build_id: str,
        error: str,
        pipeline_run_id: str,
        node_failures: Optional[List[str]] = None,
        retry_count: int = 0,
        duration_ms: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Build a Slack Block Kit message for pipeline failures."""
        
        # Error preview (truncate if too long)
        error_preview = error[:200] + "..." if len(error) > 200 else error
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🔴 Pipeline Failure",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Repository:*\n{repo_name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Build ID:*\n`{build_id[:8]}...`"
                    },
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error:*\n```{error_preview}```"
                }
            },
        ]

        # Add node failures if any
        if node_failures:
            nodes_text = ", ".join(node_failures[:5])
            if len(node_failures) > 5:
                nodes_text += f" (+{len(node_failures) - 5} more)"
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Failed Nodes:*\n{nodes_text}"
                }
            })

        # Add retry info if applicable
        if retry_count > 0:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"🔄 Retried {retry_count} time(s)"
                    }
                ]
            })

        # Add footer with timestamp and pipeline run ID
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Pipeline Run: `{pipeline_run_id}` • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                }
            ]
        })

        return {"blocks": blocks}

    def _build_slack_success_message(
        self,
        repo_name: str,
        feature_count: int,
        duration_ms: float,
        pipeline_run_id: str,
    ) -> Dict[str, Any]:
        """Build a Slack Block Kit message for pipeline success."""
        
        duration_str = f"{duration_ms / 1000:.1f}s" if duration_ms < 60000 else f"{duration_ms / 60000:.1f}m"
        
        return {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"✅ *Pipeline Completed*\n*{repo_name}* - {feature_count} features extracted in {duration_str}"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Run ID: `{pipeline_run_id}`"
                        }
                    ]
                }
            ]
        }

    async def notify_pipeline_failure(
        self,
        repo_name: str,
        build_id: str,
        error: str,
        pipeline_run_id: str,
        node_failures: Optional[List[str]] = None,
        retry_count: int = 0,
        duration_ms: Optional[float] = None,
    ) -> bool:
        """
        Send notification when a pipeline fails.

        Args:
            repo_name: Repository full name (e.g., "owner/repo")
            build_id: Build sample ID
            error: Error message
            pipeline_run_id: Pipeline run ID for tracking
            node_failures: List of failed node names
            retry_count: Total retry attempts
            duration_ms: Execution duration in milliseconds

        Returns:
            True if notification was sent successfully.
        """
        if not self.enabled or not self.is_configured:
            logger.debug("Notifications disabled or not configured")
            return False

        success = False

        # Send to Slack
        if self.slack_webhook_url:
            payload = self._build_slack_failure_message(
                repo_name=repo_name,
                build_id=build_id,
                error=error,
                pipeline_run_id=pipeline_run_id,
                node_failures=node_failures,
                retry_count=retry_count,
                duration_ms=duration_ms,
            )
            success = await self._send_slack_message(payload)

        # Send to custom webhook
        if self.custom_webhook_url:
            custom_payload = {
                "type": NotificationType.PIPELINE_FAILURE,
                "repo_name": repo_name,
                "build_id": build_id,
                "error": error,
                "pipeline_run_id": pipeline_run_id,
                "node_failures": node_failures or [],
                "retry_count": retry_count,
                "duration_ms": duration_ms,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            webhook_success = await self._send_webhook(self.custom_webhook_url, custom_payload)
            success = success or webhook_success

        return success

    async def notify_pipeline_success(
        self,
        repo_name: str,
        feature_count: int,
        duration_ms: float,
        pipeline_run_id: str,
    ) -> bool:
        """
        Send notification when a pipeline completes successfully.

        Note: Success notifications are typically verbose; consider enabling
        only for specific repos or in debug mode.

        Args:
            repo_name: Repository full name
            feature_count: Number of features extracted
            duration_ms: Execution duration
            pipeline_run_id: Pipeline run ID

        Returns:
            True if notification was sent successfully.
        """
        if not self.enabled or not self.is_configured:
            return False

        success = False

        if self.slack_webhook_url:
            payload = self._build_slack_success_message(
                repo_name=repo_name,
                feature_count=feature_count,
                duration_ms=duration_ms,
                pipeline_run_id=pipeline_run_id,
            )
            success = await self._send_slack_message(payload)

        return success

    async def notify_rate_limit_warning(
        self,
        remaining: int,
        reset_at: datetime,
        token_label: Optional[str] = None,
    ) -> bool:
        """
        Send warning when GitHub API rate limit is running low.

        Args:
            remaining: Remaining API calls
            reset_at: When the rate limit resets
            token_label: Optional label for the token

        Returns:
            True if notification was sent successfully.
        """
        if not self.enabled or not self.slack_webhook_url:
            return False

        token_info = f" (token: {token_label})" if token_label else ""
        reset_str = reset_at.strftime("%H:%M UTC")

        payload = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⚠️ *GitHub Rate Limit Warning*{token_info}\n"
                                f"Only {remaining} requests remaining. Resets at {reset_str}."
                    }
                }
            ]
        }

        return await self._send_slack_message(payload)


# Singleton instance for convenience
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """
    Get the global notification service instance.

    Creates a new instance if one doesn't exist.
    """
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
