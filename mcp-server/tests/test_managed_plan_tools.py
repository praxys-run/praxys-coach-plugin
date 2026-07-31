"""Managed-plan MCP contract tests with no private-repository dependency."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest import mock

from requests import Timeout


SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
PLUGIN_ROOT = SERVER_PATH.parents[1]


class _FakeFastMCP:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def tool(self):
        return lambda function: function


def _load_server():
    mcp_module = ModuleType("mcp")
    mcp_server_module = ModuleType("mcp.server")
    fastmcp_module = ModuleType("mcp.server.fastmcp")
    fastmcp_module.FastMCP = _FakeFastMCP
    module_name = "praxys_managed_plan_server_test"
    spec = importlib.util.spec_from_file_location(module_name, SERVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with (
        mock.patch.dict(
            os.environ,
            {"PRAXYS_LOCAL": "0", "TRAINSIGHT_LOCAL": "0"},
        ),
        mock.patch.dict(
            sys.modules,
            {
                "mcp": mcp_module,
                "mcp.server": mcp_server_module,
                "mcp.server.fastmcp": fastmcp_module,
                module_name: module,
            },
        ),
    ):
        spec.loader.exec_module(module)
    return module


def _settings(
    *,
    mode: str = "praxys",
    delivery_enabled: bool = True,
) -> dict:
    return {
        "config": {
            "plan_management": {
                "mode": mode,
                "execution_target": "stryd",
                "delivery_enabled": delivery_enabled,
                "adjustment_policy": "suggest_only",
            },
        },
        "connection_statuses": {
            "stryd": "connected",
            "garmin": "disconnected",
        },
        "platform_capabilities": {
            "stryd": {"plan": True},
            "garmin": {"plan": False},
        },
    }


def _plan() -> dict:
    return {
        "window": {"start": "2026-08-01", "end": "2026-08-14"},
        "sync_target": "stryd",
        "workouts": [
            {
                "date": "2026-08-01",
                "source": "ai",
                "owner": "praxys",
                "workout_type": "easy",
                "canonical_id": "canonical-1",
                "reconciliation": {
                    "id": "stryd:canonical-1@generation-1",
                    "state": "target_edited",
                    "conflict": True,
                    "resolutions": ["restore_praxys", "accept_target"],
                },
            },
            {
                "date": "2026-08-02",
                "source": "stryd",
                "owner": "external",
                "workout_type": "tempo",
            },
        ],
    }


class ManagedPlanToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = _load_server()

    def test_save_training_plan_is_authoring_and_push_alias_is_explicit(self) -> None:
        response = {"status": "saved", "rows": 1, "mode": "merge"}
        with (
            mock.patch.object(self.server, "IS_REMOTE", True),
            mock.patch.object(
                self.server,
                "_remote_post",
                return_value=response,
            ) as remote_post,
        ):
            saved = json.loads(
                self.server.save_training_plan(
                    "date,workout_type\n2026-08-01,easy",
                    mode="merge",
                ),
            )
            legacy = json.loads(
                self.server.push_training_plan(
                    "date,workout_type\n2026-08-01,easy",
                    mode="merge",
                ),
            )

        self.assertEqual(saved["operation"], "plan_authoring")
        self.assertFalse(saved["direct_delivery_requested"])
        self.assertNotIn("deprecated_tool", saved)
        self.assertEqual(legacy["operation"], "plan_authoring")
        self.assertIn("save_training_plan", legacy["deprecated_tool"])
        self.assertEqual(
            remote_post.call_args_list,
            [
                mock.call(
                    "/api/plan/upload?mode=merge",
                    {"csv": "date,workout_type\n2026-08-01,easy"},
                ),
                mock.call(
                    "/api/plan/upload?mode=merge",
                    {"csv": "date,workout_type\n2026-08-01,easy"},
                ),
            ],
        )

    def test_managed_plan_status_matches_in_remote_and_local_modes(self) -> None:
        settings = _settings()
        plan = _plan()

        def remote_get(path: str) -> dict:
            return settings if path == "/api/settings" else plan

        with (
            mock.patch.object(self.server, "IS_REMOTE", True),
            mock.patch.object(
                self.server,
                "_remote_get",
                side_effect=remote_get,
            ) as remote_get_mock,
        ):
            remote = json.loads(self.server.get_managed_plan_status(days=14))

        with (
            mock.patch.object(self.server, "IS_REMOTE", False),
            mock.patch.object(
                self.server,
                "_local_get_settings",
                return_value=settings,
            ),
            mock.patch.object(
                self.server,
                "_local_get_plan",
                return_value=plan,
            ),
        ):
            local = json.loads(self.server.get_managed_plan_status(days=14))

        self.assertEqual(remote, local)
        self.assertEqual(remote["plan_management"]["mode"], "praxys")
        self.assertEqual(remote["execution_target_status"], "connected")
        self.assertEqual(remote["available_execution_targets"], ["stryd"])
        self.assertEqual(
            remote["summary"],
            {
                "praxys_workouts": 1,
                "external_workouts": 1,
                "conflicts": 1,
            },
        )
        self.assertEqual(remote["workouts"][0]["reconciliation"]["id"], (
            "stryd:canonical-1@generation-1"
        ))
        calls = [call.args[0] for call in remote_get_mock.call_args_list]
        self.assertEqual(calls[0], "/api/settings")
        self.assertTrue(calls[1].startswith("/api/plan?start="))
        self.assertIn("&end=", calls[1])

    def test_lifecycle_tools_use_managed_settings_contract(self) -> None:
        external = _settings(mode="external", delivery_enabled=False)
        active = _settings()
        paused = _settings(delivery_enabled=False)
        responses = {
            "adopt": _settings(),
            "pause": paused,
            "resume": active,
            "leave": external,
        }

        with (
            mock.patch.object(self.server, "IS_REMOTE", True),
            mock.patch.object(
                self.server,
                "_remote_get",
                side_effect=[
                    external,
                    active,
                    paused,
                    active,
                ],
            ),
            mock.patch.object(
                self.server,
                "_remote_put",
                side_effect=[
                    responses["adopt"],
                    responses["pause"],
                    responses["resume"],
                    responses["leave"],
                ],
            ) as remote_put,
        ):
            adopted = json.loads(
                self.server.adopt_managed_plan(
                    "stryd",
                    "2026-08-01",
                    "2026-08-14",
                ),
            )
            paused_result = json.loads(self.server.pause_managed_plan())
            resumed = json.loads(
                self.server.resume_managed_plan(
                    "2026-08-01",
                    "2026-08-14",
                ),
            )
            left = json.loads(self.server.leave_managed_plan())

        self.assertEqual(adopted["operation"], "adopt")
        self.assertEqual(paused_result["operation"], "pause")
        self.assertEqual(resumed["operation"], "resume")
        self.assertEqual(left["operation"], "leave")
        adopt_payload = remote_put.call_args_list[0].args[1]
        self.assertEqual(
            adopt_payload["plan_management"],
            {
                "mode": "praxys",
                "execution_target": "stryd",
                "delivery_enabled": True,
                "adjustment_policy": "suggest_only",
            },
        )
        self.assertEqual(
            adopt_payload["managed_plan_preview_start"],
            "2026-08-01",
        )
        self.assertEqual(
            remote_put.call_args_list[1],
            mock.call(
                "/api/settings",
                {"plan_management": {"delivery_enabled": False}},
            ),
        )
        self.assertEqual(
            remote_put.call_args_list[3],
            mock.call(
                "/api/settings",
                {
                    "plan_management": {
                        "mode": "external",
                        "delivery_enabled": False,
                    },
                },
            ),
        )

    def test_leave_reports_partial_cleanup_and_supports_retry(self) -> None:
        active = _settings()
        external = _settings(mode="external", delivery_enabled=False)
        cleanup = {
            "status": "complete",
            "removed_count": 2,
            "remaining_count": 0,
            "target": "stryd",
        }
        with (
            mock.patch.object(self.server, "IS_REMOTE", True),
            mock.patch.object(
                self.server,
                "_remote_get",
                side_effect=[active, external],
            ),
            mock.patch.object(
                self.server,
                "_remote_put",
                return_value=external,
            ),
            mock.patch.object(
                self.server,
                "_remote_post",
                side_effect=[
                    Timeout("delete timed out"),
                    cleanup,
                ],
            ) as remote_post,
        ):
            left = json.loads(
                self.server.leave_managed_plan(
                    remove_future_deliveries=True,
                ),
            )
            retried = json.loads(
                self.server.cleanup_managed_plan_deliveries(),
            )

        self.assertEqual(left["status"], "partial")
        self.assertEqual(left["plan_management"]["mode"], "external")
        self.assertIn("delete timed out", left["cleanup"]["message"])
        self.assertEqual(retried["status"], "complete")
        self.assertEqual(
            remote_post.call_args_list,
            [
                mock.call(
                    "/api/plan/deliveries/cleanup",
                    {"scope": "future"},
                ),
                mock.call(
                    "/api/plan/deliveries/cleanup",
                    {"scope": "future"},
                ),
            ],
        )

    def test_pause_result_matches_in_remote_and_local_modes(self) -> None:
        active = _settings()
        paused = _settings(delivery_enabled=False)
        with (
            mock.patch.object(self.server, "IS_REMOTE", True),
            mock.patch.object(
                self.server,
                "_remote_get",
                return_value=active,
            ),
            mock.patch.object(
                self.server,
                "_remote_put",
                return_value=paused,
            ),
        ):
            remote = json.loads(self.server.pause_managed_plan())

        with (
            mock.patch.object(self.server, "IS_REMOTE", False),
            mock.patch.object(
                self.server,
                "_local_get_settings",
                return_value=active,
            ),
            mock.patch.object(
                self.server,
                "_local_update_settings",
                return_value=paused,
            ),
        ):
            local = json.loads(self.server.pause_managed_plan())

        self.assertEqual(remote, local)

    def test_adoption_requires_the_exact_reviewed_14_day_window(self) -> None:
        with (
            mock.patch.object(self.server, "IS_REMOTE", True),
            mock.patch.object(self.server, "_remote_get") as remote_get,
            mock.patch.object(self.server, "_remote_put") as remote_put,
        ):
            invalid = json.loads(
                self.server.adopt_managed_plan(
                    "stryd",
                    "2026-08-01",
                    "2026-08-13",
                ),
            )

        self.assertEqual(invalid["status"], "error")
        self.assertIn("14-day", invalid["message"])
        remote_get.assert_not_called()
        remote_put.assert_not_called()

    def test_generic_settings_cannot_bypass_managed_lifecycle(self) -> None:
        with (
            mock.patch.object(self.server, "IS_REMOTE", True),
            mock.patch.object(self.server, "_remote_put") as remote_put,
        ):
            blocked = json.loads(self.server.update_settings({
                "plan_management": {
                    "mode": "praxys",
                    "delivery_enabled": True,
                },
            }))

        self.assertEqual(blocked["status"], "error")
        self.assertIn("dedicated lifecycle tools", blocked["message"])
        remote_put.assert_not_called()

        ordinary = {"status": "ok", "config": {"training_base": "power"}}
        with (
            mock.patch.object(self.server, "IS_REMOTE", False),
            mock.patch.object(
                self.server,
                "_local_update_settings",
                return_value=ordinary,
            ) as local_update,
        ):
            updated = json.loads(
                self.server.update_settings({"training_base": "power"}),
            )

        self.assertEqual(updated, ordinary)
        local_update.assert_called_once_with({"training_base": "power"})

    def test_conflict_resolution_uses_opaque_id_and_whitelisted_action(self) -> None:
        resolved = {
            "status": "resolved",
            "action": "accept_target",
            "reconciliation_id": "stryd:canonical-1@generation-1",
        }
        with (
            mock.patch.object(self.server, "IS_REMOTE", True),
            mock.patch.object(
                self.server,
                "_remote_post",
                return_value=resolved,
            ) as remote_post,
        ):
            result = json.loads(
                self.server.resolve_managed_plan_conflict(
                    "stryd:canonical-1@generation-1",
                    "accept_target",
                ),
            )
            invalid = json.loads(
                self.server.resolve_managed_plan_conflict(
                    "stryd:canonical-1@generation-1",
                    "overwrite",
                ),
            )

        self.assertEqual(result, resolved)
        self.assertEqual(invalid["status"], "error")
        self.assertEqual(
            remote_post.call_args_list,
            [
                mock.call(
                    "/api/plan/reconciliation/resolve",
                    {
                        "reconciliation_id": (
                            "stryd:canonical-1@generation-1"
                        ),
                        "action": "accept_target",
                    },
                ),
            ],
        )

    def test_skills_use_authoring_and_managed_delivery_terms(self) -> None:
        training_plan = (
            PLUGIN_ROOT / "skills" / "training-plan" / "SKILL.md"
        ).read_text(encoding="utf-8")
        setup = (
            PLUGIN_ROOT / "skills" / "setup" / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("call `save_training_plan`", training_plan)
        self.assertIn(
            "`push_training_plan` is a backward-compatible alias",
            training_plan,
        )
        self.assertIn("Call `get_managed_plan_status`", setup)
        self.assertIn("Manual workouts", setup)


if __name__ == "__main__":
    unittest.main()
