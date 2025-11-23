import shutil
import tempfile
import unittest
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

# Mock dependencies
sys.modules["celery"] = MagicMock()
sys.modules["app.celery_app"] = MagicMock()
sys.modules["app.services.github.github_app"] = MagicMock()

from app.services.extracts.git_feature_extractor import GitFeatureExtractor


class TestGitTeamStats(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.extractor = GitFeatureExtractor(db=MagicMock())
        self._init_repo()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _init_repo(self):
        subprocess.run(["git", "init"], cwd=self.test_dir, check=True)
        # Ensure default branch is main
        subprocess.run(["git", "branch", "-M", "main"], cwd=self.test_dir, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.test_dir,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=self.test_dir, check=True
        )

    def _commit(self, message, author_email, date_offset_days=0):
        # Create a dummy file change to allow commit
        dummy_file = self.test_dir / "dummy.txt"
        with open(dummy_file, "a") as f:
            f.write(f"{message}\n")

        subprocess.run(["git", "add", "dummy.txt"], cwd=self.test_dir, check=True)

        date_str = (datetime.now() - timedelta(days=date_offset_days)).isoformat()
        env = {
            "GIT_AUTHOR_EMAIL": author_email,
            "GIT_COMMITTER_EMAIL": author_email,
            "GIT_AUTHOR_DATE": date_str,
            "GIT_COMMITTER_DATE": date_str,
        }

        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.test_dir,
            check=True,
            env={**subprocess.os.environ, **env},
        )

    def test_get_direct_committers_filtering(self):
        # 1. Direct commit (Should be included)
        # We need to set the config user.name for each commit to test name extraction
        subprocess.run(
            ["git", "config", "user.name", "Direct User"], cwd=self.test_dir, check=True
        )
        self._commit("Direct commit", "direct@example.com")

        # 2. Squash merge commit (Should be excluded)
        subprocess.run(
            ["git", "config", "user.name", "Squash User"], cwd=self.test_dir, check=True
        )
        self._commit("Squash commit (#123)", "squash@example.com")

        # 3. Rebase merge commit (Should be excluded)
        subprocess.run(
            ["git", "config", "user.name", "Rebase User"], cwd=self.test_dir, check=True
        )
        self._commit("Rebase commit (#456)", "rebase@example.com")

        # 4. Standard Merge commit (Should be excluded by --no-merges)
        subprocess.run(
            ["git", "checkout", "-b", "feature"], cwd=self.test_dir, check=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Feature User"],
            cwd=self.test_dir,
            check=True,
        )
        self._commit("Feature commit", "feature@example.com")

        subprocess.run(["git", "checkout", "main"], cwd=self.test_dir, check=True)
        subprocess.run(
            ["git", "config", "user.name", "Merge User"], cwd=self.test_dir, check=True
        )
        subprocess.run(
            ["git", "merge", "--no-ff", "feature", "-m", "Merge pull request #789"],
            cwd=self.test_dir,
            check=True,
            env={**subprocess.os.environ, "GIT_COMMITTER_EMAIL": "merge@example.com"},
        )

        start_date = datetime.now() - timedelta(days=90)
        end_date = datetime.now()

        committers = self.extractor._get_direct_committers(
            self.test_dir, start_date, end_date
        )

        self.assertIn("Direct User", committers)
        self.assertNotIn("Squash User", committers)
        self.assertNotIn("Rebase User", committers)
        self.assertNotIn("Merge User", committers)  # Filtered by --no-merges
        self.assertNotIn("Feature User", committers)  # Filtered by --first-parent
        self.assertNotIn(
            "feature@example.com", committers
        )  # Filtered by --first-parent

    def test_calculate_team_stats_integration(self):
        # Mock WorkflowRun repository
        self.extractor.workflow_run_repo = MagicMock()

        # Mock runs
        # Run 1: PR Run (Should be included)
        run1 = MagicMock()
        run1.raw_payload = {
            "event": "pull_request",
            "triggering_actor": {"login": "pr_user"},
        }

        # Run 2: Push Run (Should be excluded)
        run2 = MagicMock()
        run2.raw_payload = {
            "event": "push",
            "pull_requests": [],
            "triggering_actor": {"login": "push_user"},
        }

        self.extractor.workflow_run_repo.find_in_date_range.return_value = [run1, run2]

        # Create a direct commit
        self._commit("Direct", "direct@example.com")

        # Create a build sample mock
        build_sample = MagicMock()
        build_sample.tr_original_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.test_dir, text=True
        ).strip()

        # Mock Repo object
        repo = MagicMock()
        repo.id = "repo_id"
        repo.full_name = "test/repo"

        # Use real git repo
        from git import Repo

        git_repo = Repo(self.test_dir)

        stats = self.extractor._calculate_team_stats(
            build_sample, git_repo, repo, [build_sample.tr_original_commit]
        )

        # Team size should be 2: "Test User" (committer name from config) + "pr_user" (PR merger)
        # Note: In _init_repo we set user.name to "Test User".
        # The direct commit author name will be "Test User".
        self.assertEqual(stats["gh_team_size"], 2)

        # The author "Test User" is in the team
        self.assertTrue(stats["gh_by_core_team_member"])


if __name__ == "__main__":
    unittest.main()
