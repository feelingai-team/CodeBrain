"""Core data models for diagnostics, positions, and code context."""

from __future__ import annotations

from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field


class DiagnosticSeverity(IntEnum):
    """Diagnostic severity levels matching LSP specification values."""

    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4


class Position(BaseModel):
    """A position in a text document (0-indexed)."""

    line: int
    character: int

    def __str__(self) -> str:
        return f"{self.line + 1}:{self.character + 1}"


class Range(BaseModel):
    """A range in a text document."""

    start: Position
    end: Position

    def __str__(self) -> str:
        return f"{self.start}-{self.end}"


class RelatedInformation(BaseModel):
    """Additional location and message related to a diagnostic."""

    file_path: str
    range: Range
    message: str


class Diagnostic(BaseModel):
    """A diagnostic (error, warning, etc.) reported by a language server."""

    file_path: str
    range: Range
    severity: DiagnosticSeverity
    message: str
    source: str | None = None
    code: str | int | None = None
    code_description_url: str | None = None
    related_information: list[RelatedInformation] = Field(default_factory=list)
    data: Any = None

    def __str__(self) -> str:
        severity_name = self.severity.name
        code_str = f" [{self.code}]" if self.code else ""
        source_str = f" ({self.source})" if self.source else ""
        return (
            f"{self.file_path}:{self.range.start}: "
            f"{severity_name}{code_str}{source_str}: {self.message}"
        )


class SymbolKind(IntEnum):
    """Symbol kinds matching LSP specification."""

    FILE = 1
    MODULE = 2
    NAMESPACE = 3
    PACKAGE = 4
    CLASS = 5
    METHOD = 6
    PROPERTY = 7
    FIELD = 8
    CONSTRUCTOR = 9
    ENUM = 10
    INTERFACE = 11
    FUNCTION = 12
    VARIABLE = 13
    CONSTANT = 14
    STRING = 15
    NUMBER = 16
    BOOLEAN = 17
    ARRAY = 18
    OBJECT = 19
    KEY = 20
    NULL = 21
    ENUM_MEMBER = 22
    STRUCT = 23
    EVENT = 24
    OPERATOR = 25
    TYPE_PARAMETER = 26


class SymbolLocation(BaseModel):
    """A symbol's location in the codebase."""

    file_path: str
    range: Range
    name: str | None = None


class CodeActionSuggestion(BaseModel):
    """A suggested code action (quick fix, refactor, etc.)."""

    title: str
    kind: str | None = None
    is_preferred: bool = False


class SignatureChangeImpact(BaseModel):
    """Impact analysis for a symbol's signature change."""

    symbol_name: str
    symbol_location: SymbolLocation
    usages: list[SymbolLocation] = Field(default_factory=list)
    total_usages: int = 0
    affected_files: list[str] = Field(default_factory=list)


class DiagnosticContext(BaseModel):
    """Rich context gathered for a diagnostic to aid in fixing it."""

    diagnostic: Diagnostic
    definition: SymbolLocation | None = None
    references: list[SymbolLocation] = Field(default_factory=list)
    hover_info: str | None = None
    related_diagnostics: list[Diagnostic] = Field(default_factory=list)
    code_actions: list[CodeActionSuggestion] = Field(default_factory=list)
    reference_depth: int = 1
    reference_limit: int = 0
    references_truncated: bool = False


class DocumentSymbol(BaseModel):
    """A symbol in a document (hierarchical)."""

    name: str
    kind: SymbolKind
    range: Range
    selection_range: Range
    detail: str | None = None
    children: list[DocumentSymbol] = Field(default_factory=list)


class CallHierarchyItem(BaseModel):
    """An item in a call hierarchy."""

    name: str
    kind: SymbolKind
    file_path: str
    range: Range
    selection_range: Range
    detail: str | None = None


class CallHierarchyCall(BaseModel):
    """A call relationship in the hierarchy."""

    item: CallHierarchyItem
    from_ranges: list[Range] = Field(default_factory=list)


class RenameEdit(BaseModel):
    """A text edit for a rename operation."""

    file_path: str
    range: Range
    new_text: str


class RenameResult(BaseModel):
    """Result of a rename operation."""

    edits: list[RenameEdit] = Field(default_factory=list)
    files_affected: int = 0


class WorkspaceInfo(BaseModel):
    """Configuration and state for a single workspace root."""

    root_path: str
    name: str | None = None
    languages: list[str] | None = None
    lsp_overrides: dict[str, list[str]] = Field(default_factory=dict)
