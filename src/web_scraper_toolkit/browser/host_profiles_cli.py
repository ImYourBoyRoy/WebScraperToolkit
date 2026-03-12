# ./src/web_scraper_toolkit/browser/host_profiles_cli.py
"""
Operator CLI for inspecting and managing learned host routing profiles.
Run: `python -m web_scraper_toolkit.browser.host_profiles_cli <command> ...` or installed entrypoint.
Inputs: host profile store path, host names, and explicit promote/demote/reset commands.
Outputs: compact console summaries or JSON payloads describing learned routing and audit history.
Side effects: read-only for inspect/diff/summary; mutate the JSON store for promote/demote/reset.
Operational notes: mutations are always explicit subcommands so operator review stays intentional.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Sequence

from .host_profiles import HostProfileStore


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WebScraperToolkit host profile tools")
    parser.add_argument(
        "--path",
        default="./host_profiles.json",
        help="Path to the host profile JSON store.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of compact text output.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect one host profile")
    inspect_parser.add_argument("host", help="Host or URL to inspect.")

    diff_parser = subparsers.add_parser(
        "diff", help="Diff one host profile against defaults"
    )
    diff_parser.add_argument("host", help="Host or URL to diff.")

    promote_parser = subparsers.add_parser(
        "promote", help="Promote a learned candidate"
    )
    promote_parser.add_argument("host", help="Host or URL to promote.")

    demote_parser = subparsers.add_parser(
        "demote", help="Demote an active profile to candidate"
    )
    demote_parser.add_argument("host", help="Host or URL to demote.")

    reset_parser = subparsers.add_parser("reset", help="Reset a host profile")
    reset_parser.add_argument("host", help="Host or URL to reset.")
    reset_parser.add_argument(
        "--drop-audit",
        action="store_true",
        help="Drop audit history during reset.",
    )

    summary_parser = subparsers.add_parser(
        "summary", help="Summarize all learned hosts"
    )
    summary_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of hosts to print.",
    )
    return parser


def _store_from_args(args: argparse.Namespace) -> HostProfileStore:
    return HostProfileStore(path=str(Path(args.path)))


def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))  # noqa: T201


def _print_inspection(payload: Dict[str, Any]) -> None:
    print(f"Host: {payload.get('host', '')}")  # noqa: T201
    print(f"Store: {payload.get('path', '')}")  # noqa: T201
    print(f"Active: {bool(payload.get('has_active_profile', False))}")  # noqa: T201
    match = (
        payload.get("match", {}) if isinstance(payload.get("match", {}), dict) else {}
    )
    print(  # noqa: T201
        "Match: "
        f"{match.get('match_key', '') or 'none'}"
        f" ({match.get('match_scope', 'none')})"
    )
    resolved = payload.get("resolved_routing", {})
    if isinstance(resolved, dict) and resolved:
        print("Resolved Routing:")  # noqa: T201
        for key, value in sorted(resolved.items()):
            print(f"  - {key}: {value}")  # noqa: T201
    print(f"Audit Count: {int(payload.get('audit_count', 0) or 0)}")  # noqa: T201
    audit_tail = payload.get("audit_tail", [])
    if isinstance(audit_tail, list) and audit_tail:
        print("Recent Attempts:")  # noqa: T201
        for row in audit_tail[-5:]:
            if not isinstance(row, dict):
                continue
            print(  # noqa: T201
                "  - "
                f"{row.get('seen_utc', '')} "
                f"success={row.get('success', row.get('event', ''))} "
                f"status={row.get('status', '')} "
                f"blocked={row.get('blocked_reason', '')}"
            )


def _print_diff(payload: Dict[str, Any]) -> None:
    _print_inspection(payload)
    diff = payload.get("diff", {}) if isinstance(payload.get("diff", {}), dict) else {}
    print("Diffs:")  # noqa: T201
    for section, section_rows in diff.items():
        if not isinstance(section_rows, dict) or not section_rows:
            continue
        print(f"  {section}:")  # noqa: T201
        for key, row in sorted(section_rows.items()):
            if not isinstance(row, dict):
                continue
            print(  # noqa: T201
                f"    - {key}: baseline={row.get('baseline')} target={row.get('target')}"
            )


def _print_summary(payload: Dict[str, Any]) -> None:
    print(f"Store: {payload.get('path', '')}")  # noqa: T201
    print(f"Hosts: {int(payload.get('host_count', 0) or 0)}")  # noqa: T201
    rows = payload.get("hosts", [])
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        print(  # noqa: T201
            "- "
            f"{row.get('host', '')} | "
            f"active={row.get('has_active_profile', False)} | "
            f"candidate={row.get('has_candidate', False)} | "
            f"mode={row.get('routing_mode', '')} | "
            f"audit={row.get('audit_count', 0)}"
        )


def _print_action(payload: Dict[str, Any]) -> None:
    print(f"{payload.get('action', '').upper()}: {payload.get('host', '')}")  # noqa: T201
    result = payload.get("result", {})
    if isinstance(result, dict) and result:
        for key, value in sorted(result.items()):
            if key == "routing" and isinstance(value, dict):
                print("  routing:")  # noqa: T201
                for route_key, route_value in sorted(value.items()):
                    print(f"    - {route_key}: {route_value}")  # noqa: T201
                continue
            print(f"  {key}: {value}")  # noqa: T201


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    store = _store_from_args(args)

    try:
        if args.command == "inspect":
            payload = store.inspect_host(args.host)
        elif args.command == "diff":
            payload = store.diff_host(args.host)
        elif args.command == "promote":
            payload = {
                "host": args.host,
                "result": store.promote_candidate(args.host),
                "action": "promote",
            }
        elif args.command == "demote":
            payload = {
                "host": args.host,
                "result": store.demote_active(args.host),
                "action": "demote",
            }
        elif args.command == "reset":
            payload = {
                "host": args.host,
                "result": store.reset_host(args.host, keep_audit=not args.drop_audit),
                "action": "reset",
            }
        elif args.command == "summary":
            payload = store.summarize_hosts(limit=args.limit)
        else:  # pragma: no cover - argparse already constrains this
            raise ValueError(f"Unsupported command: {args.command}")
    except Exception as exc:
        error_payload = {
            "command": args.command,
            "error": str(exc),
            "path": str(Path(args.path)),
        }
        if args.json:
            _print_json(error_payload)
        else:
            print(f"ERROR: {exc}")  # noqa: T201
        return 1

    if args.json:
        _print_json(payload)
    elif args.command == "summary":
        _print_summary(payload)
    elif args.command == "diff":
        _print_diff(payload)
    elif args.command in {"promote", "demote", "reset"}:
        _print_action(payload)
    else:
        _print_inspection(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
