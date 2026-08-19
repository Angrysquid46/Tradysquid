"""validate() must not depend on where the dashboard spec sits in the list.

Real incident: the check read

    if CHANNEL_NAME not in INFRA_SPECS[-1].channels:

which silently assumed the applied-upgrades dashboard would remain the
newest infra spec forever. Appending spy-technicals-visibility made
INFRA_SPECS[-1] a spec that verifies 'spy-technicals', so validate()
raised "Applied-upgrades dashboard does not verify its own channel".

That matters far beyond this module: validate() runs inside deployment
validation, so EVERY deploy failed its check and was rolled back no
matter what the commit changed. Deploys were only reaching production
because the watchdog relaunches the stack against whatever is already in
the working tree, bypassing the validated path entirely.
"""

from __future__ import annotations

import dataclasses

import pytest

import applied_upgrades as au


def test_validate_passes_as_shipped():
    payload = au.validate()
    assert payload["version"] == au.VERSION


def test_the_dashboard_spec_actually_verifies_its_own_channel():
    dashboard = next(
        (s for s in au.INFRA_SPECS if s.key == au.DASHBOARD_SPEC_KEY), None
    )
    assert dashboard is not None, "the dashboard's own spec vanished from the catalog"
    assert au.CHANNEL_NAME in dashboard.channels


def test_appending_a_newer_infra_spec_does_not_break_validate(monkeypatch):
    """The exact regression: a new spec appended after the dashboard.

    This is what spy-technicals-visibility did.
    """
    newest = dataclasses.replace(
        au.INFRA_SPECS[-1],
        key="some-future-spec",
        channels=("some-future-channel",),
    )

    monkeypatch.setattr(au, "INFRA_SPECS", list(au.INFRA_SPECS) + [newest])
    au.validate()   # must not raise


def test_validate_still_fails_if_the_dashboard_stops_verifying_its_channel(monkeypatch):
    """The check must keep doing its real job, not just stop complaining."""
    specs = [
        dataclasses.replace(
            s, channels=tuple(c for c in s.channels if c != au.CHANNEL_NAME)
        )
        if s.key == au.DASHBOARD_SPEC_KEY
        else s
        for s in au.INFRA_SPECS
    ]

    monkeypatch.setattr(au, "INFRA_SPECS", specs)
    with pytest.raises(RuntimeError, match="does not verify its own channel"):
        au.validate()


def test_validate_fails_loudly_if_the_dashboard_spec_is_removed(monkeypatch):
    specs = [s for s in au.INFRA_SPECS if s.key != au.DASHBOARD_SPEC_KEY]
    monkeypatch.setattr(au, "INFRA_SPECS", specs)
    with pytest.raises(RuntimeError, match="is missing"):
        au.validate()
