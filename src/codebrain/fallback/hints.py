"""Remediation hints for missing or misconfigured language servers."""

from __future__ import annotations

_HINTS: dict[tuple[str, str], list[str]] = {
    ("python", "server_missing"): [
        "Install pyright language server: pip install pyright",
        "Or: npm install -g pyright",
    ],
    ("python", "venv_missing"): [
        "Create a virtual environment: python -m venv .venv",
        "Then activate and install deps: source .venv/bin/activate && pip install -e .",
    ],
    ("python", "config_missing"): [
        "Create pyrightconfig.json for custom settings",
        "Or add [tool.pyright] section to pyproject.toml",
    ],
    ("typescript", "server_missing"): [
        "Install typescript-language-server: npm install -g typescript-language-server typescript",
    ],
    ("typescript", "config_missing"): [
        "Create tsconfig.json: npx tsc --init",
    ],
    ("go", "server_missing"): [
        "Install gopls: go install golang.org/x/tools/gopls@latest",
    ],
    ("go", "modules_missing"): [
        "Download Go module dependencies: go mod download",
    ],
    ("cpp", "server_missing"): [
        "Install clangd: apt install clangd (Debian/Ubuntu) or brew install llvm (macOS)",
    ],
    ("cpp", "config_missing"): [
        "Generate compile_commands.json: cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON .",
    ],
}


def get_hints(language: str, issue_type: str) -> list[str]:
    """Return remediation hints for a given language and issue type."""
    return _HINTS.get((language, issue_type), [])
