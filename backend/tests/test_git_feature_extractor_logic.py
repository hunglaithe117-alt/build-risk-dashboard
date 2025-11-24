import shutil
import tempfile
import unittest
import subprocess
from pathlib import Path
from app.services.extracts.git_feature_extractor import GitFeatureExtractor


class TestableGitFeatureExtractor(GitFeatureExtractor):
    def __init__(self):
        self.db = None
        self.build_sample_repo = None
        self.workflow_run_repo = None


class TestGitFeatureExtractorLogic(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.repo_path = Path(self.test_dir)
        self._run_git(["init"])
        self._run_git(["config", "user.email", "test@example.com"])
        self._run_git(["config", "user.name", "Test User"])

        # Mock DB
        self.extractor = TestableGitFeatureExtractor()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _run_git(self, args):
        subprocess.run(
            ["git"] + args, cwd=self.repo_path, check=True, capture_output=True
        )
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_calculate_diff_features(self):
        # Commit 1: Add src/main.py
        (self.repo_path / "src").mkdir()
        (self.repo_path / "src" / "main.py").write_text("print('hello')\n")
        self._run_git(["add", "."])
        commit1 = self._run_git(["commit", "-m", "Initial commit"])

        # Commit 2: Modify src/main.py, Add tests/test_main.py (1 test)
        (self.repo_path / "src" / "main.py").write_text(
            "print('hello')\nprint('world')\n"
        )
        (self.repo_path / "tests").mkdir()
        (self.repo_path / "tests" / "test_main.py").write_text(
            "def test_one():\n    assert True\n"
        )
        self._run_git(["add", "."])
        commit2 = self._run_git(["commit", "-m", "Add test"])

        # Commit 3: Modify src/main.py, Modify tests/test_main.py (+1 test)
        (self.repo_path / "src" / "main.py").write_text(
            "print('hello')\nprint('world')\nprint('!')\n"
        )
        (self.repo_path / "tests" / "test_main.py").write_text(
            "def test_one():\n    assert True\n\ndef test_two():\n    assert True\n"
        )
        self._run_git(["add", "."])
        commit3 = self._run_git(["commit", "-m", "Add another test"])

        # Built commits: commit2, commit3. Prev built: commit1.
        built_commits = [commit2, commit3]
        prev_built_commit = commit1
        current_commit = commit3

        stats = self.extractor._calculate_diff_features(
            self.repo_path, built_commits, prev_built_commit, current_commit, "python"
        )

        print(f"Stats: {stats}")

        # Verification
        # gh_diff_files_modified:
        # Commit 2: src/main.py (M). tests/test_main.py (A). -> 1 Modified (src/main.py)
        # Commit 3: src/main.py (M). tests/test_main.py (M). -> 2 Modified (src/main.py, tests/test_main.py)
        # Total Modified Events: 1 + 2 = 3
        self.assertEqual(stats["gh_diff_files_modified"], 3)

        # gh_diff_files_added:
        # Commit 2: tests/test_main.py (A) -> 1 Added
        # Commit 3: None -> 0 Added
        # Total Added Events: 1
        self.assertEqual(stats["gh_diff_files_added"], 1)

        # git_diff_src_churn:
        # Commit 2: src/main.py (+1 line) -> 1
        # Commit 3: src/main.py (+1 line) -> 1
        # Total: 2 (Cumulative sum)
        self.assertEqual(stats["git_diff_src_churn"], 2)

        # gh_diff_tests_added:
        # Net diff between commit1 and commit3
        # Commit 1: 0 tests
        # Commit 3: 2 tests
        # Total: 2
        self.assertEqual(stats["gh_diff_tests_added"], 2)


if __name__ == "__main__":
    unittest.main()
