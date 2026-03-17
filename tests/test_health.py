"""Tests for health hints surfacing and MCP health tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codebrain.mcp.consolidated import _get_health_hints, validate


class TestGetHealthHints:
    def test_no_hints_when_no_reporter(self) -> None:
        ws = MagicMock()
        ws.reporter.get_reporter_for_file.return_value = None
        header, footer = _get_health_hints(ws, "/test.py")
        # No reporter = can't determine status, no hints
        assert header == ""
        assert footer == ""

    def test_unavailable_shows_header_warning(self) -> None:
        ws = MagicMock()
        reporter = MagicMock()
        reporter.status = "unavailable"
        reporter.name = "pyright"
        reporter.hints = ["Install pyright: pip install pyright"]
        ws.reporter.get_reporter_for_file.return_value = reporter
        header, footer = _get_health_hints(ws, "/test.py")
        assert "unavailable" in header.lower()
        assert "pyright" in header
        assert footer == ""

    def test_degraded_shows_footer_note(self) -> None:
        ws = MagicMock()
        reporter = MagicMock()
        reporter.status = "degraded"
        reporter.name = "pyright"
        ws.reporter.get_reporter_for_file.return_value = reporter
        header, footer = _get_health_hints(ws, "/test.py")
        assert header == ""
        assert "fallback" in footer.lower()
        assert "pyright" in footer

    def test_active_no_hints(self) -> None:
        ws = MagicMock()
        reporter = MagicMock()
        reporter.status = "active"
        reporter.name = "pyright"
        ws.reporter.get_reporter_for_file.return_value = reporter
        header, footer = _get_health_hints(ws, "/test.py")
        assert header == ""
        assert footer == ""

    def test_no_status_attr_no_hints(self) -> None:
        """Reporter without .status attr (plain LSPReporter) shows no hints."""
        ws = MagicMock()
        reporter = MagicMock(spec=[])  # No attributes
        reporter.name = "pyright"
        ws.reporter.get_reporter_for_file.return_value = reporter
        header, footer = _get_health_hints(ws, "/test.py")
        assert header == ""
        assert footer == ""


class TestValidateWithHealthHints:
    @pytest.mark.asyncio
    async def test_validate_includes_header_when_unavailable(self) -> None:
        ws = MagicMock()
        ws.info.root_path = "/workspace"
        # Set up the reporter to be unavailable
        reporter = MagicMock()
        reporter.status = "unavailable"
        reporter.name = "pyright"
        reporter.hints = []
        ws.reporter.get_reporter_for_file.return_value = reporter

        with patch(
            "codebrain.skills.contextual_diagnostics.contextual_diagnostics",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await validate(ws, file_path="/workspace/test.py")
            assert "unavailable" in result.lower()

    @pytest.mark.asyncio
    async def test_validate_includes_footer_when_degraded(self) -> None:
        ws = MagicMock()
        ws.info.root_path = "/workspace"
        reporter = MagicMock()
        reporter.status = "degraded"
        reporter.name = "pyright"
        ws.reporter.get_reporter_for_file.return_value = reporter

        with patch(
            "codebrain.skills.contextual_diagnostics.contextual_diagnostics",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await validate(ws, file_path="/workspace/test.py")
            assert "fallback" in result.lower()
