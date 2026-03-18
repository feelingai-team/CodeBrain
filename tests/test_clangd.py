"""Tests for C/C++ (clangd) language support."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.config import CppConfig, ValidationConfig
from codebrain.core.models import CppEnv
from codebrain.lsp.servers.clangd import ClangdReporter
from codebrain.search.parser import EXTENSION_TO_LANGUAGE, LANGUAGE_MAP


class TestClangdReporter:
    """Tests for the ClangdReporter class."""

    def test_name(self, tmp_path: Path) -> None:
        reporter = ClangdReporter(tmp_path)
        assert reporter.name == "clangd"

    def test_supported_extensions(self, tmp_path: Path) -> None:
        reporter = ClangdReporter(tmp_path)
        assert reporter.supported_extensions == {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hxx"}

    def test_default_command(self, tmp_path: Path) -> None:
        reporter = ClangdReporter(tmp_path)
        assert reporter._server_command == ["clangd", "--background-index"]

    def test_custom_command(self, tmp_path: Path) -> None:
        reporter = ClangdReporter(tmp_path, server_command=["clangd", "--clang-tidy"])
        assert reporter._server_command == ["clangd", "--clang-tidy"]

    def test_no_env_no_extra_args(self, tmp_path: Path) -> None:
        """Without CppEnv, command stays at plain defaults."""
        reporter = ClangdReporter(tmp_path, cpp_env=None)
        assert reporter._server_command == ["clangd", "--background-index"]

    def test_cpp_env_without_compile_commands_no_extra_args(self, tmp_path: Path) -> None:
        """CppEnv with no compile_commands path should not inject --compile-commands-dir."""
        cpp_env = CppEnv(compile_commands=None)
        reporter = ClangdReporter(tmp_path, cpp_env=cpp_env)
        assert reporter._server_command == ["clangd", "--background-index"]
        assert not any(arg.startswith("--compile-commands-dir") for arg in reporter._server_command)

    def test_cpp_env_with_compile_commands_injects_dir(self, tmp_path: Path) -> None:
        """compile_commands.json path causes --compile-commands-dir to be injected."""
        cc_json = tmp_path / "build" / "compile_commands.json"
        cpp_env = CppEnv(compile_commands=cc_json)
        reporter = ClangdReporter(tmp_path, cpp_env=cpp_env)
        expected_flag = f"--compile-commands-dir={tmp_path / 'build'}"
        assert expected_flag in reporter._server_command

    def test_compile_commands_dir_not_duplicated(self, tmp_path: Path) -> None:
        """If the flag is already in a custom command, it must not be appended again."""
        cc_json = tmp_path / "build" / "compile_commands.json"
        cc_dir = str(cc_json.parent)
        custom_cmd = ["clangd", f"--compile-commands-dir={cc_dir}"]
        cpp_env = CppEnv(compile_commands=cc_json)
        reporter = ClangdReporter(tmp_path, server_command=custom_cmd, cpp_env=cpp_env)
        # Count occurrences — must appear exactly once
        occurrences = sum(
            1 for arg in reporter._server_command
            if arg.startswith("--compile-commands-dir=")
        )
        assert occurrences == 1


class TestCppConfig:
    """Tests for the CppConfig configuration."""

    def test_defaults(self) -> None:
        config = CppConfig()
        assert config.enabled is True
        assert config.lsp_command == ["clangd", "--background-index"]

    def test_validation_config_has_cpp(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        assert isinstance(config.cpp, CppConfig)

    def test_extension_mapping_c(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        lang_config = config.get_language_config(".c")
        assert lang_config is not None
        assert isinstance(lang_config, CppConfig)

    def test_extension_mapping_cpp(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        lang_config = config.get_language_config(".cpp")
        assert lang_config is not None
        assert isinstance(lang_config, CppConfig)

    def test_extension_mapping_h(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        lang_config = config.get_language_config(".h")
        assert lang_config is not None
        assert isinstance(lang_config, CppConfig)

    def test_extension_mapping_hpp(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        lang_config = config.get_language_config(".hpp")
        assert lang_config is not None
        assert isinstance(lang_config, CppConfig)

    def test_extension_mapping_cc(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        lang_config = config.get_language_config(".cc")
        assert lang_config is not None
        assert isinstance(lang_config, CppConfig)

    def test_extension_mapping_cxx(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        lang_config = config.get_language_config(".cxx")
        assert lang_config is not None
        assert isinstance(lang_config, CppConfig)

    def test_extension_mapping_hxx(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        lang_config = config.get_language_config(".hxx")
        assert lang_config is not None
        assert isinstance(lang_config, CppConfig)

    def test_extension_mapping_non_cpp(self, tmp_path: Path) -> None:
        config = ValidationConfig(workspace_root=tmp_path)
        assert config.get_language_config(".rs") is None


class TestCppTreeSitter:
    """Tests for C/C++ tree-sitter integration."""

    def test_language_map_has_c(self) -> None:
        assert "c" in LANGUAGE_MAP
        assert LANGUAGE_MAP["c"] == "tree_sitter_c"

    def test_language_map_has_cpp(self) -> None:
        assert "cpp" in LANGUAGE_MAP
        assert LANGUAGE_MAP["cpp"] == "tree_sitter_cpp"

    def test_extension_to_language_c(self) -> None:
        assert ".c" in EXTENSION_TO_LANGUAGE
        assert EXTENSION_TO_LANGUAGE[".c"] == "c"

    def test_extension_to_language_h(self) -> None:
        assert ".h" in EXTENSION_TO_LANGUAGE
        assert EXTENSION_TO_LANGUAGE[".h"] == "c"

    def test_extension_to_language_cc(self) -> None:
        assert ".cc" in EXTENSION_TO_LANGUAGE
        assert EXTENSION_TO_LANGUAGE[".cc"] == "cpp"

    def test_extension_to_language_cpp(self) -> None:
        assert ".cpp" in EXTENSION_TO_LANGUAGE
        assert EXTENSION_TO_LANGUAGE[".cpp"] == "cpp"

    def test_extension_to_language_cxx(self) -> None:
        assert ".cxx" in EXTENSION_TO_LANGUAGE
        assert EXTENSION_TO_LANGUAGE[".cxx"] == "cpp"

    def test_extension_to_language_hpp(self) -> None:
        assert ".hpp" in EXTENSION_TO_LANGUAGE
        assert EXTENSION_TO_LANGUAGE[".hpp"] == "cpp"

    def test_extension_to_language_hxx(self) -> None:
        assert ".hxx" in EXTENSION_TO_LANGUAGE
        assert EXTENSION_TO_LANGUAGE[".hxx"] == "cpp"


class TestCppFactory:
    """Tests for C/C++ registration in the factory."""

    def test_factory_has_cpp(self) -> None:
        from codebrain.lsp.factory import _LANGUAGE_FACTORIES

        assert "cpp" in _LANGUAGE_FACTORIES
        assert _LANGUAGE_FACTORIES["cpp"] is ClangdReporter

    def test_no_fallback_factory_for_cpp(self) -> None:
        """C/C++ has no CLI fallback — _FALLBACK_FACTORIES must not contain 'cpp'."""
        from codebrain.lsp.factory import _FALLBACK_FACTORIES

        assert "cpp" not in _FALLBACK_FACTORIES

    def test_build_multi_reporter_includes_cpp_for_c(self, tmp_path: Path) -> None:
        from codebrain.lsp.factory import build_multi_reporter

        reporter = build_multi_reporter(tmp_path, languages=["cpp"])
        c_reporter = reporter.get_reporter_for_file(tmp_path / "main.c")
        assert c_reporter is not None
        assert c_reporter.name == "clangd"

    def test_build_multi_reporter_includes_cpp_for_cpp(self, tmp_path: Path) -> None:
        from codebrain.lsp.factory import build_multi_reporter

        reporter = build_multi_reporter(tmp_path, languages=["cpp"])
        cpp_reporter = reporter.get_reporter_for_file(tmp_path / "main.cpp")
        assert cpp_reporter is not None
        assert cpp_reporter.name == "clangd"

    def test_build_multi_reporter_handles_all_cpp_extensions(self, tmp_path: Path) -> None:
        from codebrain.lsp.factory import build_multi_reporter

        reporter = build_multi_reporter(tmp_path, languages=["cpp"])
        for ext in (".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hxx"):
            file_reporter = reporter.get_reporter_for_file(tmp_path / f"file{ext}")
            assert file_reporter is not None, f"No reporter found for {ext}"
            assert file_reporter.name == "clangd"
