"""CLI entry point for CodeBrain."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SUBCOMMANDS = {"server", "init"}


def _cmd_server(args: argparse.Namespace) -> None:
    """Start the CodeBrain MCP server on stdio."""
    try:
        from codebrain.mcp.server import create_server
    except ImportError:
        print(
            "Error: fastmcp is required. Install with: pip install codebrain[mcp]",
            file=sys.stderr,
        )
        sys.exit(1)

    server = create_server(
        workspace_root=args.workspace,
        languages=args.languages,
    )
    server.run(transport="stdio")


def _cmd_init(args: argparse.Namespace) -> None:
    """Initialize CodeBrain configuration in a project."""
    from codebrain.bootstrap import init_project

    result = init_project(
        root=Path(args.directory),
        dry_run=args.dry_run,
    )
    print(result)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CodeBrain — LSP-based code validation and structural search",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- server ---
    server_parser = subparsers.add_parser(
        "server", help="Start the MCP server on stdio"
    )
    server_parser.add_argument(
        "--workspace", default=".",
        help="Workspace root directory (default: current directory)",
    )
    server_parser.add_argument(
        "--languages", nargs="*", default=None,
        help="Language servers to enable (e.g. python typescript go). Default: all available.",
    )

    # --- init ---
    init_parser = subparsers.add_parser(
        "init", help="Auto-generate .mcp.json, CLAUDE.md, and hooks for a project"
    )
    init_parser.add_argument(
        "directory", nargs="?", default=".",
        help="Project root to initialize (default: current directory)",
    )
    init_parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be created without writing files",
    )

    return parser


def main() -> None:
    """CodeBrain CLI — MCP server and project initialization."""
    # Backward compatibility: if first real arg is not a known subcommand,
    # assume "server" mode (e.g. `codebrain-mcp --languages python`)
    argv = sys.argv[1:]
    has_subcommand = any(a in _SUBCOMMANDS for a in argv if not a.startswith("-"))
    if not has_subcommand:
        argv = ["server"] + argv

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        _cmd_init(args)
    else:
        _cmd_server(args)
