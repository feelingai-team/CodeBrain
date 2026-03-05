"""CLI entry point for the CodeBrain MCP server."""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    """Start the CodeBrain MCP server on stdio."""
    parser = argparse.ArgumentParser(description="CodeBrain MCP server")
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root directory (default: current directory)",
    )
    parser.add_argument(
        "--languages",
        nargs="*",
        default=None,
        help="Language servers to enable (e.g. python typescript cpp). Default: all available.",
    )
    args = parser.parse_args()

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
