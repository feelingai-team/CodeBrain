"""Tests for Go (gopls) language support."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.config import GoConfig, ValidationConfig
from codebrain.lsp.servers.gopls import GoplsReporter
from codebrain.search.parser import EXTENSION_TO_LANGUAGE, LANGUAGE_MAP


class TestGoplsReporter:
    """Tests for the GoplsReporter class."""

    def test_name(self, tmp_path: Path) -> None:
        reporter = GoplsReporter(tmp_path)
        assert reporter.name == "gopls"

    def test_supported_extensions(self, tmp_path: Path) -> None:
        reporter = GoplsReporter(tmp_path)
        assert reporter.supported_extensions == {".go"}

    def test_default_command(self, tmp_path: Path) -> None:
        reporter = GoplsReporter(tmp_path)
        assert reporter._server_command == ["gopls", "serve"]

    def test_custom_command(self, tmp_path: Path) -> None:
        reporter = GoplsReporter(tmp_path, server_command=["gopls", "-remote=auto"])
        assert reporter._server_command == ["gopls", "-remote=auto"]


class TestGoConfig:
    """Tests for the GoConfig configuration."""

    def test_defaults(self) -> None:
        config = GoConfig()
        assert config.enabled is True
        assert config.lsp_command == ["gopls", "serve"]

    def test_validation_config_has_go(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        assert isinstance(config.go, GoConfig)

    def test_extension_mapping(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        lang_config = config.get_language_config(".go")
        assert lang_config is not None
        assert isinstance(lang_config, GoConfig)

    def test_extension_mapping_non_go(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        assert config.get_language_config(".rs") is None


class TestGoTreeSitter:
    """Tests for Go tree-sitter integration."""

    def test_language_map_has_go(self) -> None:
        assert "go" in LANGUAGE_MAP
        assert LANGUAGE_MAP["go"] == "tree_sitter_go"

    def test_extension_to_language_has_go(self) -> None:
        assert ".go" in EXTENSION_TO_LANGUAGE
        assert EXTENSION_TO_LANGUAGE[".go"] == "go"


class TestGoFactory:
    """Tests for Go registration in the factory."""

    def test_factory_has_go(self) -> None:
        from codebrain.lsp.factory import _LANGUAGE_FACTORIES

        assert "go" in _LANGUAGE_FACTORIES
        assert _LANGUAGE_FACTORIES["go"] is GoplsReporter

    def test_build_multi_reporter_includes_go(self, tmp_path: Path) -> None:
        from codebrain.lsp.factory import build_multi_reporter

        reporter = build_multi_reporter(tmp_path, languages=["go"])
        # Should have one reporter registered for .go
        go_reporter = reporter.get_reporter_for_file(tmp_path / "main.go")
        assert go_reporter is not None
        assert go_reporter.name == "gopls"
