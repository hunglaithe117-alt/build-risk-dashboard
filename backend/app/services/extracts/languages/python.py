import re
from .base import LanguageStrategy


class PythonStrategy(LanguageStrategy):
    def strip_comments(self, line: str) -> str:
        if "#" in line:
            return line.split("#", 1)[0]
        return line

    def is_test_file(self, path: str) -> bool:
        lowered = path.lower()
        if not path.endswith(".py"):
            return False

        if any(x in lowered for x in ["test/", "tests/"]):
            return True

        filename = path.split("/")[-1]
        return (
            filename.lower().startswith("test_")
            or filename.lower().endswith("_test.py")
            or filename.lower() == "test.py"
        )

    def matches_test_definition(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        # Python: \s*def\s* test_(.*)\(.*\):
        return bool(re.search(r"\s*def\s* test_(.*)\(.*\):", stripped))

    def matches_assertion(self, line: str) -> bool:
        stripped = line.strip()
        # Python: assert([A-Z]\w*)?, (with)?\s*(pytest\.)?raises, (pytest.)?approx
        return bool(
            re.search(r"assert([A-Z]\w*)?", stripped)
            or re.search(r"(with)?\s*(pytest\.)?raises", stripped)
            or re.search(r"(pytest\.)?approx", stripped)
        )

    def is_source_file(self, path: str) -> bool:
        return path.lower().endswith((".py", ".pyi"))
