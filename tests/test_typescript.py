"""Tests for TypeScript (typescript-language-server) language support."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.config import TypeScriptConfig, ValidationConfig
from codebrain.core.models import NodeEnv
from codebrain.lsp.servers.typescript import TypeScriptReporter
from codebrain.search.parser import EXTENSION_TO_LANGUAGE, LANGUAGE_MAP


class TestTypeScriptReporter:
    """Tests for the TypeScriptReporter class."""

    def test_name(self, tmp_path: Path) -> None:
        reporter = TypeScriptReporter(tmp_path)
        assert reporter.name == "typescript-langserver"

    def test_supported_extensions(self, tmp_path: Path) -> None:
        reporter = TypeScriptReporter(tmp_path)
        assert reporter.supported_extensions == {".ts", ".tsx", ".js", ".jsx"}

    def test_default_command(self, tmp_path: Path) -> None:
        reporter = TypeScriptReporter(tmp_path)
        assert reporter._server_command == ["typescript-language-server", "--stdio"]

    def test_custom_command(self, tmp_path: Path) -> None:
        reporter = TypeScriptReporter(
            tmp_path, server_command=["typescript-language-server", "--log-level=4", "--stdio"]
        )
        assert reporter._server_command == [
            "typescript-language-server", "--log-level=4", "--stdio"
        ]


class TestTypeScriptLanguageId:
    """Tests for per-extension LSP languageId mapping."""

    def test_language_id_ts(self, tmp_path: Path) -> None:
        reporter = TypeScriptReporter(tmp_path)
        assert reporter._language_id_for_file(Path("index.ts")) == "typescript"

    def test_language_id_tsx(self, tmp_path: Path) -> None:
        reporter = TypeScriptReporter(tmp_path)
        assert reporter._language_id_for_file(Path("app.tsx")) == "typescriptreact"

    def test_language_id_js(self, tmp_path: Path) -> None:
        reporter = TypeScriptReporter(tmp_path)
        assert reporter._language_id_for_file(Path("index.js")) == "javascript"

    def test_language_id_jsx(self, tmp_path: Path) -> None:
        reporter = TypeScriptReporter(tmp_path)
        assert reporter._language_id_for_file(Path("app.jsx")) == "javascriptreact"

    def test_language_id_unknown_extension_falls_back_to_default(
        self, tmp_path: Path
    ) -> None:
        reporter = TypeScriptReporter(tmp_path)
        # Unknown extensions fall back to the reporter's base language_id
        assert reporter._language_id_for_file(Path("file.mts")) == "typescript"


class TestTypeScriptInitializationOptions:
    """Tests for initialization options generation."""

    def test_no_node_env_returns_none(self, tmp_path: Path) -> None:
        reporter = TypeScriptReporter(tmp_path)
        result = reporter._build_initialization_options(tmp_path)
        assert result is None

    def test_node_env_without_tsconfig_returns_none(self, tmp_path: Path) -> None:
        node_env = NodeEnv(tsconfig=None)
        reporter = TypeScriptReporter(tmp_path, node_env=node_env)
        result = reporter._build_initialization_options(tmp_path)
        assert result is None

    def test_node_env_with_tsconfig_returns_options(self, tmp_path: Path) -> None:
        tsconfig = tmp_path / "tsconfig.json"
        node_env = NodeEnv(tsconfig=tsconfig)
        reporter = TypeScriptReporter(tmp_path, node_env=node_env)
        result = reporter._build_initialization_options(tmp_path)
        assert result is not None
        assert result["preferences"]["importModuleSpecifierPreference"] == "relative"
        assert result["tsserver"]["path"] == str(tmp_path)

    def test_tsconfig_in_subdirectory(self, tmp_path: Path) -> None:
        subdir = tmp_path / "packages" / "web"
        tsconfig = subdir / "tsconfig.json"
        node_env = NodeEnv(tsconfig=tsconfig)
        reporter = TypeScriptReporter(tmp_path, node_env=node_env)
        result = reporter._build_initialization_options(tmp_path)
        assert result is not None
        assert result["tsserver"]["path"] == str(subdir)


class TestTypeScriptConfig:
    """Tests for the TypeScriptConfig configuration."""

    def test_defaults(self) -> None:
        config = TypeScriptConfig()
        assert config.enabled is True
        assert config.lsp_command == ["typescript-language-server", "--stdio"]

    def test_validation_config_has_typescript(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        assert isinstance(config.typescript, TypeScriptConfig)

    def test_extension_mapping_ts(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        lang_config = config.get_language_config(".ts")
        assert lang_config is not None
        assert isinstance(lang_config, TypeScriptConfig)

    def test_extension_mapping_tsx(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        lang_config = config.get_language_config(".tsx")
        assert lang_config is not None
        assert isinstance(lang_config, TypeScriptConfig)

    def test_extension_mapping_js(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        lang_config = config.get_language_config(".js")
        assert lang_config is not None
        assert isinstance(lang_config, TypeScriptConfig)

    def test_extension_mapping_jsx(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        lang_config = config.get_language_config(".jsx")
        assert lang_config is not None
        assert isinstance(lang_config, TypeScriptConfig)

    def test_extension_mapping_non_typescript(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        assert config.get_language_config(".rs") is None


class TestTypeScriptTreeSitter:
    """Tests for TypeScript tree-sitter integration."""

    def test_language_map_has_typescript(self) -> None:
        assert "typescript" in LANGUAGE_MAP
        assert LANGUAGE_MAP["typescript"] == "tree_sitter_typescript"

    def test_extension_to_language_ts(self) -> None:
        assert ".ts" in EXTENSION_TO_LANGUAGE
        assert EXTENSION_TO_LANGUAGE[".ts"] == "typescript"

    def test_extension_to_language_tsx(self) -> None:
        assert ".tsx" in EXTENSION_TO_LANGUAGE
        assert EXTENSION_TO_LANGUAGE[".tsx"] == "typescript"

    def test_extension_to_language_js(self) -> None:
        assert ".js" in EXTENSION_TO_LANGUAGE
        assert EXTENSION_TO_LANGUAGE[".js"] == "javascript"

    def test_extension_to_language_jsx(self) -> None:
        assert ".jsx" in EXTENSION_TO_LANGUAGE
        assert EXTENSION_TO_LANGUAGE[".jsx"] == "javascript"


class TestTypeScriptFactory:
    """Tests for TypeScript registration in the factory."""

    def test_factory_has_typescript(self) -> None:
        from codebrain.lsp.factory import _LANGUAGE_FACTORIES

        assert "typescript" in _LANGUAGE_FACTORIES
        assert _LANGUAGE_FACTORIES["typescript"] is TypeScriptReporter

    def test_fallback_factory_has_typescript(self) -> None:
        from codebrain.fallback.tsc_cli import TscCLIReporter
        from codebrain.lsp.factory import _FALLBACK_FACTORIES

        assert "typescript" in _FALLBACK_FACTORIES
        assert _FALLBACK_FACTORIES["typescript"] is TscCLIReporter

    def test_build_multi_reporter_includes_typescript(self, tmp_path: Path) -> None:
        from codebrain.lsp.factory import build_multi_reporter

        reporter = build_multi_reporter(tmp_path, languages=["typescript"])
        ts_reporter = reporter.get_reporter_for_file(tmp_path / "index.ts")
        assert ts_reporter is not None
        assert ts_reporter.name == "typescript-langserver"

    def test_build_multi_reporter_handles_all_ts_extensions(self, tmp_path: Path) -> None:
        from codebrain.lsp.factory import build_multi_reporter

        reporter = build_multi_reporter(tmp_path, languages=["typescript"])
        for ext in (".ts", ".tsx", ".js", ".jsx"):
            file_reporter = reporter.get_reporter_for_file(tmp_path / f"file{ext}")
            assert file_reporter is not None, f"No reporter found for {ext}"
            assert file_reporter.name == "typescript-langserver"
