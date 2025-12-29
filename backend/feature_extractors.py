"""
Feature Extractors for GitHub/Git Data
========================================
Extract features from GitHub API and local Git repos based on paper requirements.

Features to extract (from Dataset Requirements):
1. Source Code Stream (X_code)
2. Test & Coverage Stream (X_test)  
3. Team Activity Stream (X_team)
4. Monitoring Stream (X_monitor)
"""

import os
import re
import math
import subprocess
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from collections import Counter
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def run_git_command(cmd: List[str], repo_dir: str) -> Optional[str]:
    """Run a git command and return output."""
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=30
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


def parse_datetime(dt_str: str) -> Optional[datetime]:
    """Parse datetime string to datetime object."""
    if not dt_str or pd.isna(dt_str):
        return None
    try:
        dt = pd.to_datetime(dt_str)
        if dt.tz is None:
            dt = dt.tz_localize('UTC')
        return dt
    except Exception:
        return None


def calculate_shannon_entropy(values: List[int]) -> float:
    """Calculate Shannon entropy of a distribution."""
    total = sum(values)
    if total == 0:
        return 0.0
    
    entropy = 0.0
    for v in values:
        if v > 0:
            p = v / total
            entropy -= p * math.log2(p)
    
    return entropy


# =============================================================================
# 1. SOURCE CODE STREAM (X_code)
# =============================================================================

def extract_change_entropy(git_all_built_commits: List[str], repo_dir: str) -> float:
    """
    Calculate change entropy based on distribution of changes across files.
    Higher entropy = changes spread across many files = higher risk.
    """
    file_changes = Counter()
    
    for sha in git_all_built_commits:
        output = run_git_command(
            ["git", "show", "-m", "--name-only", "--format=", sha],
            repo_dir
        )
        if output:
            for line in output.splitlines():
                if line.strip():
                    file_changes[line.strip()] += 1
    
    if not file_changes:
        return 0.0
    
    return calculate_shannon_entropy(list(file_changes.values()))


def extract_file_change_frequency(
    git_all_built_commits: List[str],
    repo_dir: str,
    commit_date: Optional[datetime] = None
) -> float:
    """
    Calculate average number of times each touched file was modified 
    in the last 3 months.
    """
    touched_files: Set[str] = set()
    
    # Get touched files
    for sha in git_all_built_commits:
        output = run_git_command(
            ["git", "show", "-m", "--name-only", "--format=", sha],
            repo_dir
        )
        if output:
            for line in output.splitlines():
                if line.strip():
                    touched_files.add(line.strip())
    
    if not touched_files:
        return 0.0
    
    # Count commits on each file in last 3 months
    total_commits = 0
    since_date = None
    if commit_date:
        since_date = commit_date - timedelta(days=90)
    
    for filename in touched_files:
        if since_date and commit_date:
            cmd = [
                "git", "log", 
                f"--since={since_date.isoformat()}",
                f"--until={commit_date.isoformat()}",
                "--oneline", "--", filename
            ]
        else:
            cmd = ["git", "log", "-n", "50", "--oneline", "--", filename]
        
        output = run_git_command(cmd, repo_dir)
        if output:
            total_commits += len(output.splitlines())
    
    return total_commits / len(touched_files) if touched_files else 0.0


# =============================================================================
# 2. TEST & COVERAGE STREAM (X_test)
# =============================================================================

def extract_prev_build_features(
    df: pd.DataFrame,
    current_idx: int,
    project_builds: pd.DataFrame
) -> Dict[str, Any]:
    """
    Extract features related to previous builds.
    - prev_tr_status
    - is_prev_failed
    - prev_fail_streak
    - fail_rate_last_10
    """
    features = {
        'prev_tr_status': None,
        'is_prev_failed': False,
        'prev_fail_streak': 0,
        'fail_rate_last_10': 0.0,
        'avg_src_churn_last_5': 0.0,
    }
    
    # Get builds before current
    prev_builds = project_builds.iloc[:current_idx]
    
    if len(prev_builds) == 0:
        return features
    
    # Previous build status
    last_build = prev_builds.iloc[-1]
    features['prev_tr_status'] = last_build.get('tr_status')
    features['is_prev_failed'] = last_build.get('tr_status') == 'failed'
    
    # Fail streak
    streak = 0
    for i in range(len(prev_builds) - 1, -1, -1):
        if prev_builds.iloc[i].get('tr_status') == 'failed':
            streak += 1
        else:
            break
    features['prev_fail_streak'] = streak
    
    # Fail rate last 10
    last_10 = prev_builds.tail(10)
    if len(last_10) > 0:
        fail_count = (last_10['tr_status'] == 'failed').sum()
        features['fail_rate_last_10'] = fail_count / len(last_10)
    
    # Average src churn last 5
    last_5 = prev_builds.tail(5)
    if len(last_5) > 0 and 'git_diff_src_churn' in last_5.columns:
        features['avg_src_churn_last_5'] = last_5['git_diff_src_churn'].mean()
    
    return features


# NOTE: src_test_churn_ratio removed because git_diff_test_churn = 0 for all records in dataset


# =============================================================================
# 3. TEAM ACTIVITY STREAM (X_team)
# =============================================================================

def _extract_pr_features_rest(client, pr_number: int, features: Dict) -> Dict[str, Any]:
    """Fallback extraction using REST API when GraphQL fails."""
    try:
        # Get PR details
        pr = client.get_pull_request(pr_number)
        if not pr:
            return features
            
        # Reviewers
        reviewers = pr.get("requested_reviewers", [])
        features['gh_num_reviewers'] = len(reviewers)
        
        # Linked issues
        features['gh_linked_issues_count'] = _parse_linked_issues(pr.get("body") or "")
        
        # Labels
        features['gh_has_bug_label'] = any(
            "bug" in lbl["name"].lower() or "fix" in lbl["name"].lower()
            for lbl in pr.get("labels", [])
        )
        
        # Reviews
        reviews = client.get_pull_reviews(pr_number)
        if reviews:
            # Approvals
            approvals = [r for r in reviews if r.get("state") == "APPROVED"]
            features['gh_num_approvals'] = len(approvals)
            
            # Sentiment
            total_sentiment = 0
            count = 0
            for r in reviews:
                body = r.get("body", "")
                if body:
                    # Use internal sentiment calculator
                    total_sentiment += _calculate_sentiment(body)
                    count += 1
            features['gh_review_sentiment'] = total_sentiment / count if count > 0 else 0.0
            
            # Time to first review
            created_at = parse_datetime(pr.get("created_at"))
            valid_reviews = [r for r in reviews if r.get("submitted_at")]
            if created_at and valid_reviews:
                valid_reviews.sort(key=lambda x: x["submitted_at"])
                first_review = parse_datetime(valid_reviews[0]["submitted_at"])
                if first_review:
                    diff = (first_review - created_at).total_seconds() / 3600
                    features['gh_time_to_first_review'] = max(0, diff)
                    
    except Exception as e:
        logger.warning(f"REST fallback failed for PR #{pr_number}: {e}")
        
    return features

def extract_pr_features(client, pr_number: int, row: Dict) -> Dict[str, Any]:
    """
    Extract PR-related features using GraphQL.
    - gh_num_reviewers
    - gh_num_approvals
    - gh_review_sentiment
    - gh_time_to_first_review
    - gh_linked_issues_count
    - gh_has_bug_label
    """
    features = {
        'gh_num_reviewers': 0,
        'gh_num_approvals': 0,
        'gh_review_sentiment': 0.0,
        'gh_time_to_first_review': None,
        'gh_linked_issues_count': 0,
        'gh_has_bug_label': False,
    }
    
    query = """
    query ($owner: String!, $repo: String!, $pr_number: Int!) {
        repository(owner: $owner, name: $repo) {
            pullRequest(number: $pr_number) {
                title
                body
                createdAt
                labels(first: 100) { nodes { name } }
                reviewRequests(first: 100) { nodes { requestedReviewer { ... on User { login } } } }
                reviews(first: 100) { nodes { state body submittedAt author { login } } }
            }
        }
    }
    """
    
    try:
        data = client.graphql(query, {
            "owner": client.owner,
            "repo": client.repo,
            "pr_number": int(pr_number)
        })
        
        pr_data = data.get("data", {}).get("repository", {}).get("pullRequest")
        if not pr_data:
            logger.warning(f"GraphQL failed/empty for PR #{pr_number}, using REST fallback")
            return _extract_pr_features_rest(client, pr_number, features)
        
        # Reviewers
        reviewers = pr_data.get("reviewRequests", {}).get("nodes", [])
        features['gh_num_reviewers'] = len(reviewers)
        
        # Linked issues
        body = pr_data.get("body", "") or ""
        features['gh_linked_issues_count'] = _parse_linked_issues(body)
        
        # Bug label
        labels = pr_data.get("labels", {}).get("nodes", [])
        features['gh_has_bug_label'] = any(
            "bug" in lbl["name"].lower() or "fix" in lbl["name"].lower()
            for lbl in labels
        )
        
        # Reviews
        reviews = pr_data.get("reviews", {}).get("nodes", [])
        approvals = [r for r in reviews if r.get("state") == "APPROVED"]
        features['gh_num_approvals'] = len(approvals)
        
        # Sentiment
        total_sentiment = 0
        review_count = 0
        for r in reviews:
            r_body = r.get("body", "")
            if r_body:
                total_sentiment += _calculate_sentiment(r_body)
                review_count += 1
        
        features['gh_review_sentiment'] = (
            total_sentiment / review_count if review_count > 0 else 0.0
        )
        
        # Time to first review
        pr_created_at = parse_datetime(row.get("gh_pr_created_at"))
        if pr_created_at and reviews:
            valid_reviews = [r for r in reviews if r.get("submittedAt")]
            if valid_reviews:
                valid_reviews.sort(key=lambda x: x["submittedAt"])
                first_review_at = parse_datetime(valid_reviews[0]["submittedAt"])
                if first_review_at:
                    diff_hours = (first_review_at - pr_created_at).total_seconds() / 3600
                    features['gh_time_to_first_review'] = max(0, diff_hours)
        
    except Exception as e:
        logger.warning(f"Failed to extract PR features for #{pr_number}: {e}")
    
    return features


def _parse_linked_issues(body: str) -> int:
    """Parse linked issues from PR body."""
    if not body:
        return 0
    keywords = ["close", "closes", "closed", "fix", "fixes", "fixed", 
                "resolve", "resolves", "resolved"]
    pattern = r"(" + "|".join(keywords) + r")\s+#(\d+)"
    return len(re.findall(pattern, body, re.IGNORECASE))


def _calculate_sentiment(text: str) -> float:
    """Simple sentiment scoring."""
    if not text:
        return 0.0
    
    text = text.lower()
    positive = ["good", "great", "awesome", "excellent", "lgtm", 
                "looks good", "perfect", "nice", "thank", "approved"]
    negative = ["bad", "wrong", "error", "bug", "fix", "issue", 
                "problem", "change", "concern", "reject"]
    
    score = 0
    for w in positive:
        if w in text:
            score += 1
    for w in negative:
        if w in text:
            score -= 1
    
    return score


def extract_author_ownership(
    git_all_built_commits: List[str],
    repo_dir: str,
    commit_date: Optional[datetime] = None
) -> float:
    """
    Calculate author ownership: ratio of commits by build authors on touched files.
    """
    touched_files: Set[str] = set()
    build_authors: Set[str] = set()
    
    # Get files and authors from build commits
    for sha in git_all_built_commits:
        output = run_git_command(
            ["git", "show", "-m", "--name-only", "--format=%an", sha],
            repo_dir
        )
        if output:
            lines = output.splitlines()
            if lines:
                build_authors.add(lines[0])
                for f in lines[1:]:
                    if f.strip():
                        touched_files.add(f.strip())
    
    if not touched_files or not build_authors:
        return 0.0
    
    # Count ownership
    total_commits = 0
    owned_commits = 0
    
    since_date = None
    if commit_date:
        since_date = commit_date - timedelta(days=90)
    
    for filename in touched_files:
        if since_date and commit_date:
            cmd = [
                "git", "log",
                f"--since={since_date.isoformat()}",
                f"--until={commit_date.isoformat()}",
                "--format=%an", "--", filename
            ]
        else:
            cmd = ["git", "log", "-n", "50", "--format=%an", "--", filename]
        
        output = run_git_command(cmd, repo_dir)
        if output:
            for author in output.splitlines():
                total_commits += 1
                if author in build_authors:
                    owned_commits += 1
    
    return owned_commits / total_commits if total_commits > 0 else 0.0


def check_is_new_contributor(
    git_all_built_commits: List[str],
    repo_dir: str,
    commit_date: Optional[datetime] = None
) -> bool:
    """
    Check if any author is a new contributor (< 90 days).
    Uses timezone-aware datetime comparison.
    """
    if not commit_date:
        return False
    
    # Ensure commit_date is timezone-naive for comparison
    if hasattr(commit_date, 'tzinfo') and commit_date.tzinfo is not None:
        commit_date_naive = commit_date.replace(tzinfo=None)
    else:
        commit_date_naive = commit_date
    
    for sha in git_all_built_commits:
        output = run_git_command(
            ["git", "show", "--format=%ae", "-s", sha],
            repo_dir
        )
        if not output:
            continue
        
        author_email = output.strip()
        
        # Get first commit by this author
        first_commit = run_git_command(
            ["git", "log", "--author=" + author_email, 
             "--reverse", "--format=%ct", "-n", "1"],
            repo_dir
        )
        
        if first_commit:
            try:
                first_commit_ts = int(first_commit.strip())
                first_commit_date = datetime.utcfromtimestamp(first_commit_ts)
                
                # Both are now naive UTC datetimes
                days_since_first = (commit_date_naive - first_commit_date).days
                if 0 <= days_since_first < 90:
                    return True
            except (ValueError, TypeError, OSError):
                # OSError can happen with invalid timestamps
                pass
    
    return False


# =============================================================================
# 4. MONITORING STREAM (X_monitor)
# =============================================================================

def extract_build_time_features(build_started_at: str) -> Dict[str, float]:
    """
    Extract time-based risk features.
    - build_time_sin, build_time_cos (cyclic encoding)
    - build_hour_risk_score
    """
    features = {
        'build_time_sin': 0.0,
        'build_time_cos': 1.0,
        'build_hour_risk_score': 0.1,
    }
    
    dt = parse_datetime(build_started_at)
    if not dt:
        return features
    
    hour = dt.hour
    day_of_week = dt.weekday()  # 0=Monday, 6=Sunday
    
    # Cyclic encoding
    features['build_time_sin'] = math.sin(2 * math.pi * hour / 24)
    features['build_time_cos'] = math.cos(2 * math.pi * hour / 24)
    
    # Risk score based on time
    # 1.0: Night (0-5h) - Fatigue
    # 0.9: Friday afternoon (after 16h)
    # 0.8: Weekend
    # 0.1: Normal hours
    
    if 0 <= hour < 5:
        risk = 1.0
    elif day_of_week == 4 and hour >= 16:  # Friday afternoon
        risk = 0.9
    elif day_of_week >= 5:  # Weekend
        risk = 0.8
    else:
        risk = 0.1
    
    features['build_hour_risk_score'] = risk
    
    return features


def calculate_time_since_prev_build(
    current_build_started: str,
    prev_build_started: str
) -> Optional[float]:
    """Calculate hours since previous build."""
    current_dt = parse_datetime(current_build_started)
    prev_dt = parse_datetime(prev_build_started)
    
    if not current_dt or not prev_dt:
        return None
    
    diff_hours = (current_dt - prev_dt).total_seconds() / 3600
    return max(0, diff_hours)


def calculate_churn_ratio_vs_avg(current_churn: float, avg_churn: float) -> float:
    """Compare current churn vs average of last 5 builds."""
    return current_churn / (avg_churn + 1)


# =============================================================================
# 5. ADDITIONAL FEATURES (NEW)
# =============================================================================

def extract_commit_message_length(git_all_built_commits: List[str], repo_dir: str) -> float:
    """
    Calculate average commit message length.
    Short messages often indicate rushed commits.
    """
    total_length = 0
    count = 0
    
    for sha in git_all_built_commits:
        output = run_git_command(
            ["git", "log", "-1", "--format=%s", sha],
            repo_dir
        )
        if output:
            total_length += len(output)
            count += 1
    
    return total_length / count if count > 0 else 0.0


def check_has_issue_reference(git_all_built_commits: List[str], repo_dir: str) -> bool:
    """
    Check if any commit references an issue (#123, fixes #123, etc).
    Commits with issue references are usually better tracked.
    """
    issue_pattern = re.compile(r'#\d+')
    
    for sha in git_all_built_commits:
        output = run_git_command(
            ["git", "log", "-1", "--format=%s%n%b", sha],
            repo_dir
        )
        if output and issue_pattern.search(output):
            return True
    
    return False


def calculate_files_modified_ratio(row: Dict) -> float:
    """
    Calculate ratio of modified files to total changed files.
    High modification ratio = more complex changes.
    """
    added = row.get('gh_diff_files_added', 0) or 0
    deleted = row.get('gh_diff_files_deleted', 0) or 0
    modified = row.get('gh_diff_files_modified', 0) or 0
    
    total = added + deleted + modified
    if total == 0:
        return 0.0
    
    return modified / total


def check_is_merge_commit(git_trigger_commit: str, repo_dir: str) -> bool:
    """
    Check if the trigger commit is a merge commit.
    Merge commits usually have lower direct risk.
    """
    if not git_trigger_commit or not repo_dir:
        return False
    
    output = run_git_command(
        ["git", "cat-file", "-p", git_trigger_commit],
        repo_dir
    )
    
    if output:
        # Merge commits have more than one parent
        parent_count = output.count("parent ")
        return parent_count > 1
    
    return False


def extract_days_since_last_author_commit(
    git_all_built_commits: List[str],
    repo_dir: str,
    commit_date: Optional[datetime] = None
) -> Optional[float]:
    """
    Days since author's last commit before this one.
    Long gaps may indicate unfamiliarity with current codebase.
    """
    if not git_all_built_commits or not repo_dir or not commit_date:
        return None
    
    # Get author email from first commit
    sha = git_all_built_commits[0]
    output = run_git_command(
        ["git", "show", "--format=%ae", "-s", sha],
        repo_dir
    )
    
    if not output:
        return None
    
    author_email = output.strip()
    
    # Get author's previous commit before this one
    prev_commit = run_git_command(
        ["git", "log", "--author=" + author_email, 
         "-2", "--format=%ct", sha],
        repo_dir
    )
    
    if prev_commit:
        lines = prev_commit.strip().split('\n')
        if len(lines) >= 2:
            try:
                prev_ts = int(lines[1])
                prev_date = datetime.utcfromtimestamp(prev_ts)
                
                if hasattr(commit_date, 'tzinfo') and commit_date.tzinfo is not None:
                    commit_date_naive = commit_date.replace(tzinfo=None)
                else:
                    commit_date_naive = commit_date
                
                days = (commit_date_naive - prev_date).days
                return max(0, days)
            except (ValueError, TypeError, OSError):
                pass
    
    return None


def extract_pr_extra_features(client, pr_number: int, row: Dict) -> Dict[str, Any]:
    """
    Extract additional PR features:
    - pr_age_hours: Time from PR creation to build
    - pr_num_commits: Number of commits in PR
    """
    features = {
        'pr_age_hours': None,
        'pr_num_commits': 0,
    }
    
    try:
        # Get PR creation time
        pr_created_at = parse_datetime(row.get("gh_pr_created_at"))
        build_started_at = parse_datetime(row.get("gh_build_started_at"))
        
        if pr_created_at and build_started_at:
            age_hours = (build_started_at - pr_created_at).total_seconds() / 3600
            features['pr_age_hours'] = max(0, age_hours)
        
        # Get number of commits in PR via API
        commits = client.get(
            f"/repos/{client.owner}/{client.repo}/pulls/{int(pr_number)}/commits",
            paginate=True
        )
        if isinstance(commits, list):
            features['pr_num_commits'] = len(commits)
            
    except Exception as e:
        logger.debug(f"Failed to get PR extra features: {e}")
    
    return features


def extract_author_total_commits(
    git_all_built_commits: List[str],
    repo_dir: str
) -> int:
    """
    Get total number of commits by the build author in the entire repo.
    More commits = more experienced contributor.
    """
    if not git_all_built_commits or not repo_dir:
        return 0
    
    # Get author email from first commit
    sha = git_all_built_commits[0]
    output = run_git_command(
        ["git", "show", "--format=%ae", "-s", sha],
        repo_dir
    )
    
    if not output:
        return 0
    
    author_email = output.strip()
    
    # Count all commits by this author
    count_output = run_git_command(
        ["git", "rev-list", "--count", "--author=" + author_email, "HEAD"],
        repo_dir
    )
    
    if count_output:
        try:
            return int(count_output.strip())
        except ValueError:
            pass
    
    return 0
