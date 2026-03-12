# ./tests/test_host_profiles.py
"""
Unit tests for host profile learning and BrowserConfig compatibility behavior.
Run with `python -m pytest -q tests/test_host_profiles.py`.
Inputs: temp profile-store paths plus deterministic routing/outcome fixtures.
Outputs: assertions over schema, promotion/demotion, and config field roundtrip.
Side effects: writes temporary host profile JSON files under temp directories.
Operational notes: validates clean-incognito promotion rules and persistent-run exclusion.
"""

import os
import tempfile
import unittest

from web_scraper_toolkit.browser.config import BrowserConfig
from web_scraper_toolkit.browser.host_profiles import HostProfileStore


class TestBrowserConfigCompatibility(unittest.TestCase):
    def test_from_dict_preserves_stealth_serp_and_host_learning_fields(self) -> None:
        cfg = BrowserConfig.from_dict(
            {
                "headless": False,
                "browser_type": "chrome",
                "stealth_mode": True,
                "stealth_profile": "experimental_serp",
                "serp_strategy": "native_first",
                "serp_retry_policy": "balanced",
                "serp_retry_backoff_seconds": 9.5,
                "serp_allowlist_only": False,
                "serp_debug_capture_headers": True,
                "native_fallback_policy": "on_blocked",
                "native_browser_channels": "chrome,msedge",
                "host_profiles_enabled": True,
                "host_profiles_path": "./tmp_host_profiles.json",
                "host_profiles_read_only": True,
                "host_learning_enabled": True,
                "host_learning_apply_mode": "safe_subset",
                "host_learning_promotion_threshold": 2,
            }
        )
        payload = cfg.to_dict()
        self.assertEqual(cfg.stealth_profile, "experimental_serp")
        self.assertEqual(cfg.serp_strategy, "native_first")
        self.assertEqual(cfg.serp_retry_policy, "balanced")
        self.assertFalse(cfg.serp_allowlist_only)
        self.assertTrue(cfg.serp_debug_capture_headers)
        self.assertTrue(cfg.host_profiles_enabled)
        self.assertTrue(cfg.host_profiles_read_only)
        self.assertTrue(cfg.host_learning_enabled)
        self.assertEqual(cfg.host_learning_apply_mode, "safe_subset")
        self.assertEqual(cfg.host_learning_promotion_threshold, 2)
        self.assertEqual(cfg.browser_type, "chrome")
        self.assertEqual(payload["host_profiles_path"], "./tmp_host_profiles.json")

    def test_browser_default_prefers_chromium(self) -> None:
        cfg = BrowserConfig()
        self.assertEqual(cfg.browser_type, "chromium")


class TestHostProfileStore(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store_path = os.path.join(self.temp_dir.name, "host_profiles.json")
        self.store = HostProfileStore(path=self.store_path, promotion_threshold=2)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_default_schema(self) -> None:
        snapshot = self.store.export_profiles()
        self.assertEqual(snapshot["version"], 1)
        self.assertIn("defaults", snapshot)
        self.assertIn("hosts", snapshot)

    def test_set_and_reload_host_profile(self) -> None:
        active = self.store.set_host_profile(
            "example.com",
            {
                "routing": {
                    "headless": False,
                    "stealth_mode": False,
                    "native_fallback_policy": "on_blocked",
                    "native_browser_channels": ["chrome", "msedge"],
                    "native_context_mode": "persistent",
                    "allow_headed_retry": True,
                    "serp_strategy": "none",
                    "serp_retry_policy": "none",
                    "serp_retry_backoff_seconds": 12.0,
                }
            },
        )
        self.assertEqual(active["routing"]["native_fallback_policy"], "on_blocked")
        self.assertFalse(active["routing"]["headless"])
        self.assertFalse(active["routing"]["stealth_mode"])
        self.assertEqual(active["routing"]["native_context_mode"], "persistent")

        reloaded = HostProfileStore(path=self.store_path, promotion_threshold=2)
        host_data = reloaded.export_profiles(host="example.com")["hosts"]["example.com"]
        self.assertIn("active", host_data)
        self.assertEqual(
            host_data["active"]["routing"]["native_browser_channels"],
            ["chrome", "msedge"],
        )
        self.assertFalse(host_data["active"]["routing"]["headless"])
        self.assertFalse(host_data["active"]["routing"]["stealth_mode"])
        self.assertEqual(
            host_data["active"]["routing"]["native_context_mode"],
            "persistent",
        )

    def test_candidate_promotes_after_two_clean_incognito_successes(self) -> None:
        routing = {
            "native_fallback_policy": "on_blocked",
            "native_browser_channels": ["chrome"],
            "allow_headed_retry": True,
            "serp_strategy": "none",
            "serp_retry_policy": "none",
            "serp_retry_backoff_seconds": 5.0,
        }
        self.store.record_attempt(
            host="example.com",
            routing=routing,
            success=True,
            blocked_reason="none",
            context_mode="incognito",
            had_persisted_state=False,
            promotion_eligible=True,
            run_id="run_1",
            final_url="https://example.com/company",
            status=200,
            used_active_profile=False,
        )
        first = self.store.export_profiles(host="example.com")["hosts"]["example.com"]
        self.assertIn("candidate", first)
        self.assertNotIn("active", first)
        self.assertEqual(
            first["candidate"]["evidence"]["clean_incognito_successes"],
            1,
        )

        self.store.record_attempt(
            host="example.com",
            routing=routing,
            success=True,
            blocked_reason="none",
            context_mode="incognito",
            had_persisted_state=False,
            promotion_eligible=True,
            run_id="run_2",
            final_url="https://example.com/company",
            status=200,
            used_active_profile=False,
        )
        second = self.store.export_profiles(host="example.com")["hosts"]["example.com"]
        self.assertIn("active", second)
        self.assertNotIn("candidate", second)

    def test_candidate_promotion_keeps_headed_no_stealth_winning_path(self) -> None:
        routing = {
            "headless": False,
            "stealth_mode": False,
            "native_fallback_policy": "on_blocked",
            "native_browser_channels": ["chrome"],
            "native_context_mode": "incognito",
        }
        for run_id in ("run_headed_1", "run_headed_2"):
            self.store.record_attempt(
                host="example.com",
                routing=routing,
                success=True,
                blocked_reason="none",
                context_mode="incognito",
                had_persisted_state=False,
                promotion_eligible=True,
                run_id=run_id,
                final_url="https://example.com/company",
                status=200,
                used_active_profile=False,
            )

        data = self.store.export_profiles(host="example.com")["hosts"]["example.com"]
        active_routing = data["active"]["routing"]
        self.assertFalse(active_routing["headless"])
        self.assertFalse(active_routing["stealth_mode"])
        self.assertEqual(active_routing["native_context_mode"], "incognito")

    def test_persistent_success_is_not_promotion_eligible(self) -> None:
        routing = {
            "native_fallback_policy": "on_blocked",
            "native_browser_channels": ["chrome"],
            "allow_headed_retry": True,
        }
        self.store.record_attempt(
            host="example.com",
            routing=routing,
            success=True,
            blocked_reason="none",
            context_mode="persistent",
            had_persisted_state=True,
            promotion_eligible=False,
            run_id="run_persistent",
            final_url="https://example.com/company",
            status=200,
            used_active_profile=False,
        )
        data = self.store.export_profiles(host="example.com")["hosts"]["example.com"]
        self.assertIn("candidate", data)
        self.assertEqual(
            data["candidate"]["evidence"]["clean_incognito_successes"],
            0,
        )
        self.assertEqual(
            data["candidate"]["evidence"]["persistent_successes"],
            1,
        )
        self.assertNotIn("active", data)

    def test_active_profile_demotes_after_three_clean_failures(self) -> None:
        self.store.set_host_profile(
            "example.com",
            {
                "native_fallback_policy": "on_blocked",
                "native_browser_channels": ["chrome"],
            },
        )
        routing = {
            "native_fallback_policy": "on_blocked",
            "native_browser_channels": ["chrome"],
        }
        for idx in range(3):
            self.store.record_attempt(
                host="example.com",
                routing=routing,
                success=False,
                blocked_reason="cf_challenge",
                context_mode="incognito",
                had_persisted_state=False,
                promotion_eligible=True,
                run_id=f"run_fail_{idx}",
                final_url="https://example.com/challenge",
                status=403,
                used_active_profile=True,
            )

        data = self.store.export_profiles(host="example.com")["hosts"]["example.com"]
        self.assertNotIn("active", data)
        self.assertIn("candidate", data)
        self.assertGreaterEqual(
            data["candidate"]["evidence"]["clean_incognito_failures"],
            3,
        )

    def test_domain_profile_applies_to_subdomains(self) -> None:
        self.store.set_host_profile(
            "example.com",
            {
                "routing": {
                    "native_fallback_policy": "on_blocked",
                    "native_browser_channels": ["chrome", "msedge"],
                }
            },
        )
        routing, has_profile, match = self.store.resolve_strategy_with_match(
            "https://app.example.com/company"
        )
        self.assertTrue(has_profile)
        self.assertEqual(routing["native_fallback_policy"], "on_blocked")
        self.assertEqual(match["match_key"], "example.com")
        self.assertEqual(match["match_scope"], "domain")

    def test_exact_host_profile_overrides_domain_profile(self) -> None:
        self.store.set_host_profile(
            "example.com",
            {
                "routing": {
                    "native_fallback_policy": "on_blocked",
                    "native_browser_channels": ["chrome"],
                }
            },
        )
        self.store.set_host_profile(
            "api.example.com",
            {
                "routing": {
                    "native_fallback_policy": "off",
                    "native_browser_channels": ["chromium"],
                }
            },
        )
        routing, has_profile, match = self.store.resolve_strategy_with_match(
            "api.example.com"
        )
        self.assertTrue(has_profile)
        self.assertEqual(routing["native_fallback_policy"], "off")
        self.assertEqual(match["match_key"], "api.example.com")
        self.assertEqual(match["match_scope"], "exact")

    def test_registrable_domain_for_multi_part_tld(self) -> None:
        learning_key, learning_scope = self.store.resolve_learning_target(
            "https://app.example.co.uk/path"
        )
        self.assertEqual(learning_key, "example.co.uk")
        self.assertEqual(learning_scope, "domain")

    def test_store_detects_external_file_mutation(self) -> None:
        self.store.set_host_profile(
            "example.com",
            {
                "routing": {
                    "native_fallback_policy": "on_blocked",
                    "native_browser_channels": ["chrome"],
                }
            },
        )
        external_store = HostProfileStore(path=self.store_path, promotion_threshold=2)
        external_store.demote_active("example.com")

        inspection = self.store.inspect_host("example.com")
        self.assertFalse(inspection["has_active_profile"])
        self.assertTrue(bool(inspection["candidate"]))


if __name__ == "__main__":
    unittest.main()
