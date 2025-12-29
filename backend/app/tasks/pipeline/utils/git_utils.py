"""
Git Utilities using subprocess.

Provides git operations using subprocess commands for reliable behavior
across different repository configurations including submodules and complex histories.
"""

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)


def run_git(
    repo_path: Path,
    args: List[str],
    timeout: int = 60,
) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + args,
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, ["git"] + args, result.stdout, result.stderr
        )
    return result.stdout.strip()


def get_commit_info(repo_path: Path, sha: str) -> Dict[str, Any]:
    """
    Get commit info using subprocess.

    Returns dict with: hexsha, parents (list of parent shas), committed_date
    """
    try:
        # Format: sha|parent1 parent2|timestamp
        output = run_git(
            repo_path,
            ["log", "-1", "--format=%H|%P|%ct", sha],
        )
        parts = output.split("|")
        if len(parts) >= 3:
            parents = parts[1].split() if parts[1] else []
            return {
                "hexsha": parts[0],
                "parents": parents,
                "committed_date": int(parts[2]) if parts[2] else 0,
            }
    except Exception as e:
        logger.warning(f"Failed to get commit info for {sha}: {e}")

    return {"hexsha": sha, "parents": [], "committed_date": 0}


def get_commit_parents(repo_path: Path, sha: str) -> List[str]:
    """Get parent commit SHAs using subprocess."""
    try:
        output = run_git(repo_path, ["log", "-1", "--format=%P", sha])
        return output.split() if output else []
    except Exception as e:
        logger.warning(f"Failed to get parents for {sha}: {e}")
        return []


def get_diff_files(repo_path: Path, sha1: str, sha2: str) -> List[Dict[str, str]]:
    """
    Get list of files changed between two commits using subprocess.

    Returns list of dicts with: a_path, b_path (old/new paths)
    """
    try:
        # --name-status: shows status (A/D/M/R) and file paths
        output = run_git(
            repo_path,
            ["diff-tree", "-r", "--name-status", "--no-commit-id", sha1, sha2],
        )

        files = []
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                status = parts[0][0]  # First char: A, D, M, R, C
                if status == "R" or status == "C":
                    # Rename/Copy: status\told_path\tnew_path
                    a_path = parts[1] if len(parts) > 1 else None
                    b_path = parts[2] if len(parts) > 2 else parts[1]
                elif status == "D":
                    # Delete: only old path
                    a_path = parts[1]
                    b_path = None
                elif status == "A":
                    # Add: only new path
                    a_path = None
                    b_path = parts[1]
                else:
                    # Modify: same path
                    a_path = parts[1]
                    b_path = parts[1]

                files.append({"a_path": a_path, "b_path": b_path})

        return files
    except Exception as e:
        logger.warning(f"Failed to get diff files between {sha1} and {sha2}: {e}")
        return []


def iter_commit_history(
    repo_path: Path,
    start_sha: str,
    max_count: int = 1000,
) -> Generator[Dict[str, Any], None, None]:
    """
    Iterate through commit history using subprocess.

    Yields dicts with: hexsha, parents (list)
    """
    try:
        # Format: sha|parent1 parent2
        output = run_git(
            repo_path,
            ["log", f"--max-count={max_count}", "--format=%H|%P", start_sha],
        )

        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split("|")
            if parts:
                hexsha = parts[0]
                parents = parts[1].split() if len(parts) > 1 and parts[1] else []
                yield {"hexsha": hexsha, "parents": parents}
    except Exception as e:
        logger.warning(f"Failed to iterate commits from {start_sha}: {e}")
        return


def get_author_email(repo_path: Path, sha: str) -> Optional[str]:
    """Get author email for a commit."""
    try:
        return run_git(repo_path, ["log", "-1", "--format=%ae", sha])
    except Exception:
        return None


def get_committer_email(repo_path: Path, sha: str) -> Optional[str]:
    """Get committer email for a commit."""
    try:
        return run_git(repo_path, ["log", "-1", "--format=%ce", sha])
    except Exception:
        return None


def get_committed_date(repo_path: Path, sha: str) -> Optional[int]:
    """Get committed date (unix timestamp) for a commit."""
    try:
        ts = run_git(repo_path, ["log", "-1", "--format=%ct", sha])
        return int(ts) if ts else None
    except Exception:
        return None


def get_author_name(repo_path: Path, sha: str) -> Optional[str]:
    """Get author name for a commit."""
    try:
        return run_git(repo_path, ["log", "-1", "--format=%an", sha])
    except Exception:
        return None


def get_committer_name(repo_path: Path, sha: str) -> Optional[str]:
    """Get committer name for a commit."""
    try:
        return run_git(repo_path, ["log", "-1", "--format=%cn", sha])
    except Exception:
        return None


def git_log_files(
    repo_path: Path,
    sha: str,
    since_iso: str,
    file_paths: List[str],
    chunk_size: int = 50,
) -> set:
    """
    Get commit SHAs that touched the given files since a date.

    Args:
        repo_path: Path to the git repository
        sha: Starting commit SHA
        since_iso: ISO format date string for --since
        file_paths: List of file paths to check
        chunk_size: Process files in chunks to avoid arg limits

    Returns:
        Set of commit SHAs that modified the given files
    """
    all_shas: set = set()

    for i in range(0, len(file_paths), chunk_size):
        chunk = file_paths[i : i + chunk_size]
        try:
            output = run_git(
                repo_path,
                ["log", sha, "--since", since_iso, "--format=%H", "--"] + chunk,
            )
            if output:
                all_shas.update(output.splitlines())
        except Exception:
            continue

    return all_shas


def get_author_first_commit_ts(repo_path: Path, author: str) -> Optional[int]:
    """
    Get the timestamp of author's first commit in the repository.

    Uses git log --all --author --reverse to find the oldest commit.
    Matches risk_features_enrichment.py::check_is_new_contributor logic.

    Returns:
        Unix timestamp of first commit, or None if not found
    """
    try:
        # Use Popen to read only first line (more efficient for large repos)
        proc = subprocess.Popen(
            ["git", "log", "--all", "--author", author, "--reverse", "--format=%ct"],
            cwd=str(repo_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if proc.stdout:
            first_line = proc.stdout.readline().strip()
            proc.terminate()
            if first_line:
                return int(first_line)
    except Exception as e:
        logger.warning(f"Failed to get first commit for author {author}: {e}")
    return None


def get_files_in_commit(repo_path: Path, sha: str) -> List[str]:
    """Get list of files changed in a commit."""
    try:
        output = run_git(repo_path, ["diff", "--name-only", f"{sha}^", sha])
        return [f.strip() for f in output.splitlines() if f.strip()]
    except Exception:
        return []


def get_author_file_ownership(
    repo_path: Path,
    author: str,
    file_paths: List[str],
    max_files: int = 20,
) -> float:
    """
    Calculate author's ownership of files (% of commits on files by author).

    Matches github_enrichment.py::author_ownership logic.

    Args:
        repo_path: Path to repository
        author: Author name to check
        file_paths: Files to analyze
        max_files: Maximum files to check (for performance)

    Returns:
        Ownership ratio (0.0 - 1.0)
    """
    total_commits = 0
    author_commits = 0

    for filepath in file_paths[:max_files]:
        try:
            # Total commits on this file
            all_log = run_git(
                repo_path,
                ["log", "--oneline", "--follow", "--", filepath],
            )
            file_total = len([line for line in all_log.splitlines() if line])
            total_commits += file_total

            # Author's commits on this file
            author_log = run_git(
                repo_path,
                ["log", "--oneline", "--author", author, "--follow", "--", filepath],
            )
            file_author = len([line for line in author_log.splitlines() if line])
            author_commits += file_author
        except Exception:
            continue

    if total_commits > 0:
        return round(author_commits / total_commits, 4)
    return 0.0


def get_commit_message(repo_path: Path, sha: str) -> Optional[str]:
    """Get commit message body."""
    try:
        # %B: raw body (unwrapped subject and body)
        return run_git(repo_path, ["log", "-1", "--format=%B", sha])
    except Exception:
        return None


def check_is_merge_commit(repo_path: Path, sha: str) -> bool:
    """Check if commit is a merge commit (has >1 parent)."""
    try:
        parents = get_commit_parents(repo_path, sha)
        return len(parents) > 1
    except Exception:
        return False


def get_author_total_commits(repo_path: Path, author: str) -> int:
    """Count total commits by author in the repository."""
    try:
        output = run_git(
            repo_path,
            ["rev-list", "--count", "--author", author, "--all"],
        )
        return int(output) if output else 0
    except Exception:
        return 0


def get_author_last_commit_ts(repo_path: Path, author: str, before_ts: int) -> Optional[int]:
    """
    Get timestamp of author's last commit before a given timestamp.

    Args:
        repo_path: Path to repository
        author: Author email/name
        before_ts: Timestamp to look before

    Returns:
        Timestamp of previous commit or None
    """
    try:
        # Get 1 commit by author, before the given date
        # --before accepts absolute timestamp
        output = run_git(
            repo_path,
            [
                "log",
                "-1",
                "--author",
                author,
                f"--before={before_ts}",
                "--format=%ct",
                "--date=raw",
            ],
        )
        return int(output) if output else None
    except Exception:
        return None


def get_file_change_stats(repo_path: Path, sha: str) -> List[int]:
    """
    Get lines changed per file for entropy calculation.
    Returns list of integers (added + deleted lines per file).
    """
    try:
        # --numstat returns: added\tdeleted\tfilepath
        output = run_git(
            repo_path,
            ["show", "--numstat", "--format=", sha],
        )
        changes = []
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                try:
                    added = int(parts[0]) if parts[0] != "-" else 0
                    deleted = int(parts[1]) if parts[1] != "-" else 0
                    changes.append(added + deleted)
                except ValueError:
                    continue  # Skip binary files or parse errors
        return changes
    except Exception as e:
        logger.warning(f"Failed to get file change stats for {sha}: {e}")
        return []


def get_file_modification_count(repo_path: Path, files: List[str], since_iso: str) -> float:
    """
    Calculate average modification count for a list of files since a date.

    Args:
        repo_path: Path to repository
        files: List of file paths to check
        since_iso: ISO date string for --since

    Returns:
        Average number of commits per file
    """
    if not files:
        return 0.0

    try:
        if len(files) > 20:
            check_files = files[:20]
        else:
            check_files = files

        count_sum = 0
        valid_files = 0
        for f in check_files:
            try:
                c = run_git(
                    repo_path, ["rev-list", "--count", "--since", since_iso, "HEAD", "--", f]
                )
                if c:
                    count_sum += int(c)
                    valid_files += 1
            except Exception:
                continue

        return round(count_sum / valid_files, 2) if valid_files > 0 else 0.0

    except Exception as e:
        logger.warning(f"Failed to calc file mod count: {e}")
        return 0.0
