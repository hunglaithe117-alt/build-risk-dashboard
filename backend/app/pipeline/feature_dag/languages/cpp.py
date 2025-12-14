import re
from .base import LanguageStrategy


class CppStrategy(LanguageStrategy):
    def strip_comments(self, line: str) -> str:
        line = re.sub(r"//.*", "", line)
        line = re.sub(r"/\*.*?\*/", "", line)
        return line.strip()

    def is_test_file(self, path: str) -> bool:
        path_lower = path.lower()
        # Common conventions: test folder, or *test.cpp, *Test.cpp
        # Check for test directories (start or middle)
        parts = path_lower.split("/")
        if "test" in parts or "tests" in parts:
            return True

        return (
            path_lower.endswith("_test.cpp")
            or path_lower.endswith("_test.cc")
            or path_lower.endswith("test.cpp")
        )

    def matches_test_definition(self, line: str) -> bool:
        # GoogleTest, Catch2, Boost.Test
        patterns = [
            r"^\s*TEST\s*\(",
            r"^\s*TEST_F\s*\(",
            r"^\s*TEST_P\s*\(",
            r"^\s*TYPED_TEST\s*\(",
            r"^\s*SCENARIO\s*\(",
            r"^\s*CATCH_CONFIG_MAIN",
            r"^\s*BOOST_AUTO_TEST_CASE\s*\(",
        ]
        return any(re.search(p, line) for p in patterns)

    def matches_assertion(self, line: str) -> bool:
        # GoogleTest, Catch2
        patterns = [
            r"^\s*ASSERT_",
            r"^\s*EXPECT_",
            r"^\s*CHECK\s*\(",
            r"^\s*REQUIRE\s*\(",
        ]
        return any(re.search(p, line) for p in patterns)

    def is_source_file(self, path: str) -> bool:
        extensions = {".cpp", ".cc", ".cxx", ".c", ".h", ".hpp"}
        return any(path.lower().endswith(ext) for ext in extensions)
