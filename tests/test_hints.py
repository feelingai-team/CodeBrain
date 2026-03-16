"""Tests for remediation hints."""

from __future__ import annotations

from codebrain.fallback.hints import get_hints


class TestGetHints:
    def test_python_missing_server(self) -> None:
        hints = get_hints("python", "server_missing")
        assert any("pyright" in h.lower() for h in hints)
        assert any("pip install" in h or "npm install" in h for h in hints)

    def test_python_missing_venv(self) -> None:
        hints = get_hints("python", "venv_missing")
        assert any("venv" in h for h in hints)

    def test_go_missing_server(self) -> None:
        hints = get_hints("go", "server_missing")
        assert any("gopls" in h for h in hints)

    def test_typescript_missing_server(self) -> None:
        hints = get_hints("typescript", "server_missing")
        assert any("typescript-language-server" in h for h in hints)

    def test_cpp_missing_server(self) -> None:
        hints = get_hints("cpp", "server_missing")
        assert any("clangd" in h for h in hints)

    def test_unknown_language(self) -> None:
        hints = get_hints("rust", "server_missing")
        assert hints == []

    def test_unknown_issue(self) -> None:
        hints = get_hints("python", "unknown_issue_type")
        assert hints == []
