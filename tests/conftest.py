"""Shared test fixtures for CodeBrain tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace directory for testing."""
    return tmp_path


@pytest.fixture
def python_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with a sample Python file."""
    test_file = tmp_path / "example.py"
    test_file.write_text(
        'def greet(name: str) -> str:\n    return "Hello, " + name\n'
    )
    return tmp_path


@pytest.fixture
def python_workspace_with_errors(tmp_path: Path) -> Path:
    """Create a temporary workspace with a Python file containing type errors."""
    test_file = tmp_path / "errors.py"
    test_file.write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n\nresult: str = add(1, 2)\n"
    )
    return tmp_path
