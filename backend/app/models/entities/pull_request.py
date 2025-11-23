from datetime import datetime
from typing import Optional

from pydantic import Field

from .base import BaseEntity, PyObjectId


class PullRequest(BaseEntity):
    repo_id: PyObjectId
    number: int
    title: str | None = None
    user_login: str | None = None  # The user who opened the PR
    state: str  # open, closed
    merged: bool = False
    merged_at: datetime | None = None
    merged_by_login: str | None = None  # The user who merged the PR
    created_at: datetime
    updated_at: datetime

    # Extra fields if needed later
    head_sha: str | None = None
    base_sha: str | None = None
