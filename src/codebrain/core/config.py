"""Configuration models for validation behavior."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codebrain.core.models import DiagnosticSeverity


class ValidationAction(StrEnum):
    """What to do when a diagnostic of a given severity is found."""

    BLOCK = "block"
    WARN = "warn"
    IGNORE = "ignore"


class LanguageConfig(BaseModel):
    """Base configuration for a language's validation behavior."""

    enabled: bool = True
    lsp_command: list[str] | None = None
    use_fallback: bool = False
    error_action: ValidationAction = ValidationAction.BLOCK
    warning_action: ValidationAction = ValidationAction.WARN
    info_action: ValidationAction = ValidationAction.IGNORE
    hint_action: ValidationAction = ValidationAction.IGNORE

    def get_action(self, severity: DiagnosticSeverity) -> ValidationAction:
        mapping = {
            DiagnosticSeverity.ERROR: self.error_action,
            DiagnosticSeverity.WARNING: self.warning_action,
            DiagnosticSeverity.INFORMATION: self.info_action,
            DiagnosticSeverity.HINT: self.hint_action,
        }
        return mapping.get(severity, ValidationAction.IGNORE)


class PythonConfig(LanguageConfig):
    lsp_command: list[str] | None = Field(
        default_factory=lambda: ["pyright-langserver", "--stdio"]
    )
    pyrightconfig_path: Path | None = None


class CppConfig(LanguageConfig):
    lsp_command: list[str] | None = Field(
        default_factory=lambda: ["clangd", "--background-index"]
    )
    compile_commands_path: Path | None = None


class TypeScriptConfig(LanguageConfig):
    lsp_command: list[str] | None = Field(
        default_factory=lambda: ["typescript-language-server", "--stdio"]
    )
    tsconfig_path: Path | None = None


class GoConfig(LanguageConfig):
    lsp_command: list[str] | None = Field(default_factory=lambda: ["gopls", "serve"])


class ValidationConfig(BaseModel):
    """Master configuration for multi-language validation."""

    workspace_root: Path
    python: PythonConfig = Field(default_factory=PythonConfig)
    cpp: CppConfig = Field(default_factory=CppConfig)
    typescript: TypeScriptConfig = Field(default_factory=TypeScriptConfig)
    go: GoConfig = Field(default_factory=GoConfig)
    parallel_file_limit: int = 10
    diagnostic_timeout: float = 30.0

    def get_language_config(self, extension: str) -> LanguageConfig | None:
        mapping: dict[str, LanguageConfig] = {
            ".py": self.python,
            ".pyi": self.python,
            ".c": self.cpp,
            ".cc": self.cpp,
            ".cpp": self.cpp,
            ".cxx": self.cpp,
            ".h": self.cpp,
            ".hpp": self.cpp,
            ".hxx": self.cpp,
            ".ts": self.typescript,
            ".tsx": self.typescript,
            ".js": self.typescript,
            ".jsx": self.typescript,
            ".go": self.go,
        }
        return mapping.get(extension)

    @classmethod
    def from_dict(cls, data: dict[str, Any], workspace_root: Path) -> ValidationConfig:
        raise NotImplementedError

    @classmethod
    def default(cls, workspace_root: Path) -> ValidationConfig:
        return cls(workspace_root=workspace_root)
