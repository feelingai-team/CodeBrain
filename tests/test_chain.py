"""Tests for FallbackChain reporter wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from codebrain.core.models import Diagnostic, DiagnosticContext, DiagnosticSeverity, Position, Range
from codebrain.fallback.chain import FallbackChain


def _make_diagnostic(msg: str = "test error") -> Diagnostic:
    return Diagnostic(
        file_path="/test.py",
        range=Range(
            start=Position(line=0, character=0),
            end=Position(line=0, character=5),
        ),
        severity=DiagnosticSeverity.ERROR,
        message=msg,
        source="test",
    )


@pytest.fixture
def primary() -> AsyncMock:
    mock = AsyncMock()
    mock.name = "pyright"
    mock.supported_extensions = {".py"}
    mock.is_running = False
    return mock


@pytest.fixture
def fallback() -> AsyncMock:
    mock = AsyncMock()
    mock.name = "pyright-cli"
    mock.supported_extensions = {".py"}
    return mock


class TestFallbackChainStart:
    @pytest.mark.asyncio
    async def test_primary_succeeds(self, primary: AsyncMock, fallback: AsyncMock) -> None:
        chain = FallbackChain(primary=primary, fallback=fallback)
        await chain.start()
        assert chain.status == "active"
        primary.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_primary_fails_with_fallback(
        self, primary: AsyncMock, fallback: AsyncMock
    ) -> None:
        primary.start.side_effect = FileNotFoundError("pyright not found")
        chain = FallbackChain(primary=primary, fallback=fallback)
        await chain.start()
        assert chain.status == "degraded"

    @pytest.mark.asyncio
    async def test_primary_fails_no_fallback(self, primary: AsyncMock) -> None:
        primary.start.side_effect = FileNotFoundError("pyright not found")
        chain = FallbackChain(primary=primary, fallback=None)
        await chain.start()
        assert chain.status == "unavailable"


class TestFallbackChainDiagnostics:
    @pytest.mark.asyncio
    async def test_active_returns_primary(self, primary: AsyncMock, fallback: AsyncMock) -> None:
        diag = _make_diagnostic()
        primary.get_diagnostics.return_value = [diag]

        chain = FallbackChain(primary=primary, fallback=fallback)
        chain.status = "active"

        result = await chain.get_diagnostics(Path("/test.py"))
        assert result == [diag]
        primary.get_diagnostics.assert_called_once()
        fallback.get_diagnostics.assert_not_called()

    @pytest.mark.asyncio
    async def test_degraded_returns_fallback(self, primary: AsyncMock, fallback: AsyncMock) -> None:
        diag = _make_diagnostic()
        fallback.get_diagnostics.return_value = [diag]

        chain = FallbackChain(primary=primary, fallback=fallback)
        chain.status = "degraded"

        result = await chain.get_diagnostics(Path("/test.py"))
        assert result == [diag]
        fallback.get_diagnostics.assert_called_once()
        primary.get_diagnostics.assert_not_called()

    @pytest.mark.asyncio
    async def test_active_fails_falls_to_degraded(
        self, primary: AsyncMock, fallback: AsyncMock
    ) -> None:
        diag = _make_diagnostic()
        primary.get_diagnostics.side_effect = ConnectionError("server died")
        fallback.get_diagnostics.return_value = [diag]

        chain = FallbackChain(primary=primary, fallback=fallback)
        chain.status = "active"

        result = await chain.get_diagnostics(Path("/test.py"))
        assert result == [diag]
        assert chain.status == "degraded"

    @pytest.mark.asyncio
    async def test_unavailable_returns_empty(self, primary: AsyncMock) -> None:
        chain = FallbackChain(primary=primary, fallback=None)
        chain.status = "unavailable"

        result = await chain.get_diagnostics(Path("/test.py"))
        assert result == []


class TestFallbackChainContext:
    @pytest.mark.asyncio
    async def test_active_returns_context(self, primary: AsyncMock, fallback: AsyncMock) -> None:
        diag = _make_diagnostic()
        ctx = DiagnosticContext(diagnostic=diag)
        primary.get_context.return_value = ctx

        chain = FallbackChain(primary=primary, fallback=fallback)
        chain.status = "active"

        result = await chain.get_context(diag)
        assert result == ctx

    @pytest.mark.asyncio
    async def test_degraded_returns_basic_context(
        self, primary: AsyncMock, fallback: AsyncMock
    ) -> None:
        diag = _make_diagnostic()
        chain = FallbackChain(primary=primary, fallback=fallback)
        chain.status = "degraded"

        result = await chain.get_context(diag)
        assert result.diagnostic == diag
        assert result.definition is None
