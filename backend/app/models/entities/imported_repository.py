"""Repository entity - represents a tracked repository"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, Field


class ImportedRepository(BaseModel):
    id: Optional[ObjectId] = Field(None, alias="_id")
    user_id: Optional[ObjectId] = None
    provider: str
    full_name: str
    default_branch: Optional[str] = None
    is_private: bool = False
    main_lang: Optional[str] = None
    github_repo_id: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    last_scanned_at: Optional[datetime] = None
    installation_id: Optional[str] = None
    ci_provider: Literal["github_actions", "travis_ci"] = "github_actions"
    sync_status: Literal["healthy", "error", "disabled"] = "healthy"
    ci_token_status: Literal["valid", "missing"] = "valid"
    test_frameworks: List[Literal["PYTEST", "UNITTEST", "RSPEC", "MINITEST"]] = Field(
        default_factory=list
    )
    source_languages: List[Literal["PYTHON", "RUBY"]] = Field(default_factory=list)
    total_builds_imported: int = 0
    last_sync_error: Optional[str] = None
    notes: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


# class ImportedRepository(BaseModel):
#     id: Optional[ObjectId] = Field(None, alias="_id")

#     # Ownership / provider
#     user_id: Optional[ObjectId] = None
#     provider: Literal["github", "gitlab", "bitbucket"] = "github"

#     # Repo identity / lookup (nên giữ ở top-level)
#     full_name: str  # "owner/repo"
#     github_repo_id: Optional[int] = None  # id numeric, dùng nhiều ⇒ giữ lại

#     # Repo config do user chọn trong UI
#     test_frameworks: List[Literal["PYTEST", "UNITTEST", "RSPEC", "MINITEST"]] = Field(
#         default_factory=list
#     )
#     source_languages: List[Literal["PYTHON", "RUBY"]] = Field(default_factory=list)

#     # CI / Integration
#     ci_provider: Literal["github_actions", "travis_ci"] = "github_actions"
#     installation_id: Optional[str] = None

#     # Import / sync lifecycle
#     import_status: Literal["not_imported", "importing", "imported", "failed"] = (
#         "not_imported"
#     )
#     total_builds_imported: int = 0
#     last_build_scan_at: Optional[datetime] = None
#     last_sync_error: Optional[str] = None

#     # Tất cả thông tin “thuộc về GitHub” cho vào metadata
#     metadata: Dict[str, Any] = Field(default_factory=dict)

#     created_at: datetime
#     updated_at: Optional[datetime] = None

#     class Config:
#         populate_by_name = True
#         arbitrary_types_allowed = True
