"""Tree-sitter parser management with lazy grammar loading."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Language, Parser, Tree

LANGUAGE_MAP: dict[str, str] = {
    "python": "tree_sitter_python",
    "javascript": "tree_sitter_javascript",
    "typescript": "tree_sitter_typescript",
    "c": "tree_sitter_c",
    "cpp": "tree_sitter_cpp",
    "go": "tree_sitter_go",
}

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".go": "go",
}


def language_for_extension(ext: str) -> str | None:
    """Return the tree-sitter language name for a file extension."""
    return EXTENSION_TO_LANGUAGE.get(ext)


# Directories to skip when collecting source files
_SKIP_DIRS: set[str] = {
    ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules", ".git", ".hg", "dist", "build", ".tox", ".nox", ".eggs",
    "site-packages", ".cache", ".pytype", "vendor",
}


def collect_source_files(
    root: Path,
    language: str | None = None,
) -> list[tuple[Path, str]]:
    """Collect source files under *root*, skipping vendor/build directories.

    Returns a sorted list of (file_path, language) tuples.
    """
    extensions = {
        ext: lang
        for ext, lang in EXTENSION_TO_LANGUAGE.items()
        if language is None or lang == language
    }
    result: list[tuple[Path, str]] = []
    _walk_source_files(root, extensions, result)
    return sorted(result, key=lambda t: t[0])


def _walk_source_files(
    directory: Path,
    extensions: dict[str, str],
    result: list[tuple[Path, str]],
) -> None:
    try:
        entries = sorted(directory.iterdir())
    except PermissionError:
        return
    for entry in entries:
        if entry.is_dir():
            if entry.name not in _SKIP_DIRS:
                _walk_source_files(entry, extensions, result)
        elif entry.suffix in extensions:
            result.append((entry, extensions[entry.suffix]))


class TreeSitterParser:
    """Manages tree-sitter parsers and language grammars with lazy loading."""

    def __init__(self) -> None:
        self._languages: dict[str, Language] = {}
        self._parsers: dict[str, Parser] = {}

    def get_language(self, language: str) -> Language:
        """Load and cache a tree-sitter language grammar."""
        if language in self._languages:
            return self._languages[language]

        from tree_sitter import Language as TSLanguage

        module_name = LANGUAGE_MAP.get(language)
        if module_name is None:
            msg = f"Unsupported language: {language}"
            raise ValueError(msg)

        mod = importlib.import_module(module_name)
        # TypeScript package exposes language_typescript() and language_tsx()
        if language == "typescript" and hasattr(mod, "language_typescript"):
            lang = TSLanguage(mod.language_typescript())
        else:
            lang = TSLanguage(mod.language())

        self._languages[language] = lang
        return lang

    def get_parser(self, language: str) -> Parser:
        """Get a cached parser for the given language."""
        if language in self._parsers:
            return self._parsers[language]

        from tree_sitter import Parser as TSParser

        lang = self.get_language(language)
        parser = TSParser(lang)
        self._parsers[language] = parser
        return parser

    def parse(self, source: bytes, language: str) -> Tree:
        """Parse source bytes and return the syntax tree."""
        parser = self.get_parser(language)
        return parser.parse(source)

    def parse_file(self, file_path: Path) -> Tree:
        """Parse a file and return the syntax tree."""
        ext = file_path.suffix
        language = language_for_extension(ext)
        if language is None:
            msg = f"Cannot determine language for extension: {ext}"
            raise ValueError(msg)
        source = file_path.read_bytes()
        return self.parse(source, language)


# Module-level singleton for convenience
_default_parser: TreeSitterParser | None = None


def get_default_parser() -> TreeSitterParser:
    """Return the module-level default parser instance."""
    global _default_parser  # noqa: PLW0603
    if _default_parser is None:
        _default_parser = TreeSitterParser()
    return _default_parser
