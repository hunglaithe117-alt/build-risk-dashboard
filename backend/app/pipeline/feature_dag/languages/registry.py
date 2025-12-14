from .base import LanguageStrategy
from .python import PythonStrategy
from .java import JavaStrategy
from .ruby import RubyStrategy
from .javascript import JavascriptStrategy
from .go import GoStrategy
from .cpp import CppStrategy
from .generic import GenericStrategy


class LanguageRegistry:
    _strategies: dict[str, LanguageStrategy] = {
        "python": PythonStrategy(),
        "java": JavaStrategy(),
        "ruby": RubyStrategy(),
        "javascript": JavascriptStrategy(),
        "typescript": JavascriptStrategy(),
        "go": GoStrategy(),
        "cpp": CppStrategy(),
        "c++": CppStrategy(),
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
