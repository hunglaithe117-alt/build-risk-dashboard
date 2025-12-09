import shutil
import tempfile
import unittest
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

# Mocking modules that might not be easily importable or initialized in test env
sys.modules["app.pipeline.resources"] = MagicMock()
sys.modules["app.pipeline.resources.git_repo"] = MagicMock()
sys.modules["app.pipeline.resources.log_storage"] = MagicMock()
sys.modules["app.pipeline.resources.github_client"] = MagicMock()
sys.modules["app.pipeline.resources.sonar"] = MagicMock()
from app.pipeline.resources import ResourceNames
from app.pipeline.resources.git_repo import GitRepoHandle

# Import the nodes under test
from app.pipeline.features.git.commit_info import GitCommitInfoNode
from app.pipeline.core.context import ExecutionContext


class TestGitPipelineFeatures(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self._init_repo()

        # Common Mock Setup
        self.db = MagicMock()
        self.build_sample = MagicMock()
        self.build_sample.repo_id = "test_repo_id"
        self.build_sample.workflow_run_id = 100
        self.build_sample.created_at = datetime.now(timezone.utc)

        self.git_handle = MagicMock()
        self.git_handle.path = self.test_dir
        self.git_handle.is_commit_available = True

        # Use real git repo object for handle
        from git import Repo

        self.repo = Repo(self.test_dir)
        self.git_handle.repo = self.repo

        self.context = MagicMock(spec=ExecutionContext)
        self.context.db = self.db
        self.context.build_sample = self.build_sample
        self.context.get_resource.side_effect = lambda name: (
            self.git_handle if name == ResourceNames.GIT_REPO else None
        )

        # Feature dictionary for context
        self.features = {}
        self.context.get_feature.side_effect = (
            lambda name, default=None: self.features.get(name, default)
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _init_repo(self):
        subprocess.run(["git", "init"], cwd=self.test_dir, check=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=self.test_dir, check=True)
        self._set_git_identity("Test User", "test@example.com")

    def _set_git_identity(self, name, email):
        subprocess.run(
            ["git", "config", "user.name", name], cwd=self.test_dir, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", email], cwd=self.test_dir, check=True
        )

    def _commit(self, message, allow_empty=False):
        if not allow_empty:
            (self.test_dir / "file.txt").write_text(f"content {message}")
            subprocess.run(["git", "add", "file.txt"], cwd=self.test_dir, check=True)

        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", message],
            cwd=self.test_dir,
            check=True,
        )
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.test_dir, text=True
        ).strip()

    def test_commit_info_walking(self):
        """Test that GitCommitInfoNode correctly walks history to find previous build."""

        # History: C1 -> C2 -> C3
        c1 = self._commit("C1")
        c2 = self._commit("C2")
        c3 = self._commit("C3")

        self.git_handle.effective_sha = c3

        # Mock DB: C1 was a pre-created build (exists in DB)
        # The node calls: db["model_builds"].find_one(...) with head_sha field

        def find_one_side_effect(query):
            # Check if query matches C1 by head_sha field
            if query.get("head_sha") == c1:
                return {
                    "workflow_run_id": 99,
                    "head_sha": c1,
                }
            return None

        self.db.__getitem__.return_value.find_one.side_effect = find_one_side_effect

        node = GitCommitInfoNode()
        result = node.extract(self.context)

        # Expectation:
        # Prev built commit should be C1
        # Built commits should be [C3, C2] (or reverse, depending on implementation detail)
        # Note: Implementation logic was:
        # walker = repo.iter_commits(c3)
        # C3 -> loop, not built, append
        # C2 -> loop, not built, append
        # C1 -> loop, built! break.
        # prev_commits_objs = [C3, C2]

        self.assertEqual(result["git_prev_built_commit"], c1)
        self.assertEqual(result["tr_prev_build"], 99)
        self.assertEqual(result["git_prev_commit_resolution_status"], "build_found")

        # Verify built commits list
        self.assertIn(c2, result["git_all_built_commits"])
        self.assertIn(c3, result["git_all_built_commits"])
        self.assertNotIn(c1, result["git_all_built_commits"])
        self.assertEqual(result["git_num_all_built_commits"], 2)
