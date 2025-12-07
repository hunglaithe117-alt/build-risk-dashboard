import re
from .base import LanguageStrategy


class GoStrategy(LanguageStrategy):
    def strip_comments(self, line: str) -> str:
        line = re.sub(r"//.*", "", line)
        line = re.sub(r"/\*.*?\*/", "", line)
        return line.strip()

    def is_test_file(self, path: str) -> bool:
        return path.lower().endswith("_test.go")

    def matches_test_definition(self, line: str) -> bool:
        # standard go test: func TestXxx(t *testing.T)
        return bool(re.search(r"^\s*func\s+Test", line))

    def matches_assertion(self, line: str) -> bool:
        # t.Error, t.Fail, or commonly used assert libraries like testify
        patterns = [r"t\.(Error|Fail|Fatal|Log)", r"assert\.", r"require\."]
        return any(re.search(p, line) for p in patterns)

    def is_source_file(self, path: str) -> bool:
        return path.lower().endswith(".go")
