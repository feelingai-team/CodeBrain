"""Tests for file watcher integration with Workspace lifecycle."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codebrain.core.models import WorkspaceInfo
from codebrain.core.workspace import Workspace
from codebrain.search.index import FileWatcher, SymbolIndex


@pytest.fixture
def mock_workspace(tmp_path: Path) -> Workspace:
    """Create a Workspace with mocked reporter and index."""
    info = WorkspaceInfo(root_path=str(tmp_path), name="test")
    reporter = MagicMock()
    reporter.start = AsyncMock()
    reporter.stop = AsyncMock()
    index = MagicMock(spec=SymbolIndex)
    index.build = AsyncMock()
    return Workspace(info=info, reporter=reporter, index=index)


class TestFileWatcherClass:
    """Tests for the FileWatcher class itself."""

    def test_init(self, tmp_path: Path) -> None:
        index = MagicMock(spec=SymbolIndex)
        watcher = FileWatcher(index, tmp_path)
        assert not watcher.is_running

    async def test_start_stop(self, tmp_path: Path) -> None:
        index = MagicMock(spec=SymbolIndex)
        watcher = FileWatcher(index, tmp_path)

        with patch("watchfiles.awatch") as mock_awatch:
            async def empty_awatch(*_args, **kwargs):  # noqa: ANN002, ANN003
                stop_event = kwargs.get("stop_event")
                if stop_event:
                    await stop_event.wait()
                return
                yield  # type: ignore[misc]  # noqa: RET503

            mock_awatch.side_effect = empty_awatch
            await watcher.start()
            assert watcher.is_running

            await watcher.stop()
            assert not watcher.is_running

    async def test_start_idempotent(self, tmp_path: Path) -> None:
        index = MagicMock(spec=SymbolIndex)
        watcher = FileWatcher(index, tmp_path)

        with patch("watchfiles.awatch") as mock_awatch:
            async def empty_awatch(*_args, **kwargs):  # noqa: ANN002, ANN003
                stop_event = kwargs.get("stop_event")
                if stop_event:
                    await stop_event.wait()
                return
                yield  # type: ignore[misc]  # noqa: RET503

            mock_awatch.side_effect = empty_awatch
            await watcher.start()
            await watcher.start()  # Second call should be a no-op
            assert watcher.is_running

            await watcher.stop()

    async def test_stop_when_not_running(self, tmp_path: Path) -> None:
        index = MagicMock(spec=SymbolIndex)
        watcher = FileWatcher(index, tmp_path)
        # Should not raise
        await watcher.stop()
        assert not watcher.is_running


class TestWorkspaceFileWatcher:
    """Tests for file watcher wiring in Workspace lifecycle."""

    async def test_start_creates_watcher(self, mock_workspace: Workspace) -> None:
        with patch("codebrain.core.workspace.FileWatcher") as MockWatcher:
            mock_watcher_instance = MagicMock()
            mock_watcher_instance.start = AsyncMock()
            mock_watcher_instance.stop = AsyncMock()
            MockWatcher.return_value = mock_watcher_instance

            await mock_workspace.start()

            MockWatcher.assert_called_once_with(
                mock_workspace.index,
                Path(mock_workspace.info.root_path),
            )
            mock_watcher_instance.start.assert_awaited_once()
            assert mock_workspace.watcher is mock_watcher_instance

    async def test_stop_stops_watcher(self, mock_workspace: Workspace) -> None:
        with patch("codebrain.core.workspace.FileWatcher") as MockWatcher:
            mock_watcher_instance = MagicMock()
            mock_watcher_instance.start = AsyncMock()
            mock_watcher_instance.stop = AsyncMock()
            MockWatcher.return_value = mock_watcher_instance

            await mock_workspace.start()
            await mock_workspace.stop()

            mock_watcher_instance.stop.assert_awaited_once()
            assert mock_workspace.watcher is None

    async def test_start_graceful_fallback(self, mock_workspace: Workspace) -> None:
        """Workspace starts even if file watcher fails (e.g. watchfiles not installed)."""
        with patch("codebrain.core.workspace.FileWatcher") as MockWatcher:
            mock_watcher_instance = MagicMock()
            mock_watcher_instance.start = AsyncMock(side_effect=ImportError("no watchfiles"))
            MockWatcher.return_value = mock_watcher_instance

            await mock_workspace.start()

            # Workspace should still be running despite watcher failure
            assert mock_workspace._is_running
            assert mock_workspace.watcher is None

    async def test_stop_without_watcher(self, mock_workspace: Workspace) -> None:
        """Workspace stops cleanly even if no watcher was created."""
        with patch("codebrain.core.workspace.FileWatcher") as MockWatcher:
            mock_watcher_instance = MagicMock()
            mock_watcher_instance.start = AsyncMock(side_effect=ImportError)
            MockWatcher.return_value = mock_watcher_instance

            await mock_workspace.start()
            assert mock_workspace.watcher is None

            # Should not raise
            await mock_workspace.stop()
            assert not mock_workspace._is_running
