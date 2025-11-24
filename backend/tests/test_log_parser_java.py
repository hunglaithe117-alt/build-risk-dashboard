import unittest
from app.services.extracts.log_parser import TestLogParser


class TestJavaMavenLogParser(unittest.TestCase):
    def setUp(self):
        self.parser = TestLogParser()

    def test_maven_junit_basic(self):
        log = """
-------------------------------------------------------
 T E S T S
-------------------------------------------------------
Running com.example.AppTest
Tests run: 5, Failures: 1, Errors: 0, Skipped: 0, Time elapsed: 0.123 sec <<< FAILURE!
        """
        result = self.parser.parse(log)
        self.assertEqual(result.framework, "junit")
        self.assertEqual(result.language, "java")
        self.assertEqual(result.tests_run, 5)
        self.assertEqual(result.tests_failed, 1)
        self.assertEqual(result.tests_skipped, 0)
        self.assertAlmostEqual(result.test_duration_seconds, 0.123)

    def test_maven_junit_with_skipped(self):
        log = """
Tests run: 10, Failures: 2, Errors: 1, Skipped: 3
        """
        result = self.parser.parse(log)
        self.assertEqual(result.framework, "junit")
        self.assertEqual(result.tests_run, 10)
        self.assertEqual(result.tests_failed, 3)  # 2 failures + 1 error
        self.assertEqual(result.tests_skipped, 3)

    def test_maven_testng(self):
        log = """
===============================================
TestNG
Total tests run: 25, Failures: 2, Skips: 5
===============================================
        """
        result = self.parser.parse(log)
        self.assertEqual(result.framework, "testng")
        self.assertEqual(result.language, "java")
        self.assertEqual(result.tests_run, 25)
        self.assertEqual(result.tests_failed, 2)
        self.assertEqual(result.tests_skipped, 5)

    def test_maven_junit_no_failures(self):
        log = """
Tests run: 8, Failures: 0, Errors: 0, Skipped: 1, Time elapsed: 5.432 sec
        """
        result = self.parser.parse(log)
        self.assertEqual(result.framework, "junit")
        self.assertEqual(result.tests_run, 8)
        self.assertEqual(result.tests_failed, 0)
        self.assertEqual(result.tests_skipped, 1)
        self.assertEqual(result.tests_ok, 7)


if __name__ == "__main__":
    unittest.main()
