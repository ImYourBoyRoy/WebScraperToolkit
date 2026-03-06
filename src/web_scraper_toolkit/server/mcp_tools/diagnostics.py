# ./src/web_scraper_toolkit/server/mcp_tools/diagnostics.py
"""
Register MCP tools that expose standalone diagnostics scripts as callable APIs.
Used by the MCP server to let agents run browser diagnostics without shell access.
Run: imported by mcp_server during startup; not a standalone executable.
Inputs: tool mode, URLs, browser options, and optional passthrough CLI args.
Outputs: JSON envelopes containing subprocess telemetry and parsed diagnostic reports.
Side effects: launches local browser/script subprocesses and writes files in ./scripts/out.
Operational notes: intended for authorized testing workflows and deterministic troubleshooting.
"""

from __future__ import annotations

import logging

from ...core.script_diagnostics import (
    run_bot_check_diagnostic,
    run_browser_info_diagnostic,
    run_challenge_matrix_diagnostic,
    run_toolkit_route_diagnostic,
    split_cli_args,
)

logger = logging.getLogger("mcp_server")


def register_diagnostics_tools(
    mcp: object,
    create_envelope: object,
    format_error: object,
    run_in_process: object,
) -> None:
    """Register script-backed diagnostics tools with MCP."""

    @mcp.tool()
    async def run_challenge_diagnostic(
        mode: str = "toolkit",
        url: str = "https://example.com/",
        timeout_ms: int = 45000,
        skip_interactive: bool = False,
        include_headless_stage: bool = False,
        require_2xx_status: bool = False,
        save_artifacts: bool = False,
        artifacts_dir: str | None = None,
        auto_commit_host_profile: bool = False,
        host_profiles_path: str | None = None,
        read_only: bool = False,
        variants: str = "baseline,minimal_stealth,legacy_stealth",
        runs_per_variant: int = 1,
        browser: str = "chrome",
        headless: bool = False,
        hold_method: str = "auto",
        hold_seconds: float = 12.0,
        skip_hold: bool = False,
        extra_args: str = "",
    ) -> str:
        """
        Run target-site diagnostics in either toolkit-native or matrix smoking-gun mode.
        mode=toolkit -> scripts/diag_toolkit_route.py
        mode=matrix  -> scripts/challenge_diagnostic_matrix.py
        """
        try:
            parsed_extra = split_cli_args(extra_args)
            logger.info(
                "Tool Call: run_challenge_diagnostic mode=%s url=%s browser=%s headless=%s",
                mode,
                url,
                browser,
                headless,
            )

            normalized_mode = mode.strip().lower()
            if normalized_mode == "toolkit":
                result = await run_in_process(
                    run_toolkit_route_diagnostic,
                    url=url,
                    timeout_ms=timeout_ms,
                    skip_interactive=skip_interactive,
                    include_headless_stage=include_headless_stage,
                    require_2xx_status=require_2xx_status,
                    save_artifacts=save_artifacts,
                    artifacts_dir=artifacts_dir,
                    auto_commit_host_profile=auto_commit_host_profile,
                    host_profiles_path=host_profiles_path,
                    read_only=read_only,
                    extra_args=parsed_extra,
                    timeout_profile="long",
                    work_units=4,
                )
            elif normalized_mode == "matrix":
                result = await run_in_process(
                    run_challenge_matrix_diagnostic,
                    url=url,
                    variants=variants,
                    runs_per_variant=runs_per_variant,
                    browser=browser,
                    headless=headless,
                    timeout_ms=timeout_ms,
                    hold_method=hold_method,
                    hold_seconds=hold_seconds,
                    skip_hold=skip_hold,
                    extra_args=parsed_extra,
                    timeout_profile="long",
                    work_units=6,
                )
            else:
                raise ValueError("mode must be 'toolkit' or 'matrix'")

            return create_envelope(
                "success",
                result,
                meta={
                    "mode": normalized_mode,
                    "authorized_testing_only": True,
                    "read_only": read_only,
                    "auto_commit_host_profile": auto_commit_host_profile,
                    "require_2xx_status": require_2xx_status,
                    "save_artifacts": save_artifacts,
                },
            )
        except Exception as exc:
            return format_error("run_challenge_diagnostic", exc)

    @mcp.tool()
    async def run_bot_surface_diagnostic(
        test_url: str = "https://example.com/",
        browsers: str = "chromium,pw_chrome,system_chrome",
        modes: str = "baseline,stealth",
        headless: bool = False,
        prefer_system: str = "chrome",
        use_default_sites: bool = False,
        screenshots: bool = False,
        sites: str = "",
        extra_args: str = "",
    ) -> str:
        """Run script-level bot surface diagnostics (scripts/bot_check.py)."""
        try:
            logger.info(
                "Tool Call: run_bot_surface_diagnostic test_url=%s browsers=%s modes=%s",
                test_url,
                browsers,
                modes,
            )
            result = await run_in_process(
                run_bot_check_diagnostic,
                test_url=test_url,
                browsers=browsers,
                modes=modes,
                headless=headless,
                prefer_system=prefer_system,
                use_default_sites=use_default_sites,
                screenshots=screenshots,
                sites=sites,
                extra_args=split_cli_args(extra_args),
                timeout_profile="long",
                work_units=6,
            )
            return create_envelope(
                "success",
                result,
                meta={"authorized_testing_only": True},
            )
        except Exception as exc:
            return format_error("run_bot_surface_diagnostic", exc)

    @mcp.tool()
    async def run_browser_info_diagnostic_tool(
        save_to_file: bool = True,
        extra_args: str = "",
    ) -> str:
        """Collect browser fingerprint telemetry via scripts/get_browser_info.py."""
        try:
            logger.info(
                "Tool Call: run_browser_info_diagnostic_tool save_to_file=%s",
                save_to_file,
            )
            result = await run_in_process(
                run_browser_info_diagnostic,
                save_to_file=save_to_file,
                extra_args=split_cli_args(extra_args),
                timeout_profile="long",
                work_units=3,
            )
            return create_envelope(
                "success",
                result,
                meta={"authorized_testing_only": True},
            )
        except Exception as exc:
            return format_error("run_browser_info_diagnostic_tool", exc)

    logger.info("Registered: diagnostics tools (4, including one compatibility alias)")
