import re
from .base import LanguageStrategy


class GenericStrategy(LanguageStrategy):
    TEST_DIR_HINTS = ("tests/", "test/", "spec/")

    def strip_comments(self, line: str) -> str:
        # Generic fallback: check both # and //
        if "#" in line:
            line = line.split("#", 1)[0]
        if "//" in line:
            line = line.split("//", 1)[0]
        return line

    def is_test_file(self, path: str) -> bool:
        lowered = path.lower()
        if any(hint in lowered for hint in self.TEST_DIR_HINTS):
            return True
        return lowered.endswith(
            ("_test.py", "_test.rb", "test.py", "test.rb", "_spec.rb")
        )

    def matches_test_definition(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        return bool(
            re.search(r"def\s+test_", stripped)
            or re.search(r"class\s+Test", stripped)
            or "self.assert" in stripped
            or "pytest.mark" in stripped
        )

    def matches_assertion(self, line: str) -> bool:
        stripped = line.strip()
        return "assert" in stripped

    def is_source_file(self, path: str) -> bool:
        # Fallback for generic
        return path.lower().endswith(
            (
                ".py",
                ".pyi",
                ".rb",
                ".rake",
                ".erb",
                ".java",
                ".js",
                ".ts",
                ".go",
                ".c",
                ".cpp",
            )
        )
