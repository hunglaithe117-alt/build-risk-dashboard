from abc import ABC, abstractmethod


class LanguageStrategy(ABC):
    @abstractmethod
    def strip_comments(self, line: str) -> str:
        """Strip comments from a line."""
        pass

    @abstractmethod
    def is_test_file(self, path: str) -> bool:
        """Determine if a file is a test file."""
        pass

    @abstractmethod
    def matches_test_definition(self, line: str) -> bool:
        """Check if line matches a test definition."""
        pass

    @abstractmethod
    def matches_assertion(self, line: str) -> bool:
        """Check if line matches an assertion."""
        pass

    @abstractmethod
    def is_source_file(self, path: str) -> bool:
        """Determine if a file is a source code file."""
        pass
