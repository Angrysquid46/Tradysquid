from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import discord_surface_manifest as manifest


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(manifest, "DB_PATH", Path(tempfile.mkdtemp()) / "surfaces.db")
    connection = manifest.connect_db()
    yield connection
    connection.close()


def _register(db, surface_id="scoreboard-card", *, update_mode="PERIODIC",
              expected_silence=False, max_silence_minutes=10, enabled=True):
    manifest.register_surface(
        db, surface_id=surface_id, category="COMPETITION", channel="scoreboard",
        owner="Claude", purpose="test", producer="scoreboard.py",
        publisher="discord_transport.py", update_mode=update_mode,
        expected_silence=expected_silence, max_silence_minutes=max_silence_minutes,
        enabled=enabled,
    )


# --- registration --------------------------------------------------------------

def test_register_surface_requires_max_silence_for_non_silent_periodic_surfaces(db):
    with pytest.raises(ValueError, match="max_silence_minutes"):
        manifest.register_surface(
            db, surface_id="x", category="C", channel="c", owner="Claude",
            purpose="p", producer="p", publisher="p", update_mode="PERIODIC",
            expected_silence=False,
        )


def test_register_surface_is_idempotent_upsert(db):
    _register(db)
    manifest.register_surface(
        db, surface_id="scoreboard-card", category="COMPETITION", channel="scoreboard",
        owner="Claude", purpose="updated purpose", producer="scoreboard.py",
        publisher="discord_transport.py", update_mode="PERIODIC",
        expected_silence=False, max_silence_minutes=10,
    )
    row = db.execute("SELECT purpose FROM surfaces WHERE surface_id=?", ("scoreboard-card",)).fetchone()
    assert row["purpose"] == "updated purpose"
    count = db.execute("SELECT COUNT(*) AS n FROM surfaces").fetchone()["n"]
    assert count == 1


def test_record_surface_event_rejects_unregistered_surface(db):
    with pytest.raises(ValueError, match="never registered"):
        manifest.record_surface_event(db, surface_id="ghost", event_type="PUBLISH")


def test_record_surface_event_rejects_unknown_event_type(db):
    _register(db)
    with pytest.raises(ValueError, match="Unknown event_type"):
        manifest.record_surface_event(db, surface_id="scoreboard-card", event_type="WHATEVER")


# --- compute_health: all eight states -----------------------------------------

def test_health_no_data_expected_when_disabled(db):
    _register(db, enabled=False)
    assert manifest.compute_health(db, "scoreboard-card") == manifest.NO_DATA_EXPECTED


def test_health_producer_offline_when_periodic_never_published(db):
    _register(db, update_mode="PERIODIC", expected_silence=False, max_silence_minutes=10)
    assert manifest.compute_health(db, "scoreboard-card") == manifest.PRODUCER_OFFLINE


def test_health_quiet_valid_when_event_driven_and_silence_is_expected(db):
    _register(db, surface_id="rivalry-card", update_mode="EVENT_DRIVEN", expected_silence=True)
    assert manifest.compute_health(db, "rivalry-card") == manifest.QUIET_VALID


def test_health_healthy_when_periodic_and_recently_published(db):
    _register(db)
    manifest.record_surface_event(db, surface_id="scoreboard-card", event_type="PUBLISH")
    assert manifest.compute_health(db, "scoreboard-card") == manifest.HEALTHY


def test_health_stale_when_periodic_and_overdue(db):
    _register(db, max_silence_minutes=10)
    manifest.record_surface_event(db, surface_id="scoreboard-card", event_type="PUBLISH")
    later = datetime.now().astimezone() + timedelta(minutes=20)
    assert manifest.compute_health(db, "scoreboard-card", now=later) == manifest.STALE


def test_health_healthy_when_periodic_but_silence_is_expected_regardless_of_age(db):
    _register(db, update_mode="PERIODIC", expected_silence=True)
    manifest.record_surface_event(db, surface_id="scoreboard-card", event_type="PUBLISH")
    much_later = datetime.now().astimezone() + timedelta(days=5)
    assert manifest.compute_health(db, "scoreboard-card", now=much_later) == manifest.HEALTHY


def test_health_publish_failed_after_an_error_event(db):
    _register(db)
    manifest.record_surface_event(db, surface_id="scoreboard-card", event_type="PUBLISH")
    manifest.record_surface_event(db, surface_id="scoreboard-card", event_type="ERROR", detail="429")
    assert manifest.compute_health(db, "scoreboard-card") == manifest.PUBLISH_FAILED


def test_health_healthy_for_event_driven_with_any_recorded_event(db):
    _register(db, surface_id="rivalry-card", update_mode="EVENT_DRIVEN", expected_silence=True)
    manifest.record_surface_event(db, surface_id="rivalry-card", event_type="EVENT")
    assert manifest.compute_health(db, "rivalry-card") == manifest.HEALTHY


def test_desynchronized_and_misconfigured_are_valid_states_but_never_auto_derived(db):
    _register(db)
    manifest.record_surface_event(db, surface_id="scoreboard-card", event_type="PUBLISH")
    assert manifest.compute_health(db, "scoreboard-card") not in (
        manifest.DESYNCHRONIZED, manifest.MISCONFIGURED,
    )
    assert manifest.DESYNCHRONIZED in manifest.HEALTH_STATES
    assert manifest.MISCONFIGURED in manifest.HEALTH_STATES


# --- set_surface_status / surface_snapshot -------------------------------------

def test_set_surface_status_round_trips(db):
    _register(db)
    manifest.set_surface_status(db, "scoreboard-card", "VERIFIED_UNAFFECTED")
    row = db.execute("SELECT status FROM surfaces WHERE surface_id=?", ("scoreboard-card",)).fetchone()
    assert row["status"] == "VERIFIED_UNAFFECTED"


def test_set_surface_status_accepts_desynchronized_and_misconfigured(db):
    """Phase 14 audit finding: HEALTH_STATES declares these two and the
    module's own docstring says set_surface_status is the manual route to
    record them, but SURFACE_STATUSES didn't actually include them."""
    _register(db)
    manifest.set_surface_status(db, "scoreboard-card", manifest.DESYNCHRONIZED)
    assert manifest.surface_snapshot(db, "scoreboard-card")["status"] == manifest.DESYNCHRONIZED
    manifest.set_surface_status(db, "scoreboard-card", manifest.MISCONFIGURED)
    assert manifest.surface_snapshot(db, "scoreboard-card")["status"] == manifest.MISCONFIGURED


def test_set_surface_status_rejects_unknown_status(db):
    _register(db)
    with pytest.raises(ValueError, match="Unknown surface status"):
        manifest.set_surface_status(db, "scoreboard-card", "MAYBE")


def test_set_surface_status_rejects_unregistered_surface(db):
    with pytest.raises(ValueError, match="never registered"):
        manifest.set_surface_status(db, "ghost", "RETIRED")


def test_surface_snapshot_bundles_declaration_and_health(db):
    _register(db)
    manifest.record_surface_event(db, surface_id="scoreboard-card", event_type="PUBLISH", detail="ok")
    snapshot = manifest.surface_snapshot(db, "scoreboard-card")
    assert snapshot["surface_id"] == "scoreboard-card"
    assert snapshot["health"] == manifest.HEALTHY
    assert snapshot["last_event_type"] == "PUBLISH"


def test_canonical_competition_reconciliation_retires_orphans(db):
    _register(db, surface_id="old-rivalry-card")
    db.execute("UPDATE surfaces SET category='RIVALRY' WHERE surface_id='old-rivalry-card'")
    db.commit()
    retired = manifest.reconcile_canonical_competition_surfaces(db)
    assert retired == ("old-rivalry-card",)
    rows = db.execute("SELECT surface_id, enabled, status FROM surfaces").fetchall()
    indexed = {row["surface_id"]: dict(row) for row in rows}
    assert set(indexed) >= {"competition-scoreboard-card", "competition-rivalry-card"}
    assert indexed["old-rivalry-card"]["enabled"] == 0
    assert indexed["old-rivalry-card"]["status"] == "RETIRED"
