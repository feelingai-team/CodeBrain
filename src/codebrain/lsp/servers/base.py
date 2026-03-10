"""Base LSP reporter with context gathering capabilities."""

from __future__ import annotations

import asyncio
import logging
import re
from abc import abstractmethod
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from lsprotocol import converters
from lsprotocol import types as lsp

from codebrain.core.interfaces import ContextAwareDiagnosticReporter
from codebrain.core.models import (
    CodeActionSuggestion,
    Diagnostic,
    DiagnosticContext,
    DiagnosticSeverity,
    Position,
    Range,
    RelatedInformation,
    SignatureChangeImpact,
    SymbolLocation,
)
from codebrain.lsp.client import LSPClient

logger = logging.getLogger(__name__)

_converter = converters.get_converter()

# Utility functions


def uri_to_path(uri: str) -> Path:
    parsed = urlparse(uri)
    return Path(unquote(parsed.path))


def lsp_range_to_range(lsp_range: lsp.Range) -> Range:
    return Range(
        start=Position(line=lsp_range.start.line, character=lsp_range.start.character),
        end=Position(line=lsp_range.end.line, character=lsp_range.end.character),
    )


def range_to_lsp_range(range_: Range) -> lsp.Range:
    return lsp.Range(
        start=lsp.Position(line=range_.start.line, character=range_.start.character),
        end=lsp.Position(line=range_.end.line, character=range_.end.character),
    )


def lsp_severity_to_severity(
    lsp_severity: lsp.DiagnosticSeverity | None,
) -> DiagnosticSeverity:
    if lsp_severity is None:
        return DiagnosticSeverity.ERROR
    return DiagnosticSeverity(lsp_severity.value)


class LSPReporter(ContextAwareDiagnosticReporter):
    """Base class for all LSP-based diagnostic reporters."""

    # Subclasses set this to auto-discover the project root.
    # E.g. ("go.mod", "go.work") for Go, ("pyproject.toml",) for Python.
    _project_markers: tuple[str, ...] = ()

    def __init__(
        self,
        workspace_root: Path,
        server_command: list[str],
        language_id: str,
        reference_depth: int = 2,
        reference_limit: int = 8,
    ) -> None:
        self._workspace_root = workspace_root
        self._server_command = server_command
        self._language_id = language_id
        self._reference_depth = reference_depth
        self._reference_limit = reference_limit
        self._client: LSPClient | None = None
        self._diagnostics: dict[Path, list[Diagnostic]] = {}
        self._diagnostics_event: asyncio.Event = asyncio.Event()
        self._open_files: set[Path] = set()
        self._file_versions: dict[Path, int] = {}

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def supported_extensions(self) -> set[str]: ...

    @property
    def is_running(self) -> bool:
        return self._client is not None and self._client.is_running

    def _resolve_project_root(self) -> Path:
        """Find the best project root by looking for marker files.

        Checks the workspace root first, then one level of subdirectories.
        Returns workspace_root unchanged if no markers are defined or found.
        """
        if not self._project_markers:
            return self._workspace_root

        # Check workspace root itself
        for marker in self._project_markers:
            if (self._workspace_root / marker).exists():
                return self._workspace_root

        # Search one level down
        try:
            for child in sorted(self._workspace_root.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    for marker in self._project_markers:
                        if (child / marker).exists():
                            logger.info(
                                "Auto-detected %s project root: %s (found %s)",
                                self.name, child, marker,
                            )
                            return child
        except OSError:
            pass

        return self._workspace_root

    def _build_initialization_options(
        self, effective_root: Path
    ) -> dict[str, Any] | None:
        """Build LSP initialization options. Override in subclasses for server-specific settings."""
        return None

    # -- Lifecycle --

    async def start(self) -> None:
        if self.is_running:
            return
        effective_root = self._resolve_project_root()
        self._client = LSPClient(
            server_command=self._server_command,
            workspace_root=effective_root,
            notification_handlers={
                "textDocument/publishDiagnostics": self._handle_diagnostics,
            },
            initialization_options=self._build_initialization_options(effective_root),
        )
        await self._client.start()

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.stop()
            self._client = None
        self._diagnostics.clear()
        self._open_files.clear()
        self._file_versions.clear()
        self._diagnostics_event.clear()

    def _handle_diagnostics(self, params: dict[str, Any] | list[Any]) -> None:
        """Handle publishDiagnostics notification from the server."""
        if not isinstance(params, dict):
            return
        pub = _converter.structure(params, lsp.PublishDiagnosticsParams)
        file_path = uri_to_path(pub.uri)

        diagnostics: list[Diagnostic] = []
        for lsp_diag in pub.diagnostics:
            related: list[RelatedInformation] = []
            if lsp_diag.related_information:
                for info in lsp_diag.related_information:
                    related.append(
                        RelatedInformation(
                            file_path=str(uri_to_path(info.location.uri)),
                            range=lsp_range_to_range(info.location.range),
                            message=info.message,
                        )
                    )

            code: str | int | None = None
            code_url: str | None = None
            if lsp_diag.code is not None:
                code = lsp_diag.code
            if lsp_diag.code_description is not None:
                code_url = lsp_diag.code_description.href

            diagnostics.append(
                Diagnostic(
                    file_path=str(file_path),
                    range=lsp_range_to_range(lsp_diag.range),
                    severity=lsp_severity_to_severity(lsp_diag.severity),
                    message=lsp_diag.message,
                    source=lsp_diag.source,
                    code=code,
                    code_description_url=code_url,
                    related_information=related,
                    data=lsp_diag.data,
                )
            )

        self._diagnostics[file_path] = diagnostics
        self._diagnostics_event.set()

    async def _ensure_started(self) -> None:
        if not self.is_running:
            await self.start()

    # -- File management --

    async def open_file(self, file_path: Path) -> None:
        await self._ensure_started()
        assert self._client is not None
        if file_path in self._open_files:
            return
        self._file_versions[file_path] = 1
        self._diagnostics_event.clear()
        await self._client.did_open(file_path, self._language_id, version=1)
        self._open_files.add(file_path)

    async def update_file(self, file_path: Path, content: str) -> None:
        await self._ensure_started()
        assert self._client is not None
        if file_path not in self._open_files:
            await self.open_file(file_path)
        version = self._file_versions.get(file_path, 0) + 1
        self._file_versions[file_path] = version
        self._diagnostics_event.clear()
        await self._client.did_change(file_path, content, version)

    async def close_file(self, file_path: Path) -> None:
        if self._client is None or file_path not in self._open_files:
            return
        await self._client.did_close(file_path)
        self._open_files.discard(file_path)
        self._file_versions.pop(file_path, None)

    # -- Diagnostics --

    async def get_diagnostics(self, file_path: Path) -> list[Diagnostic]:
        if file_path in self._open_files:
            # Re-read from disk — the file may have been edited externally
            content = file_path.read_text(errors="replace")
            await self.update_file(file_path, content)
        else:
            await self.open_file(file_path)
        try:
            await asyncio.wait_for(self._diagnostics_event.wait(), timeout=5.0)
        except TimeoutError:
            logger.debug("Timed out waiting for diagnostics for %s", file_path)
        return self._diagnostics.get(file_path, [])

    async def get_all_diagnostics(self) -> dict[Path, list[Diagnostic]]:
        return dict(self._diagnostics)

    # -- Code actions --

    async def get_code_actions_for_diagnostic(
        self, diagnostic: Diagnostic
    ) -> list[CodeActionSuggestion]:
        await self._ensure_started()
        assert self._client is not None

        file_path = Path(diagnostic.file_path)
        await self.open_file(file_path)

        lsp_range = range_to_lsp_range(diagnostic.range)
        lsp_diag = lsp.Diagnostic(
            range=lsp_range,
            message=diagnostic.message,
            severity=lsp.DiagnosticSeverity(diagnostic.severity.value),
            source=diagnostic.source,
            code=diagnostic.code,
        )

        try:
            actions = await self._client.get_code_actions(
                file_path,
                lsp_range,
                diagnostics=[lsp_diag],
                only=[lsp.CodeActionKind.QuickFix],
            )
        except Exception:
            logger.debug("Error getting code actions", exc_info=True)
            return []

        suggestions: list[CodeActionSuggestion] = []
        for action in actions:
            if isinstance(action, lsp.CodeAction):
                suggestions.append(
                    CodeActionSuggestion(
                        title=action.title,
                        kind=action.kind if action.kind else None,
                        is_preferred=action.is_preferred or False,
                    )
                )
        return suggestions

    # -- Definition & references --

    async def _resolve_definition(
        self, file_path: Path, line: int, character: int
    ) -> SymbolLocation | None:
        assert self._client is not None
        try:
            result = await self._client.get_definition(file_path, line, character)
        except Exception:
            logger.debug("Error resolving definition", exc_info=True)
            return None

        if not result:
            return None

        first = result[0]
        if isinstance(first, lsp.LocationLink):
            return SymbolLocation(
                file_path=str(uri_to_path(first.target_uri)),
                range=lsp_range_to_range(first.target_range),
            )
        if isinstance(first, lsp.Location):
            return SymbolLocation(
                file_path=str(uri_to_path(first.uri)),
                range=lsp_range_to_range(first.range),
            )
        return None

    async def _gather_recursive_references(
        self,
        file_path: Path,
        line: int,
        character: int,
        max_depth: int,
        max_refs: int,
    ) -> tuple[list[SymbolLocation], bool]:
        """BFS reference gathering with depth/limit controls."""
        assert self._client is not None

        queue: deque[tuple[Path, int, int, int]] = deque()
        queue.append((file_path, line, character, 0))
        visited_defs: set[tuple[str, int, int]] = set()
        visited_refs: set[tuple[str, int, int]] = set()
        references: list[SymbolLocation] = []
        truncated = False

        while queue and not truncated:
            cur_path, cur_line, cur_char, depth = queue.popleft()

            definition = await self._resolve_definition(cur_path, cur_line, cur_char)
            if definition is not None:
                def_key = (
                    definition.file_path,
                    definition.range.start.line,
                    definition.range.start.character,
                )
                if def_key in visited_defs:
                    continue
                visited_defs.add(def_key)
                target_path = Path(definition.file_path)
                target_line = definition.range.start.line
                target_char = definition.range.start.character
            else:
                target_path = cur_path
                target_line = cur_line
                target_char = cur_char

            try:
                lsp_refs = await self._client.get_references(
                    target_path, target_line, target_char
                )
            except Exception:
                logger.debug("Error gathering references", exc_info=True)
                continue

            for ref in lsp_refs:
                ref_path = uri_to_path(ref.uri)
                ref_key = (str(ref_path), ref.range.start.line, ref.range.start.character)

                if ref_key in visited_refs:
                    continue
                visited_refs.add(ref_key)

                references.append(
                    SymbolLocation(
                        file_path=str(ref_path),
                        range=lsp_range_to_range(ref.range),
                    )
                )

                if len(references) >= max_refs:
                    truncated = True
                    break

                if depth + 1 < max_depth:
                    queue.append(
                        (ref_path, ref.range.start.line, ref.range.start.character, depth + 1)
                    )

        return references, truncated

    # -- Context --

    async def get_context(self, diagnostic: Diagnostic) -> DiagnosticContext:
        await self._ensure_started()
        assert self._client is not None

        file_path = Path(diagnostic.file_path)
        await self.open_file(file_path)

        start_line = diagnostic.range.start.line
        start_char = diagnostic.range.start.character

        definition = await self._resolve_definition(file_path, start_line, start_char)

        refs, truncated = await self._gather_recursive_references(
            file_path, start_line, start_char, self._reference_depth, self._reference_limit
        )

        hover_info: str | None = None
        try:
            hover = await self._client.get_hover(file_path, start_line, start_char)
            if hover is not None:
                contents = hover.contents
                if isinstance(contents, str):
                    hover_info = contents
                elif isinstance(contents, lsp.MarkupContent):
                    hover_info = contents.value
                elif isinstance(contents, list):
                    parts = []
                    for item in contents:
                        if isinstance(item, str):
                            parts.append(item)
                        elif hasattr(item, "value"):
                            parts.append(item.value)
                    hover_info = "\n".join(parts) if parts else None
        except Exception:
            logger.debug("Error getting hover info", exc_info=True)

        code_actions = await self.get_code_actions_for_diagnostic(diagnostic)

        all_diags = self._diagnostics.get(file_path, [])
        related = [d for d in all_diags if d != diagnostic][:5]

        return DiagnosticContext(
            diagnostic=diagnostic,
            definition=definition,
            references=refs,
            hover_info=hover_info,
            related_diagnostics=related,
            code_actions=code_actions,
            reference_depth=self._reference_depth,
            reference_limit=self._reference_limit,
            references_truncated=truncated,
        )

    # -- Signature change impact --

    async def analyze_signature_change_impact(
        self, file_path: Path, line: int, character: int
    ) -> SignatureChangeImpact:
        await self._ensure_started()
        assert self._client is not None
        await self.open_file(file_path)

        symbol_name = ""
        try:
            hover = await self._client.get_hover(file_path, line, character)
            if hover is not None:
                text = ""
                if isinstance(hover.contents, str):
                    text = hover.contents
                elif isinstance(hover.contents, lsp.MarkupContent):
                    text = hover.contents.value
                match = re.search(r"(?:def|class|function)\s+(\w+)", text)
                if match:
                    symbol_name = match.group(1)
        except Exception:
            logger.debug("Error extracting symbol name", exc_info=True)

        try:
            lsp_refs = await self._client.get_references(
                file_path, line, character, include_declaration=False
            )
        except Exception:
            logger.debug("Error getting references for impact analysis", exc_info=True)
            lsp_refs = []

        usages: list[SymbolLocation] = []
        affected_files: set[str] = set()
        for ref in lsp_refs:
            ref_path = str(uri_to_path(ref.uri))
            affected_files.add(ref_path)
            usages.append(
                SymbolLocation(file_path=ref_path, range=lsp_range_to_range(ref.range))
            )

        return SignatureChangeImpact(
            symbol_name=symbol_name,
            symbol_location=SymbolLocation(
                file_path=str(file_path),
                range=Range(
                    start=Position(line=line, character=character),
                    end=Position(line=line, character=character),
                ),
            ),
            usages=usages,
            total_usages=len(usages),
            affected_files=sorted(affected_files),
        )
