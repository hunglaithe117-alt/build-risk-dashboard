"""
RawRepository Entity - Immutable GitHub repository data.

This entity stores raw repository information fetched from GitHub.
It serves as a single source of truth for repository metadata across all flows.

Key design principles:
- Immutable: Once fetched, data should not be modified (only updated on re-fetch)
- Shared: Both model training and dataset enrichment flows reference this table
- Minimal: Contains only essential GitHub metadata, no user-specific configs
"""

from typing import Any, Dict, List, Optional

from pydantic import Field

from app.entities.base import BaseEntity


class RawRepository(BaseEntity):
    """
    Raw repository data from GitHub.

    This is the single source of truth for repository information.
    Multiple flows can reference the same repository via raw_repo_id.
    """

    class Config:
        collection = "raw_repositories"

    # Core identifiers
    full_name: str = Field(
        ...,
        description="Repository full name (owner/repo). Unique across GitHub.",
        example="facebook/react",
    )
    github_repo_id: Optional[int] = Field(
        None,
        description="GitHub's internal repository ID. More stable than full_name.",
    )

    # Repository metadata
    default_branch: str = Field(
        default="main",
        description="Default branch name (main, master, develop, etc.)",
    )
    is_private: bool = Field(
        default=False,
        description="Whether the repository is private",
    )

    # Language information
    main_lang: Optional[str] = Field(
        None,
        description="Primary programming language (lowercase)",
        example="python",
    )
    source_languages: List[str] = Field(
        default_factory=list,
        description="All detected programming languages (lowercase, sorted by usage)",
        example=["python", "javascript", "shell"],
    )
    language_stats: Dict[str, int] = Field(
        default_factory=dict,
        description="Language distribution in bytes from GitHub API",
        example={"Python": 45620, "JavaScript": 12340, "Shell": 890},
    )

    # Full GitHub metadata (for future use)
    github_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Complete GitHub API response for this repository",
    )
