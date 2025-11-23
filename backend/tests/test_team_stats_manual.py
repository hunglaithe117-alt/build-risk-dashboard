import unittest
from typing import Set, Tuple
from app.services.extracts.git_feature_extractor import GitFeatureExtractor


class TestTeamStats(unittest.TestCase):
    def setUp(self):
        # Mock DB as None since we are only testing the static-like method
        self.extractor = GitFeatureExtractor(db=None)

    def test_resolve_team_size_and_membership(self):
        # Format: (Name, Email, Login)

        # Historical people
        historical: Set[Tuple[str, str, str]] = {
            ("John Doe", "john@example.com", "johndoe"),
            ("Jane Smith", "jane@example.com", "janesmith"),
            ("Alice", "alice@example.com", "alice"),
        }

        # Case 1: Exact match by Email
        current_1 = {("Johnny", "john@example.com", None)}
        size_1, is_member_1 = self.extractor._resolve_team_size_and_membership(
            current_1, historical
        )
        self.assertEqual(size_1, 3)
        self.assertTrue(is_member_1, "Should match by email")

        # Case 2: Exact match by Login
        current_2 = {("Unknown", None, "janesmith")}
        size_2, is_member_2 = self.extractor._resolve_team_size_and_membership(
            current_2, historical
        )
        self.assertEqual(size_2, 3)
        self.assertTrue(is_member_2, "Should match by login")

        # Case 3: Fuzzy match by Name (Jaro-Winkler > 0.9)
        # "John Doe" vs "John Do" -> likely high similarity
        current_3 = {("John Do", None, None)}
        size_3, is_member_3 = self.extractor._resolve_team_size_and_membership(
            current_3, historical
        )
        self.assertEqual(size_3, 3)
        self.assertTrue(is_member_3, "Should match by fuzzy name")

        # Case 4: No match
        current_4 = {("Bob", "bob@example.com", "bob")}
        size_4, is_member_4 = self.extractor._resolve_team_size_and_membership(
            current_4, historical
        )
        self.assertEqual(size_4, 3)  # Historical size is still 3
        self.assertFalse(is_member_4, "Should not match")

        # Case 5: Identity Merging within Historical Data
        # If historical data has duplicates that should be merged
        historical_dirty = {
            ("John Doe", "john@example.com", "johndoe"),
            ("John Doe", "other@email.com", None),  # Same name
            ("Johnny", "john@example.com", None),  # Same email
        }
        # These 3 should be merged into 1 person ideally if the logic handles it?
        # The current logic builds unique_identities from historical_people.
        # Let's trace:
        # 1. ("John Doe", "john@example.com", "johndoe") -> New Identity 1
        # 2. ("John Doe", "other@email.com", None) -> Matches Identity 1 by Name?
        #    Name "John Doe" == "John Doe", sim = 1.0 > 0.9. Yes.
        # 3. ("Johnny", "john@example.com", None) -> Matches Identity 1 by Email. Yes.

        # So size should be 1.

        # We need to pass a dummy current set
        size_5, _ = self.extractor._resolve_team_size_and_membership(
            set(), historical_dirty
        )
        self.assertEqual(
            size_5, 1, "Should merge duplicate identities in historical data"
        )


if __name__ == "__main__":
    unittest.main()
