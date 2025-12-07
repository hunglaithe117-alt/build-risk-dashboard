import re
from .base import LanguageStrategy


class RubyStrategy(LanguageStrategy):
    def strip_comments(self, line: str) -> str:
        if "#" in line:
            return line.split("#", 1)[0]
        return line

    def is_test_file(self, path: str) -> bool:
        lowered = path.lower()
        if not path.endswith(".rb"):
            return False
        has_test_dir = any(x in lowered for x in ["test/", "tests/", "spec/"])
        has_lib_dir = "lib/" in lowered
        return has_test_dir and not has_lib_dir

    def matches_test_definition(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        # Ruby: ^ *def +.*test.* OR ^\s*should\s+.*\s+(do|{) OR ^\s*it\s+.*\s+(do|{)
        return bool(
            re.match(r"^ *def +.*test.*", stripped)
            or re.match(r"^\s*should\s+.*\s+(do|{)", stripped)
            or re.match(r"^\s*it\s+.*\s+(do|{)", stripped)
        )

    def matches_assertion(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        # Ruby: assert, .should, .expect, .must_, .wont_
        return bool(
            re.search(r"assert", stripped)
            or re.search(r"\.should", stripped)
            or re.search(r"\.expect", stripped)
            or re.search(r"\.must_", stripped)
            or re.search(r"\.wont_", stripped)
            or re.search(r"(^|\s+)should\s*[({]?", stripped)
            or re.search(r"(^|\s+)expect\s*[({]?", stripped)
        )

    def is_source_file(self, path: str) -> bool:
        return path.lower().endswith((".rb", ".rake", ".erb"))
