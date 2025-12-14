import re
from .base import LanguageStrategy


class JavascriptStrategy(LanguageStrategy):
    def strip_comments(self, line: str) -> str:
        # Remove single-line comments //
        line = re.sub(r"//.*", "", line)
        # Remove multi-line comments /* ... */ (simplified for single line processing)
        line = re.sub(r"/\*.*?\*/", "", line)
        return line.strip()

    def is_test_file(self, path: str) -> bool:
        path_lower = path.lower()
        if "/node_modules/" in path_lower:
            return False

        return (
            path_lower.endswith(".test.js")
            or path_lower.endswith(".spec.js")
            or path_lower.endswith(".test.ts")
            or path_lower.endswith(".spec.ts")
            or path_lower.endswith(".test.jsx")
            or path_lower.endswith(".spec.jsx")
            or path_lower.endswith(".test.tsx")
            or path_lower.endswith(".spec.tsx")
            or "/__tests__/" in path_lower
            or "/test/" in path_lower
            or "/tests/" in path_lower
        )

    def matches_test_definition(self, line: str) -> bool:
        # Jest, Mocha, Jasmine patterns
        patterns = [
            r"^\s*describe\s*\(",
            r"^\s*it\s*\(",
            r"^\s*test\s*\(",
            r"^\s*context\s*\(",
            r"^\s*suite\s*\(",
            r"^\s*beforeAll\s*\(",
            r"^\s*afterAll\s*\(",
            r"^\s*beforeEach\s*\(",
            r"^\s*afterEach\s*\(",
        ]
        return any(re.search(p, line) for p in patterns)

    def matches_assertion(self, line: str) -> bool:
        # Jest, Chai, Assert patterns
        patterns = [r"expect\s*\(", r"assert\.", r"\.should\."]
        return any(re.search(p, line) for p in patterns)

    def is_source_file(self, path: str) -> bool:
        path_lower = path.lower()
        if "/node_modules/" in path_lower:
            return False

        extensions = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
        return any(path_lower.endswith(ext) for ext in extensions)
