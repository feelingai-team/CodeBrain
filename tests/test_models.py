"""Tests for new toolchain and sub-project models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from codebrain.core.models import (
    CppEnv,
    GoEnv,
    HealthReport,
    Language,
    LanguageHealth,
    NodeEnv,
    PythonEnv,
    SubProject,
    SubProjectHealth,
    ToolchainConfig,
)


class TestLanguageEnum:
    def test_is_str_enum(self) -> None:
        assert issubclass(Language, StrEnum)

    def test_values(self) -> None:
        assert Language.PYTHON == "python"
        assert Language.TYPESCRIPT == "typescript"
        assert Language.GO == "go"
        assert Language.CPP == "cpp"

    def test_from_string(self) -> None:
        assert Language("python") == Language.PYTHON


class TestEnvModels:
    def test_python_env_defaults(self) -> None:
        env = PythonEnv()
        assert env.venv_path is None
        assert env.python_binary is None
        assert env.pyright_config is None
        assert env.manager is None

    def test_python_env_with_values(self) -> None:
        env = PythonEnv(
            venv_path=Path("/project/.venv"),
            python_binary=Path("/project/.venv/bin/python"),
            manager="venv",
        )
        assert env.venv_path == Path("/project/.venv")
        assert env.manager == "venv"

    def test_node_env(self) -> None:
        env = NodeEnv(
            node_modules=Path("/project/node_modules"),
            tsconfig=Path("/project/tsconfig.json"),
            package_manager="pnpm",
        )
        assert env.package_manager == "pnpm"

    def test_go_env(self) -> None:
        env = GoEnv(go_mod=Path("/project/go.mod"))
        assert env.go_mod == Path("/project/go.mod")
        assert env.go_work is None

    def test_cpp_env(self) -> None:
        env = CppEnv(compile_commands=Path("/project/build/compile_commands.json"))
        assert env.compile_commands is not None


class TestToolchainConfig:
    def test_empty_config(self) -> None:
        tc = ToolchainConfig()
        assert tc.python_env is None
        assert tc.node_env is None
        assert tc.go_env is None
        assert tc.cpp_env is None
        assert tc.extra_config == {}

    def test_with_python(self) -> None:
        tc = ToolchainConfig(
            python_env=PythonEnv(venv_path=Path("/p/.venv"))
        )
        assert tc.python_env is not None
        assert tc.python_env.venv_path == Path("/p/.venv")


class TestSubProject:
    def test_basic(self) -> None:
        sp = SubProject(
            root=Path("/mono/backend"),
            languages=[Language.GO],
            markers={"go.mod": Path("/mono/backend/go.mod")},
            toolchain=ToolchainConfig(),
        )
        assert sp.root == Path("/mono/backend")
        assert sp.parent is None

    def test_nested(self) -> None:
        sp = SubProject(
            root=Path("/mono/backend/ml"),
            languages=[Language.PYTHON],
            markers={"pyproject.toml": Path("/mono/backend/ml/pyproject.toml")},
            toolchain=ToolchainConfig(),
            parent=Path("/mono/backend"),
        )
        assert sp.parent == Path("/mono/backend")


class TestHealthReport:
    def test_health_report(self) -> None:
        report = HealthReport(
            workspace_root=Path("/mono"),
            timestamp=datetime.now(tz=UTC),
            sub_projects=[
                SubProjectHealth(
                    root=Path("/mono/backend"),
                    languages={
                        "go": LanguageHealth(
                            status="active", server="gopls"
                        )
                    },
                ),
            ],
        )
        assert len(report.sub_projects) == 1
        assert report.sub_projects[0].languages["go"].status == "active"
