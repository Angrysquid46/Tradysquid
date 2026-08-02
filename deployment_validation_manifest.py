"""Single source of truth for pre-deployment compilation and focused tests."""

from __future__ import annotations

# Historical modules remain compiled so stale code cannot silently rot, but only
# the modules installed by run_with_env.py participate in the live runtime.
COMPILE_MODULES = (
    "ford_scan.py",
    "discord_command_bot_public.py",
    "local_information_engine_bootstrap.py",
    "local_information_engine_public.py",
    "run_with_env.py",
    "tradysquid_supervisor.py",
    "run_supervisor_simple.py",
    "network_compat.py",
    "github_upgrade_bridge.py",
    "github_upgrade_bridge_runtime.py",
    "github_upgrade_patch.py",
    "shared_upgrade_lifecycle.py",
    "simple_upgrade_runtime.py",
    "upgrade_batch_44.py",
    "upgrade_batch_44_live_acceptance.py",
    "upgrade_lifecycle_dashboard.py",
    "diagnostic_upgrade_system.py",
    "diagnostic_runtime_integration.py",
    "diagnostic_startup_runtime.py",
    "diagnostic_nonblocking_runtime.py",
    "diagnostic_state_migration.py",
    "diagnostic_review_runtime.py",
    "outbound_connectivity_runtime.py",
    "discord_command_diagnostics.py",
    "supervisor_diagnostic_runtime.py",
    "scheduler_diagnostic_runtime.py",
    "market_calendar_runtime.py",
    "applied_upgrades.py",
    "applied_upgrade_status_runtime.py",
)

FOCUSED_TEST_MODULES = (
    "test_github_upgrade_bridge.py",
    "test_github_upgrade_bridge_runtime.py",
    "test_supervisor_availability.py",
    "test_supervisor_entrypoint_diagnostics.py",
    "test_runtime_contract.py",
    "test_runtime_state_hygiene.py",
    "test_applied_upgrades.py",
    "test_applied_upgrade_status_runtime.py",
    "test_simple_upgrade_flow.py",
    "test_diagnostic_upgrade_system.py",
    "test_diagnostic_startup_runtime.py",
    "test_diagnostic_nonblocking_runtime.py",
    "test_diagnostic_state_migration.py",
    "test_diagnostic_review_runtime.py",
    "test_outbound_connectivity_runtime.py",
    "test_discord_command_diagnostics.py",
    "test_supervisor_diagnostic_runtime.py",
    "test_scheduler_diagnostic_runtime.py",
    "test_upgrade_lifecycle_dashboard.py",
    "test_market_calendar_runtime.py",
)


def validate_manifest() -> dict[str, object]:
    if len(COMPILE_MODULES) != len(set(COMPILE_MODULES)):
        raise RuntimeError("Deployment compile manifest contains duplicates")
    if len(FOCUSED_TEST_MODULES) != len(set(FOCUSED_TEST_MODULES)):
        raise RuntimeError("Deployment test manifest contains duplicates")
    required_modules = {
        "ford_scan.py",
        "run_with_env.py",
        "run_supervisor_simple.py",
        "tradysquid_supervisor.py",
        "diagnostic_upgrade_system.py",
        "diagnostic_review_runtime.py",
        "outbound_connectivity_runtime.py",
        "supervisor_diagnostic_runtime.py",
        "scheduler_diagnostic_runtime.py",
        "market_calendar_runtime.py",
    }
    required_tests = {
        "test_runtime_contract.py",
        "test_simple_upgrade_flow.py",
        "test_diagnostic_upgrade_system.py",
        "test_diagnostic_review_runtime.py",
        "test_outbound_connectivity_runtime.py",
        "test_supervisor_diagnostic_runtime.py",
        "test_scheduler_diagnostic_runtime.py",
        "test_market_calendar_runtime.py",
        "test_supervisor_entrypoint_diagnostics.py",
    }
    missing_modules = sorted(required_modules - set(COMPILE_MODULES))
    missing_tests = sorted(required_tests - set(FOCUSED_TEST_MODULES))
    if missing_modules or missing_tests:
        raise RuntimeError(
            f"Deployment validation manifest incomplete: modules={missing_modules}; tests={missing_tests}"
        )
    return {
        "compile_modules": len(COMPILE_MODULES),
        "focused_tests": len(FOCUSED_TEST_MODULES),
        "required_modules_present": True,
        "required_tests_present": True,
        "runtime_contract_tested": True,
    }
