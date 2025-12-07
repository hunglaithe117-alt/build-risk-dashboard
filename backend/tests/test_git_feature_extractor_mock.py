import unittest
from unittest.mock import MagicMock
from datetime import datetime, timedelta
from app.services.extracts.git_feature_extractor import GitFeatureExtractor
from app.entities.imported_repository import ImportedRepository
from bson import ObjectId


class TestGitFeatureExtractorMock(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.extractor = GitFeatureExtractor(db=self.mock_db)
        # Mock the repositories
        self.extractor.build_sample_repo = MagicMock()
        self.extractor.workflow_run_repo = MagicMock()
        self.extractor.pr_repo = MagicMock()

    def test_fetch_mergers_uses_repo(self):
        # Setup
        repo = ImportedRepository(
            _id=ObjectId(),
            user_id=ObjectId(),
            full_name="test/repo",
            provider="github",
            import_status="imported",
        )
        start_date = datetime.now() - timedelta(days=10)
        end_date = datetime.now()

        # Mock return value
        self.extractor.pr_repo.get_mergers_in_range.return_value = {
            "merger1",
            "merger2",
        }

        # Execute
        mergers = self.extractor._fetch_mergers(repo, start_date, end_date)

        # Verify
        self.extractor.pr_repo.get_mergers_in_range.assert_called_once_with(
            repo.id, start_date, end_date
        )
        self.assertEqual(mergers, {"merger1", "merger2"})


if __name__ == "__main__":
    unittest.main()
