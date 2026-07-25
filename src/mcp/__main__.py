# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.server-identity
# - 001055#repo.mcp.transport-default-and-expansion-gate
# - 001055#repo.mcp.remote-http-loopback-transport
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Local MCP command entrypoint.

Boundary contract:
- Owns: repository-local CLI inspection for MCP startup and tool registry state.
- Must not: open network listeners, run live services, or execute tools.
- Allows: deterministic JSON output for local startup checks.
- Split when: a real MCP SDK transport or long-running host is introduced.
- Merge when: another entrypoint exposes the same local MCP startup contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from mcp.context import mcp_prompt_registry
from mcp.http_server import (
    DEFAULT_PUBLIC_BASE_URL,
    DEFAULT_REMOTE_MCP_HOST,
    DEFAULT_REMOTE_MCP_PORT,
    RemoteMcpHttpOptions,
    serve_remote_mcp_http,
)
from mcp.registry import mcp_tool_registry
from mcp.server import start_mcp_test_server

if TYPE_CHECKING:
    from mcp.models import JsonObject


class McpCommandNamespace(argparse.Namespace):
    """Typed namespace for MCP inspection commands."""

    command: str
    repo_root: str
    host: str
    port: int
    public_base_url: str


def main(argv: list[str] | None = None) -> int:
    """Run the local MCP inspection CLI.

    Returns:
        The process exit status.
    """
    args = _parse_args(argv)
    if args.command == "http":
        serve_remote_mcp_http(
            RemoteMcpHttpOptions(
                repo_root=Path(args.repo_root),
                host=args.host,
                port=args.port,
                public_base_url=args.public_base_url.rstrip("/"),
            )
        )
        return 0
    if args.command == "start":
        payload = _startup_payload()
    elif args.command == "prompts":
        payload = _prompts_payload()
    else:
        payload = _tools_payload()
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    _ = sys.stdout.write("\n")
    return 0


def _parse_args(argv: list[str] | None) -> McpCommandNamespace:
    """Parse MCP CLI arguments into a typed namespace.

    Returns:
        The parsed value.

    Raises:
        TypeError: If an input value has an unsupported type.
    """
    namespace = McpCommandNamespace()
    parsed_namespace = _argument_parser().parse_args(argv, namespace=namespace)
    if parsed_namespace is not namespace:
        message = "argparse returned an unexpected namespace instance."
        raise TypeError(message)
    return namespace


def _argument_parser() -> argparse.ArgumentParser:
    """Build the MCP CLI argument parser.

    Returns:
        The constructed value.
    """
    parser = argparse.ArgumentParser(prog="python -B -m mcp")
    subcommands = parser.add_subparsers(dest="command", required=True)
    _ = subcommands.add_parser(
        "start", help="print the local test-mode startup contract"
    )
    _ = subcommands.add_parser(
        "tools", help="print the local MCP tool registry"
    )
    _ = subcommands.add_parser(
        "prompts", help="print the local MCP catalog prompt registry"
    )
    http_parser = subcommands.add_parser(
        "http",
        help="serve the loopback MCP HTTP origin for Cloudflare Tunnel",
    )
    _ = http_parser.add_argument("--repo-root", default=".")
    _ = http_parser.add_argument("--host", default=DEFAULT_REMOTE_MCP_HOST)
    _ = http_parser.add_argument(
        "--port", type=int, default=DEFAULT_REMOTE_MCP_PORT
    )
    _ = http_parser.add_argument(
        "--public-base-url", default=DEFAULT_PUBLIC_BASE_URL
    )
    return parser


def _startup_payload() -> JsonObject:
    """Return local MCP startup state without live networking."""
    server = start_mcp_test_server()
    return {
        "server_name": server.config.server_name,
        "canonical_url": server.config.canonical_url,
        "transports": list(server.config.transports),
        "test_mode": server.config.test_mode,
        "started": server.started,
        "tool_names": [tool.name for tool in server.tools],
        "resource_uris": [resource.uri for resource in server.resources],
        "prompt_names": [prompt.name for prompt in server.prompts],
        "live_network_transport": False,
    }


def _tools_payload() -> JsonObject:
    """Return the local MCP registry without executing any tool."""
    return {
        "tools": [
            {
                "name": tool.name,
                "read_only": tool.read_only,
                "input_schema": tool.input_schema(),
            }
            for tool in mcp_tool_registry()
        ]
    }


def _prompts_payload() -> JsonObject:
    """Return the local MCP prompt registry without executing tools."""
    return {
        "prompts": [
            {
                "name": prompt.name,
                "description": prompt.description,
            }
            for prompt in mcp_prompt_registry()
        ]
    }


if __name__ == "__main__":
    raise SystemExit(main())
