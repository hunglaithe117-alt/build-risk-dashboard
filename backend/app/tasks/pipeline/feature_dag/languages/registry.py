from .base import LanguageStrategy
from .cpp import CppStrategy
from .generic import GenericStrategy
from .go import GoStrategy
from .java import JavaStrategy
from .javascript import JavascriptStrategy
from .python import PythonStrategy
from .ruby import RubyStrategy


class LanguageRegistry:
    _strategies: dict[str, LanguageStrategy] = {
        "python": PythonStrategy(),
        "java": JavaStrategy(),
        "ruby": RubyStrategy(),
        "javascript": JavascriptStrategy(),
        "typescript": JavascriptStrategy(),
        "go": GoStrategy(),
        "cpp": CppStrategy(),
    }
    _generic = GenericStrategy()

    @classmethod
    def get_strategy(cls, language: str) -> LanguageStrategy:
        """Get strategy for specific language, defaulting to generic."""
        return cls._strategies.get(language.lower(), cls._generic)

    @classmethod
    def get_supported_languages(cls) -> list[str]:
        """Get list of supported languages."""
        return list(cls._strategies.keys())
