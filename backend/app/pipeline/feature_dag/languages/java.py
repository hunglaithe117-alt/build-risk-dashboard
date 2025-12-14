import re
from .base import LanguageStrategy


class JavaStrategy(LanguageStrategy):
    def strip_comments(self, line: str) -> str:
        if "//" in line:
            return line.split("//", 1)[0]
        return line

    def is_test_file(self, path: str) -> bool:
        lowered = path.lower()
        if not path.endswith(".java"):
            return False
        has_test_dir = any(x in lowered for x in ["test/", "tests/"])
        is_test_suffix = bool(re.search(r"[tT]est\.java$", path))
        return has_test_dir or is_test_suffix

    def matches_test_definition(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        # Java: @Test OR (public|protected|private|static|\s) +[\w<>\[\]]+\s+(.*[tT]est) *\([^\)]*\) *(\{?|[^;])
        return bool(
            re.search(r"@Test", stripped)
            or re.search(
                r"(public|protected|private|static|\s) +[\w<>\[\]]+\s+(.*[tT]est) *\([^\)]*\) *(\{?|[^;])",
                stripped,
            )
        )

    def matches_assertion(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        return bool(re.search(r"assert", stripped))

    def is_source_file(self, path: str) -> bool:
        return path.lower().endswith(".java")
