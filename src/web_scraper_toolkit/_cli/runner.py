# ./src/web_scraper_toolkit/_cli/runner.py
"""
Async CLI runtime orchestration extracted from the public cli.py facade.
Used by cli facade while preserving patchable module-level dependencies.
Run: invoked by cli.main_async wrapper.
Inputs: dependency bundle, parsed CLI args, runtime settings, and config payloads.
Outputs: executes selected CLI mode workflows and returns on success.
Side effects: reads/writes files, starts crawlers, prints console panels, may sys.exit.
Operational notes: dependency injection preserves test patch behavior on facade symbols.
"""

from __future__ import annotations

from typing import Any, Callable


async def run_main_async(
    *,
    parse_arguments_fn: Callable[..., Any],
    normalize_diagnostic_name_fn: Callable[[str | None], str | None],
    bootstrap_default_config_files_fn: Callable[..., dict],
    load_global_config_fn: Callable[..., dict],
    load_runtime_settings_fn: Callable[..., Any],
    resolve_worker_count_fn: Callable[..., int],
    console: Any,
    logger: Any,
    load_urls_from_source_fn: Callable[[str], Any],
    WebCrawlerCls: Any,
    BrowserConfigCls: Any,
    print_diagnostics_fn: Callable[[], None],
    ProxyManagerCls: Any,
    ProxieConfigCls: Any,
    AutonomousCrawlerCls: Any,
    PlaybookCls: Any,
    extract_sitemap_tree_fn: Callable[[str], Any],
    PanelCls: Any,
    TableCls: Any,
    os_module: Any,
    sys_module: Any,
    json_module: Any,
    asyncio_module: Any,
) -> None:
    args = parse_arguments_fn()
    bootstrap_result = bootstrap_default_config_files_fn(
        config_path=args.config,
        local_config_path=args.local_config,
    )
    if bootstrap_result["errors"]:
        for err in bootstrap_result["errors"]:
            logger.warning(err)
    if bootstrap_result["created"] and args.verbose:
        console.print(
            PanelCls(
                "[green]Bootstrapped config files:[/green]\n"
                + "\n".join(f"- {path}" for path in bootstrap_result["created"]),
                title="Config Bootstrap",
            )
        )

    runtime_settings = load_runtime_settings_fn(
        config_json_path=args.config,
        local_cfg_path=args.local_config,
    )
    global_config = load_global_config_fn(args.config, logger=logger)

    if args.run_diagnostic:
        from ..core.script_diagnostics import (
            run_bot_check_diagnostic,
            run_browser_info_diagnostic,
            run_challenge_matrix_diagnostic,
            run_toolkit_route_diagnostic,
            split_cli_args,
        )

        normalized_diagnostic = normalize_diagnostic_name_fn(args.run_diagnostic)
        if normalized_diagnostic is None:
            supported = [
                "toolkit_route",
                "challenge_matrix",
                "bot_check",
                "browser_info",
            ]
            console.print(
                f"[bold red]Unsupported --run-diagnostic value:[/bold red] {args.run_diagnostic}"
            )
            console.print(f"Supported values: {', '.join(supported)}")
            sys_module.exit(1)

        diag_url = args.diagnostic_url or "https://example.com/"
        extra_args = split_cli_args(args.diagnostic_extra_args)
        console.print(
            PanelCls(
                f"[bold cyan]Running diagnostic:[/bold cyan] {normalized_diagnostic}",
                title="Toolkit Diagnostics",
            )
        )

        if normalized_diagnostic == "toolkit_route":
            result = await asyncio_module.to_thread(
                run_toolkit_route_diagnostic,
                url=diag_url,
                timeout_ms=max(5000, int(args.diagnostic_timeout_ms)),
                skip_interactive=args.diagnostic_skip_interactive,
                include_headless_stage=args.diagnostic_include_headless_stage,
                require_2xx_status=args.diagnostic_require_2xx,
                save_artifacts=args.diagnostic_save_artifacts,
                artifacts_dir=args.diagnostic_artifacts_dir,
                auto_commit_host_profile=args.diagnostic_auto_commit_host_profile,
                host_profiles_path=args.diagnostic_host_profiles_file,
                read_only=args.diagnostic_read_only,
                extra_args=extra_args,
            )
        elif normalized_diagnostic == "challenge_matrix":
            result = await asyncio_module.to_thread(
                run_challenge_matrix_diagnostic,
                url=diag_url,
                variants=args.diagnostic_variants,
                runs_per_variant=max(1, int(args.diagnostic_runs_per_variant)),
                browser=args.diagnostic_browser,
                headless=args.diagnostic_headless,
                timeout_ms=max(10000, int(args.diagnostic_timeout_ms)),
                hold_method=args.diagnostic_hold_method,
                hold_seconds=max(0.5, float(args.diagnostic_hold_seconds)),
                extra_args=extra_args,
            )
        elif normalized_diagnostic == "bot_check":
            bot_url = args.diagnostic_url or "https://example.com/"
            result = await asyncio_module.to_thread(
                run_bot_check_diagnostic,
                test_url=bot_url,
                browsers=args.diagnostic_browsers,
                modes=args.diagnostic_modes,
                headless=args.diagnostic_headless,
                prefer_system=args.diagnostic_prefer_system,
                use_default_sites=args.diagnostic_use_default_sites,
                screenshots=args.diagnostic_screenshots,
                sites=args.diagnostic_sites,
                extra_args=extra_args,
            )
        else:
            result = await asyncio_module.to_thread(
                run_browser_info_diagnostic,
                save_to_file=True,
                extra_args=extra_args,
            )

        summary = {
            "tool": normalized_diagnostic,
            "return_code": result.get("return_code"),
            "success": result.get("success"),
            "elapsed_ms": result.get("elapsed_ms"),
            "report_path": result.get("report_path"),
        }
        console.print(
            PanelCls(json_module.dumps(summary, indent=2), title="Diagnostic Summary")
        )

        if args.verbose:
            console.print(
                PanelCls(
                    json_module.dumps(result, indent=2)[:12000],
                    title="Diagnostic Full Payload (truncated)",
                )
            )

        if not bool(result.get("success", False)):
            sys_module.exit(1)
        return

    if args.site_tree and args.input:
        console.print(
            f"[bold cyan]Extracting Sitemap Tree from:[/bold cyan] {args.input}"
        )
        urls = await extract_sitemap_tree_fn(args.input)

        if not urls:
            console.print("[bold red]No URLs found.[/bold red]")
            sys_module.exit(1)

        if args.output_name:
            out_path = args.output_name
        else:
            base = "sitemap_tree"
            if args.format == "json":
                out_path = f"{base}.json"
            elif args.format == "xml":
                out_path = f"{base}.xml"
            else:
                out_path = f"{base}.csv"

        if out_path.endswith(".json"):
            with open(out_path, "w", encoding="utf-8") as handle:
                json_module.dump(urls, handle, indent=2)
        elif out_path.endswith(".xml"):
            with open(out_path, "w", encoding="utf-8") as handle:
                handle.write(
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                )
                for item in urls:
                    handle.write(f"  <url><loc>{item}</loc></url>\n")
                handle.write("</urlset>")
        else:
            with open(out_path, "w", encoding="utf-8") as handle:
                for item in urls:
                    handle.write(f"{item}\n")

        console.print(
            PanelCls(
                f"[green]Sitemap Tree saved to:[/green] {out_path} ({len(urls)} URLs)",
                title="Success",
            )
        )
        return

    if args.playbook:
        try:
            console.print(
                PanelCls(
                    f"[bold cyan]Launching Autonomous Playbook:[/bold cyan] {args.playbook}",
                    title="System Startup",
                )
            )
            with open(args.playbook, "r", encoding="utf-8") as handle:
                playbook_data = json_module.load(handle)
            playbook = PlaybookCls(**playbook_data)

            manager = None
            proxie_cfg_dict = global_config.get("proxie", {})
            proxie_config = ProxieConfigCls.from_dict(proxie_cfg_dict)

            proxy_file = os_module.environ.get("PROXY_FILE", "proxies.json")
            if os_module.path.exists(proxy_file) and not args.no_proxy:
                manager = ProxyManagerCls(proxie_config)
                manager.load_proxies_from_json(proxy_file)
                proxy_count = len(manager.proxies)
                if proxy_count == 0:
                    manager = None
                    console.print(
                        "[yellow]Proxy file found but no valid proxies were loaded. "
                        "Falling back to direct mode.[/yellow]"
                    )
                else:
                    console.print(
                        f"[green]Proxy System Active: Loaded {proxy_count} proxies.[/green]"
                    )
            else:
                msg = "Running in Direct (No-Proxy) Mode."
                if args.no_proxy:
                    msg += " (Forced by --no-proxy)"
                elif not os_module.path.exists(proxy_file):
                    msg += " (No proxies.json found)"
                console.print(f"[dim]{msg}[/dim]")

            crawler = AutonomousCrawlerCls(playbook, proxy_manager=manager)
            await crawler.run()
            console.print(
                PanelCls(
                    f"[bold green]Playbook Completed![/bold green]\nResults saved to: {crawler.results_filename}",
                    title="Success",
                )
            )
            return
        except Exception as exc:
            console.print(f"[bold red]Playbook Failed:[/bold red] {exc}")
            logger.exception("Playbook execution failed")
            sys_module.exit(1)

    worker_request = args.workers or runtime_settings.concurrency.cli_workers_default
    worker_count = resolve_worker_count_fn(
        worker_request,
        cpu_reserve=runtime_settings.concurrency.cpu_reserve,
        max_workers=runtime_settings.concurrency.cli_workers_max,
        fallback=1,
    )

    if args.diagnostics:
        print_diagnostics_fn()
        return

    target_urls = []
    if args.url:
        target_urls.append(args.url)
    elif args.input:
        target_urls = await load_urls_from_source_fn(args.input)
        console.print(f"[dim]Loaded {len(target_urls)} URLs from source[/dim]")
        if not target_urls and args.input.startswith("http"):
            if "sitemap" not in args.input and not args.input.endswith(".xml"):
                console.print(
                    "[yellow]⚠️  Input looked like a webpage URL but not a sitemap.[/yellow]"
                )
                console.print("   Use --url for single pages.")

    if not target_urls and not args.host_profile_host:
        console.print("[bold red]No URLs found to process.[/bold red]")
        sys_module.exit(1)

    browser_defaults = global_config.get("browser", {})
    final_headless = args.headless or browser_defaults.get("headless", False)
    browser_merged = dict(browser_defaults)
    browser_merged["headless"] = final_headless
    browser_merged["browser_type"] = browser_defaults.get("browser_type", "chromium")
    browser_merged["timeout"] = browser_defaults.get("timeout", 30000)

    if args.native_fallback_policy is not None:
        browser_merged["native_fallback_policy"] = args.native_fallback_policy
    if args.native_browser_channels is not None:
        browser_merged["native_browser_channels"] = args.native_browser_channels
    if args.native_browser_headless:
        browser_merged["native_browser_headless"] = True
    if args.native_context_mode is not None:
        browser_merged["native_context_mode"] = args.native_context_mode
    if args.native_profile_dir is not None:
        browser_merged["native_profile_dir"] = args.native_profile_dir
    if args.interactive_channel is not None:
        browser_merged["interactive_channel"] = args.interactive_channel
    if args.interactive_context_mode is not None:
        browser_merged["interactive_context_mode"] = args.interactive_context_mode
    if args.interactive_profile_dir is not None:
        browser_merged["interactive_profile_dir"] = args.interactive_profile_dir
    if args.host_profiles_file is not None:
        browser_merged["host_profiles_path"] = args.host_profiles_file
    if args.host_profiles_read_only is not None:
        browser_merged["host_profiles_read_only"] = args.host_profiles_read_only == "on"
    if args.host_learning is not None:
        browser_merged["host_learning_enabled"] = args.host_learning == "on"
    if args.host_learning_threshold is not None and args.host_learning_threshold > 0:
        browser_merged["host_learning_promotion_threshold"] = (
            args.host_learning_threshold
        )

    b_config = BrowserConfigCls.from_dict(browser_merged)

    if args.host_profile_host:
        from ..browser.host_profiles import HostProfileStore

        profile_store = HostProfileStore(
            path=b_config.host_profiles_path,
            promotion_threshold=b_config.host_learning_promotion_threshold,
            apply_mode=b_config.host_learning_apply_mode,
        )
        try:
            if args.host_profile_json:
                profile_payload = json_module.loads(args.host_profile_json)
                if not isinstance(profile_payload, dict):
                    raise ValueError(
                        "--host-profile-json must decode to a JSON object."
                    )
                active = profile_store.set_host_profile(
                    args.host_profile_host,
                    profile_payload,
                )
                console.print(
                    PanelCls(
                        json_module.dumps(
                            {
                                "host": args.host_profile_host,
                                "active": active,
                                "profiles_path": b_config.host_profiles_path,
                            },
                            indent=2,
                        ),
                        title="Host Profile Updated",
                    )
                )
            else:
                snapshot = profile_store.export_profiles(host=args.host_profile_host)
                console.print(
                    PanelCls(
                        json_module.dumps(snapshot, indent=2),
                        title="Host Profile Snapshot",
                    )
                )
        except Exception as exc:
            console.print(f"[bold red]Host profile command failed:[/bold red] {exc}")
            sys_module.exit(1)

        if not target_urls:
            return

    if args.verbose:
        config_table = TableCls(
            title="Active Configuration", show_header=True, header_style="bold magenta"
        )
        config_table.add_column("Key", style="cyan")
        config_table.add_column("Value", style="green")
        config_table.add_row("Workers", str(worker_count))
        config_table.add_row("Delay", str(args.delay))
        config_table.add_row("Headless", str(b_config.headless))
        config_table.add_row("Native Fallback", str(b_config.native_fallback_policy))
        config_table.add_row(
            "Native Channels", ",".join(b_config.native_browser_channels)
        )
        config_table.add_row("Native Context", b_config.native_context_mode)
        config_table.add_row("Host Profiles", str(b_config.host_profiles_enabled))
        config_table.add_row(
            "Host Profiles ReadOnly", str(b_config.host_profiles_read_only)
        )
        config_table.add_row("Host Learning", str(b_config.host_learning_enabled))
        config_table.add_row(
            "Host Learn Threshold", str(b_config.host_learning_promotion_threshold)
        )
        config_table.add_row("Output Dir", args.output_dir)
        console.print(config_table)

    crawler = WebCrawlerCls(config=b_config, workers=worker_count, delay=args.delay)
    await crawler.run(
        urls=target_urls,
        output_format=args.format,
        export=args.export,
        merge=args.merge,
        output_dir=args.output_dir,
        temp_dir=args.temp_dir,
        clean=args.clean,
        output_filename=args.output_name,
        extract_contacts=args.contacts,
    )
