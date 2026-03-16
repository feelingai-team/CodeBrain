"""Per-language toolchain detection for sub-projects."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from codebrain.core.models import CppEnv, GoEnv, NodeEnv, PythonEnv, ToolchainConfig

logger = logging.getLogger(__name__)


def detect_python_env(root: Path) -> PythonEnv | None:
    """Detect Python virtual environment and pyright configuration."""
    venv_path: Path | None = None
    python_binary: Path | None = None
    manager: str | None = None
    pyright_config: Path | None = None

    # 1. Check standard venv directory names
    for name in (".venv", "venv", ".env", "env"):
        candidate = root / name
        if candidate.is_dir():
            venv_path = candidate
            bin_path = candidate / "bin" / "python"
            if bin_path.exists() and os.access(bin_path, os.X_OK):
                python_binary = bin_path
            manager = "venv"
            break

    # 2. Check .python-version (pyenv)
    if manager is None and (root / ".python-version").is_file():
        manager = "pyenv"

    # 3. Check CONDA_PREFIX
    if manager is None:
        conda_prefix = os.environ.get("CONDA_PREFIX")
        if conda_prefix:
            conda_path = Path(conda_prefix)
            if conda_path.is_dir():
                venv_path = conda_path
                manager = "conda"
                conda_python = conda_path / "bin" / "python"
                if conda_python.exists():
                    python_binary = conda_python

    # 4. Detect pyright config
    pyrightconfig = root / "pyrightconfig.json"
    if pyrightconfig.is_file():
        pyright_config = pyrightconfig
    else:
        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            try:
                import tomllib

                with open(pyproject, "rb") as f:
                    data = tomllib.load(f)
                if "tool" in data and "pyright" in data["tool"]:
                    pyright_config = pyproject
            except Exception:
                pass

    if venv_path is None and pyright_config is None and manager is None:
        return None

    return PythonEnv(
        venv_path=venv_path,
        python_binary=python_binary,
        pyright_config=pyright_config,
        manager=manager,
    )


def detect_node_env(root: Path) -> NodeEnv | None:
    """Detect Node.js environment: node_modules, tsconfig, package manager."""
    node_modules: Path | None = None
    tsconfig: Path | None = None
    package_manager: str | None = None

    nm = root / "node_modules"
    if nm.is_dir():
        node_modules = nm

    for name in ("tsconfig.json", "jsconfig.json"):
        candidate = root / name
        if candidate.is_file():
            tsconfig = candidate
            break

    if (root / "pnpm-lock.yaml").is_file():
        package_manager = "pnpm"
    elif (root / "yarn.lock").is_file():
        package_manager = "yarn"
    elif (root / "package-lock.json").is_file():
        package_manager = "npm"

    if node_modules is None and tsconfig is None and package_manager is None:
        return None

    return NodeEnv(
        node_modules=node_modules,
        tsconfig=tsconfig,
        package_manager=package_manager,
    )


def detect_go_env(root: Path) -> GoEnv | None:
    """Detect Go environment: go.mod, go.work, GOROOT."""
    go_mod: Path | None = None
    go_work: Path | None = None

    if (root / "go.mod").is_file():
        go_mod = root / "go.mod"
    if (root / "go.work").is_file():
        go_work = root / "go.work"

    if go_mod is None and go_work is None:
        return None

    goroot_str = os.environ.get("GOROOT")
    goroot = Path(goroot_str) if goroot_str else None

    gomodcache_str = os.environ.get("GOMODCACHE")
    gomodcache = Path(gomodcache_str) if gomodcache_str else None

    return GoEnv(
        go_mod=go_mod,
        go_work=go_work,
        goroot=goroot,
        gomodcache=gomodcache,
    )


def detect_cpp_env(root: Path) -> CppEnv | None:
    """Detect C/C++ environment: compile_commands, .clangd, CMake."""
    compile_commands: Path | None = None
    clangd_config: Path | None = None
    cmake_presets: Path | None = None

    cc = root / "compile_commands.json"
    if cc.is_file():
        compile_commands = cc
    else:
        cc_build = root / "build" / "compile_commands.json"
        if cc_build.is_file():
            compile_commands = cc_build

    if (root / ".clangd").is_file():
        clangd_config = root / ".clangd"

    if (root / "CMakePresets.json").is_file():
        cmake_presets = root / "CMakePresets.json"

    if compile_commands is None and clangd_config is None and cmake_presets is None:
        return None

    return CppEnv(
        compile_commands=compile_commands,
        clangd_config=clangd_config,
        cmake_presets=cmake_presets,
    )


def detect_toolchain(root: Path, languages: list[str]) -> ToolchainConfig:
    """Detect the full toolchain for a sub-project given its detected languages."""
    python_env = detect_python_env(root) if "python" in languages else None
    node_env = detect_node_env(root) if "typescript" in languages else None
    go_env = detect_go_env(root) if "go" in languages else None
    cpp_env = detect_cpp_env(root) if "cpp" in languages else None

    return ToolchainConfig(
        python_env=python_env,
        node_env=node_env,
        go_env=go_env,
        cpp_env=cpp_env,
    )


def load_codebrain_overrides(root: Path, parent_root: Path | None = None) -> dict:
    """Load .codebrain.toml overrides, merging parent workspace config if present."""
    import tomllib

    merged: dict = {}

    if parent_root is not None:
        parent_config = parent_root / ".codebrain.toml"
        if parent_config.is_file():
            try:
                with open(parent_config, "rb") as f:
                    merged = tomllib.load(f)
            except Exception:
                logger.warning("Failed to parse %s", parent_config)

    config_path = root / ".codebrain.toml"
    if config_path.is_file():
        try:
            with open(config_path, "rb") as f:
                local = tomllib.load(f)
            merged.update(local)
        except Exception:
            logger.warning("Failed to parse %s", config_path)

    return merged
