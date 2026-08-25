"""Single source of truth for pre-deployment compilation and focused tests."""

from __future__ import annotations

# Historical modules remain compiled so stale code cannot silently rot, but only
# the modules installed by run_with_env.py participate in the live runtime.
COMPILE_MODULES = (
    # spy_scanner.py removed - Phase 3 purge, owner-authorized (deleted along
    # with the old 15-strategy roster it implemented).
    "discord_command_bot_public.py",
    "local_information_engine_bootstrap.py",
    # local_information_engine_public.py removed - Phase 3 purge, same basis
    # as spy_scanner.py above: its Discord-dashboard visibility layer required
    # discover()-based channel resolution that was purged with spy_scanner.py.
    "run_with_env.py",
    "runtime_contract.py",
    "single_owner_runtime.py",
    "ngrok_process_runtime.py",
    "tradysquid_supervisor.py",
    "run_supervisor_simple.py",
    "clean_rebuild_auto_handoff.py",
    "network_compat.py",
    "github_upgrade_bridge.py",
    "github_upgrade_bridge_runtime.py",
    "shared_upgrade_lifecycle.py",
    "upgrade_batch_44.py",
    "diagnostic_upgrade_system.py",
    "diagnostic_startup_runtime.py",
    "diagnostic_state_migration.py",
    "diagnostic_review_runtime.py",
    "outbound_connectivity_runtime.py",
    "supervisor_diagnostic_runtime.py",
    "scheduler_diagnostic_runtime.py",
    "market_calendar_runtime.py",
)

FOCUSED_TEST_MODULES = (
    "test_deployment_validation_manifest.py",
    "test_github_upgrade_bridge.py",
    "test_github_upgrade_bridge_runtime.py",
    "test_supervisor_availability.py",
    "test_supervisor_entrypoint_diagnostics.py",
    "test_runtime_contract.py",
    "test_single_owner_runtime.py",
    "test_ngrok_process_runtime.py",
    "test_runtime_state_hygiene.py",
    "test_visible_manual_installer.py",
    "test_diagnostic_upgrade_system.py",
    "test_diagnostic_startup_runtime.py",
    "test_diagnostic_state_migration.py",
    "test_diagnostic_review_runtime.py",
    "test_outbound_connectivity_runtime.py",
    "test_supervisor_diagnostic_runtime.py",
    "test_scheduler_diagnostic_runtime.py",
    "test_market_calendar_runtime.py",
)


def validate_manifest() -> dict[str, object]:
    if len(COMPILE_MODULES) != len(set(COMPILE_MODULES)):
        raise RuntimeError("Deployment compile manifest contains duplicates")
    if len(FOCUSED_TEST_MODULES) != len(set(FOCUSED_TEST_MODULES)):
        raise RuntimeError("Deployment test manifest contains duplicates")
    required_modules = {
        "run_with_env.py",
        "runtime_contract.py",
        "single_owner_runtime.py",
        "ngrok_process_runtime.py",
        "run_supervisor_simple.py",
        "clean_rebuild_auto_handoff.py",
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
        "test_single_owner_runtime.py",
        "test_ngrok_process_runtime.py",
        "test_visible_manual_installer.py",
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
        "single_owner_guard_tested": True,
        "direct_ngrok_process_tested": True,
        "automatic_handoff_tested": True,
        "visible_manual_installer_tested": True,
    }
