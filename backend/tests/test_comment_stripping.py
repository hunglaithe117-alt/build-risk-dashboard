import unittest
from app.services.extracts.diff_analyzer import (
    _strip_comments,
    _strip_shell_comments,
    _strip_c_comments,
    _matches_test_definition,
    _matches_assertion,
)


class TestCommentStripping(unittest.TestCase):
    def test_strip_shell_comments_python(self):
        self.assertEqual(
            _strip_shell_comments("def test_foo():  # comment"), "def test_foo():  "
        )
        self.assertEqual(
            _strip_shell_comments("assert x == 1  # comment"), "assert x == 1  "
        )
        self.assertEqual(_strip_shell_comments("# def test_bar():"), "")
        self.assertEqual(_strip_shell_comments("no comment"), "no comment")

    def test_strip_c_comments_java(self):
        self.assertEqual(_strip_c_comments("@Test // comment"), "@Test ")
        self.assertEqual(_strip_c_comments("assert true; // comment"), "assert true; ")
        self.assertEqual(_strip_c_comments("// public void testFoo() {"), "")
        self.assertEqual(_strip_c_comments("no comment"), "no comment")

    def test_strip_comments_by_language(self):
        # Python
        self.assertEqual(
            _strip_comments("def test_foo():  # comment", "python"), "def test_foo():  "
        )
        # Ruby
        self.assertEqual(
            _strip_comments("def test_foo  # comment", "ruby"), "def test_foo  "
        )
        # Java
        self.assertEqual(_strip_comments("@Test // comment", "java"), "@Test ")

    def test_commented_out_tests_not_matched_python(self):
        # Commented-out test should not match
        line = "# def test_something():"
        clean_line = _strip_comments(line, "python")
        self.assertFalse(_matches_test_definition(clean_line, "python"))

        # Real test should match
        line = "def test_something():  # this is a comment"
        clean_line = _strip_comments(line, "python")
        self.assertTrue(_matches_test_definition(clean_line, "python"))

    def test_commented_out_assertions_not_matched_python(self):
        # Commented-out assertion should not match
        line = "# assert x == 1"
        clean_line = _strip_comments(line, "python")
        self.assertFalse(_matches_assertion(clean_line, "python"))

        # Real assertion should match
        line = "assert x == 1  # checking x"
        clean_line = _strip_comments(line, "python")
        self.assertTrue(_matches_assertion(clean_line, "python"))

    def test_commented_out_tests_not_matched_java(self):
        # Commented-out test should not match
        line = "// @Test"
        clean_line = _strip_comments(line, "java")
        self.assertFalse(_matches_test_definition(clean_line, "java"))

        # Real test should match
        line = "@Test // comment"
        clean_line = _strip_comments(line, "java")
        self.assertTrue(_matches_test_definition(clean_line, "java"))

    def test_commented_out_tests_not_matched_ruby(self):
        # Commented-out test should not match
        line = "# it 'does something' do"
        clean_line = _strip_comments(line, "ruby")
        self.assertFalse(_matches_test_definition(clean_line, "ruby"))

        # Real test should match
        line = "it 'does something' do  # comment"
        clean_line = _strip_comments(line, "ruby")
        self.assertTrue(_matches_test_definition(clean_line, "ruby"))


if __name__ == "__main__":
    unittest.main()
