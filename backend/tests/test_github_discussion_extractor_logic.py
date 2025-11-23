import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone
from app.services.extracts.github_discussion_extractor import GitHubDiscussionExtractor
from app.models.entities.build_sample import BuildSample
from app.models.entities.imported_repository import ImportedRepository
from app.models.entities.workflow_run import WorkflowRunRaw
from bson import ObjectId


class TestGitHubDiscussionExtractorLogic(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.extractor = GitHubDiscussionExtractor(db=self.mock_db)
        self.extractor.workflow_run_repo = MagicMock()

    @patch("app.services.extracts.github_discussion_extractor.get_app_github_client")
    def test_extract_logic(self, mock_get_client):
        # Setup
        mock_gh = MagicMock()
        mock_get_client.return_value.__enter__.return_value = mock_gh

        repo = ImportedRepository(
            _id=ObjectId(),
            user_id=ObjectId(),
            full_name="test/repo",
            provider="github",
            import_status="imported",
            installation_id="123",
        )

        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=2)
        mid_time = now - timedelta(hours=1)
        end_time = now

        build_sample = BuildSample(
            repo_id=repo.id,
            workflow_run_id=100,
            tr_original_commit="sha1",
            git_all_built_commits=["sha1", "sha2"],
            gh_build_started_at=end_time,
            gh_pr_created_at=start_time.isoformat(),
            tr_prev_build=99,
        )

        workflow_run = WorkflowRunRaw(
            repo_id=repo.id,
            workflow_run_id=100,
            head_sha="sha1",
            run_number=100,
            status="completed",
            conclusion="success",
            created_at=end_time,
            updated_at=end_time,
            raw_payload={"number": 123, "pull_requests": [{"number": 123}]},
        )

        # Mock Previous Build
        prev_run = WorkflowRunRaw(
            repo_id=repo.id,
            workflow_run_id=99,
            head_sha="sha0",
            run_number=99,
            status="completed",
            conclusion="success",
            created_at=start_time,
            updated_at=start_time,
            raw_payload={},
        )
        self.extractor.workflow_run_repo.find_by_repo_and_run_id.return_value = prev_run

        # Mock GitHub Responses
        # Commit comments: 2 for sha1, 1 for sha2
        mock_gh.list_commit_comments.side_effect = lambda repo, sha: (
            ["c1", "c2"] if sha == "sha1" else ["c3"]
        )

        # PR Review Comments: 1 inside window, 1 outside
        mock_gh.list_review_comments.return_value = [
            {"created_at": mid_time.isoformat()},
            {"created_at": (start_time - timedelta(minutes=1)).isoformat()},
        ]

        # Issue Comments: 1 inside window, 1 outside
        mock_gh.list_issue_comments.return_value = [
            {"created_at": mid_time.isoformat()},
            {"created_at": (end_time + timedelta(minutes=1)).isoformat()},
        ]

        # Execute
        result = self.extractor.extract(build_sample, workflow_run, repo)

        # Verify
        self.assertEqual(result["gh_num_commit_comments"], 3)  # 2 + 1
        self.assertEqual(result["gh_num_pr_comments"], 1)
        self.assertEqual(result["gh_num_issue_comments"], 1)

    @patch("app.services.extracts.github_discussion_extractor.get_public_github_client")
    def test_extract_public_repo(self, mock_get_public_client):
        # Setup
        mock_gh = MagicMock()
        mock_get_public_client.return_value.__enter__.return_value = mock_gh

        repo = ImportedRepository(
            _id=ObjectId(),
            user_id=ObjectId(),
            full_name="test/public-repo",
            provider="github",
            import_status="imported",
            installation_id=None,  # Public repo
        )

        build_sample = BuildSample(
            repo_id=repo.id,
            workflow_run_id=101,
            tr_original_commit="sha1",
            git_all_built_commits=["sha1"],
            gh_build_started_at=datetime.now(timezone.utc),
            gh_pr_created_at=None,
            tr_prev_build=None,
        )

        workflow_run = WorkflowRunRaw(
            repo_id=repo.id,
            workflow_run_id=101,
            head_sha="sha1",
            run_number=101,
            status="completed",
            conclusion="success",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            raw_payload={},
        )

        # Mock responses
        mock_gh.list_commit_comments.return_value = []

        # Execute
        self.extractor.extract(build_sample, workflow_run, repo)

        # Verify
        mock_get_public_client.assert_called_once()


if __name__ == "__main__":
    unittest.main()
