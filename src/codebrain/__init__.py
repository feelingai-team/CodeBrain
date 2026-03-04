"""CodeBrain: LSP-based code validation and structural syntax search."""

from codebrain.core.config import ValidationAction, ValidationConfig
from codebrain.core.interfaces import (
    ContextAwareDiagnosticReporter,
    ContextProvider,
    DiagnosticReporter,
)
from codebrain.core.models import (
    CodeActionSuggestion,
    Diagnostic,
    DiagnosticContext,
    DiagnosticSeverity,
    Position,
    Range,
    SignatureChangeImpact,
    SymbolLocation,
)

__all__ = [
    "CodeActionSuggestion",
    "ContextAwareDiagnosticReporter",
    "ContextProvider",
    "Diagnostic",
    "DiagnosticContext",
    "DiagnosticReporter",
    "DiagnosticSeverity",
    "Position",
    "Range",
    "SignatureChangeImpact",
    "SymbolLocation",
    "ValidationAction",
    "ValidationConfig",
]
