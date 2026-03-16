"""Factory for creating LSP reporters based on language and workspace root."""

from __future__ import annotations

import logging
from pathlib import Path

from codebrain.core.models import SubProject
from codebrain.lsp.servers.multi import MultiLanguageReporter
from codebrain.lsp.servers.pyright import PyrightReporter

logger = logging.getLogger(__name__)

# Registry mapping language names to their reporter classes
_LANGUAGE_FACTORIES: dict[str, type] = {
    "python": PyrightReporter,
}

# Lazy-import optional reporters
try:
    from codebrain.lsp.servers.clangd import ClangdReporter
    _LANGUAGE_FACTORIES["cpp"] = ClangdReporter
except ImportError:
    pass

try:
    from codebrain.lsp.servers.typescript import TypeScriptReporter
    _LANGUAGE_FACTORIES["typescript"] = TypeScriptReporter
except ImportError:
    pass

try:
    from codebrain.lsp.servers.gopls import GoplsReporter
    _LANGUAGE_FACTORIES["go"] = GoplsReporter
except ImportError:
    pass


def build_multi_reporter(
    workspace_root: Path,
    languages: list[str] | None = None,
    sub_project: SubProject | None = None,
) -> MultiLanguageReporter:
    """Build a MultiLanguageReporter for the requested languages at the given root."""
    langs = languages or list(_LANGUAGE_FACTORIES.keys())
    reporters = []
    for lang in langs:
        factory = _LANGUAGE_FACTORIES.get(lang)
        if factory is None:
            logger.warning("No reporter factory for language: %s", lang)
            continue

        # Pass toolchain env to reporter if available
        kwargs: dict = {}
        if sub_project:
            tc = sub_project.toolchain
            if lang == "python" and tc.python_env:
                kwargs["python_env"] = tc.python_env
            elif lang == "go" and tc.go_env:
                kwargs["go_env"] = tc.go_env
            elif lang == "typescript" and tc.node_env:
                kwargs["node_env"] = tc.node_env
            elif lang == "cpp" and tc.cpp_env:
                kwargs["cpp_env"] = tc.cpp_env

        reporters.append(factory(workspace_root, **kwargs))
    return MultiLanguageReporter(workspace_root, reporters)
