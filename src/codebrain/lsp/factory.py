"""Factory for creating LSP reporters based on language and workspace root."""

from __future__ import annotations

import logging
from pathlib import Path

from codebrain.core.interfaces import ContextAwareDiagnosticReporter
from codebrain.core.models import SubProject
from codebrain.fallback.chain import FallbackChain
from codebrain.fallback.hints import get_hints
from codebrain.lsp.servers.multi import MultiLanguageReporter
from codebrain.lsp.servers.pyright import PyrightReporter

logger = logging.getLogger(__name__)

# Registry mapping language names to their reporter classes
_LANGUAGE_FACTORIES: dict[str, type] = {
    "python": PyrightReporter,
}

# Registry mapping language names to their CLI fallback classes (if any)
_FALLBACK_FACTORIES: dict[str, type] = {}

# Python always has a CLI fallback
try:
    from codebrain.fallback.pyright_cli import PyrightCLIReporter
    _FALLBACK_FACTORIES["python"] = PyrightCLIReporter
except ImportError:
    pass

# Go always has a CLI fallback
try:
    from codebrain.fallback.govet_cli import GoVetCLIReporter
    _FALLBACK_FACTORIES["go"] = GoVetCLIReporter
except ImportError:
    pass

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
    reporters: list[ContextAwareDiagnosticReporter] = []
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

        primary = factory(workspace_root, **kwargs)

        # Wrap in FallbackChain if a CLI fallback exists for this language
        fallback_factory = _FALLBACK_FACTORIES.get(lang)
        if fallback_factory is not None:
            fallback = fallback_factory(workspace_root)
            hints = get_hints(lang, "server_missing")
            reporter = FallbackChain(primary=primary, fallback=fallback, hints=hints)
        else:
            reporter = primary

        reporters.append(reporter)
    return MultiLanguageReporter(workspace_root, reporters)
