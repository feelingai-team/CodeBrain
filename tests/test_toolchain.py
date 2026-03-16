"""Tests for per-language toolchain detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from codebrain.core.toolchain import (
    detect_cpp_env,
    detect_go_env,
    detect_node_env,
    detect_python_env,
    detect_toolchain,
    load_codebrain_overrides,
)


class TestDetectPythonEnv:
    def test_venv_directory(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "bin").mkdir()
        (venv / "bin" / "python").write_text("#!/bin/sh\n")
        (venv / "bin" / "python").chmod(0o755)

        env = detect_python_env(tmp_path)
        assert env is not None
        assert env.venv_path == venv
        assert env.python_binary == venv / "bin" / "python"
        assert env.manager == "venv"

    def test_venv_named_venv(self, tmp_path: Path) -> None:
        venv = tmp_path / "venv"
        venv.mkdir()
        (venv / "bin").mkdir()
        (venv / "bin" / "python").write_text("#!/bin/sh\n")
        (venv / "bin" / "python").chmod(0o755)

        env = detect_python_env(tmp_path)
        assert env is not None
        assert env.venv_path == venv

    def test_no_venv(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CONDA_PREFIX", raising=False)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\n")
        env = detect_python_env(tmp_path)
        assert env is None or env.venv_path is None

    def test_pyrightconfig_detected(self, tmp_path: Path) -> None:
        (tmp_path / "pyrightconfig.json").write_text("{}")
        env = detect_python_env(tmp_path)
        assert env is not None
        assert env.pyright_config == tmp_path / "pyrightconfig.json"

    def test_pyright_in_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[project]\nname = 'foo'\n\n[tool.pyright]\nreportMissingImports = true\n"
        )
        env = detect_python_env(tmp_path)
        assert env is not None
        assert env.pyright_config == tmp_path / "pyproject.toml"

    def test_python_version_file(self, tmp_path: Path) -> None:
        (tmp_path / ".python-version").write_text("3.11.5\n")
        env = detect_python_env(tmp_path)
        assert env is not None
        assert env.manager == "pyenv"

    def test_conda_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        conda_path = tmp_path / "conda_env"
        conda_path.mkdir()
        monkeypatch.setenv("CONDA_PREFIX", str(conda_path))
        env = detect_python_env(tmp_path)
        assert env is not None
        assert env.manager == "conda"
        assert env.venv_path == conda_path


class TestDetectNodeEnv:
    def test_npm_project(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "package-lock.json").write_text("{}")
        env = detect_node_env(tmp_path)
        assert env is not None
        assert env.node_modules == tmp_path / "node_modules"
        assert env.package_manager == "npm"

    def test_yarn_project(self, tmp_path: Path) -> None:
        (tmp_path / "yarn.lock").write_text("")
        env = detect_node_env(tmp_path)
        assert env is not None
        assert env.package_manager == "yarn"

    def test_pnpm_project(self, tmp_path: Path) -> None:
        (tmp_path / "pnpm-lock.yaml").write_text("")
        env = detect_node_env(tmp_path)
        assert env is not None
        assert env.package_manager == "pnpm"

    def test_tsconfig_detected(self, tmp_path: Path) -> None:
        (tmp_path / "tsconfig.json").write_text("{}")
        env = detect_node_env(tmp_path)
        assert env is not None
        assert env.tsconfig == tmp_path / "tsconfig.json"

    def test_no_node(self, tmp_path: Path) -> None:
        env = detect_node_env(tmp_path)
        assert env is None


class TestDetectGoEnv:
    def test_go_mod(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module example.com/foo\n\ngo 1.21\n")
        env = detect_go_env(tmp_path)
        assert env is not None
        assert env.go_mod == tmp_path / "go.mod"

    def test_go_work(self, tmp_path: Path) -> None:
        (tmp_path / "go.work").write_text("go 1.21\n\nuse ./service\n")
        env = detect_go_env(tmp_path)
        assert env is not None
        assert env.go_work == tmp_path / "go.work"

    def test_no_go(self, tmp_path: Path) -> None:
        env = detect_go_env(tmp_path)
        assert env is None


class TestDetectCppEnv:
    def test_compile_commands(self, tmp_path: Path) -> None:
        (tmp_path / "compile_commands.json").write_text("[]")
        env = detect_cpp_env(tmp_path)
        assert env is not None
        assert env.compile_commands == tmp_path / "compile_commands.json"

    def test_compile_commands_in_build(self, tmp_path: Path) -> None:
        build = tmp_path / "build"
        build.mkdir()
        (build / "compile_commands.json").write_text("[]")
        env = detect_cpp_env(tmp_path)
        assert env is not None
        assert env.compile_commands == build / "compile_commands.json"

    def test_clangd_config(self, tmp_path: Path) -> None:
        (tmp_path / ".clangd").write_text("CompileFlags:\n  Add: [-std=c++20]\n")
        env = detect_cpp_env(tmp_path)
        assert env is not None
        assert env.clangd_config == tmp_path / ".clangd"

    def test_no_cpp(self, tmp_path: Path) -> None:
        env = detect_cpp_env(tmp_path)
        assert env is None


class TestDetectToolchain:
    def test_multi_language(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module example.com/foo\n\ngo 1.21\n")
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\n")
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "bin").mkdir()
        (venv / "bin" / "python").write_text("#!/bin/sh\n")
        (venv / "bin" / "python").chmod(0o755)

        tc = detect_toolchain(tmp_path, ["python", "go"])
        assert tc.python_env is not None
        assert tc.go_env is not None
        assert tc.node_env is None

    def test_empty_languages(self, tmp_path: Path) -> None:
        tc = detect_toolchain(tmp_path, [])
        assert tc.python_env is None


class TestLoadCodebrainOverrides:
    def test_no_config(self, tmp_path: Path) -> None:
        overrides = load_codebrain_overrides(tmp_path)
        assert overrides == {}

    def test_python_overrides(self, tmp_path: Path) -> None:
        (tmp_path / ".codebrain.toml").write_text(
            '[python]\nvenv = "custom_venv"\npyright_config = "custom_pyright.json"\n'
        )
        overrides = load_codebrain_overrides(tmp_path)
        assert overrides["python"]["venv"] == "custom_venv"

    def test_exclude_paths(self, tmp_path: Path) -> None:
        (tmp_path / ".codebrain.toml").write_text('[exclude]\npaths = ["legacy/", "vendor/"]\n')
        overrides = load_codebrain_overrides(tmp_path)
        assert "legacy/" in overrides["exclude"]["paths"]

    def test_scan_depth(self, tmp_path: Path) -> None:
        (tmp_path / ".codebrain.toml").write_text("[scan]\nmax_depth = 8\n")
        overrides = load_codebrain_overrides(tmp_path)
        assert overrides["scan"]["max_depth"] == 8
