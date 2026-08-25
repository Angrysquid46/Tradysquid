from bots.blacktide.engine import BLACKTIDE
from bots.blacktide.evolution import EvolutionLoop, Outcome


def outcome(i, value):
    return Outcome(f"t{i}", 1, value * 100, value, "IGNITION_TRANSITION",
                   "IGNITION", f"2026-08-25T10:{i:02d}:00")


def test_outcomes_are_append_only_and_duplicate_rejected(tmp_path):
    loop = EvolutionLoop(tmp_path / "outcomes.jsonl")
    loop.record(outcome(1, .1))
    try:
        loop.record(outcome(1, .2))
        assert False
    except ValueError:
        pass
    assert loop.load() == [outcome(1, .1)]


def test_evolution_requires_minimum_chronological_sample(tmp_path):
    loop = EvolutionLoop(tmp_path / "outcomes.jsonl")
    for i in range(29):
        loop.record(outcome(i, .01))
    receipt = loop.evaluate(BLACKTIDE())
    assert receipt["decision"] == "REJECT"
    assert "minimum sample" in receipt["reason"]


def test_evolution_receipt_contains_every_guard_stage(tmp_path):
    loop = EvolutionLoop(tmp_path / "outcomes.jsonl")
    for i in range(40):
        loop.record(outcome(i, .02 if i % 3 else -.01))
    receipt = loop.evaluate(BLACKTIDE())
    assert receipt["stages"] == loop.stages
    assert receipt["decision"] in ("PROMOTE", "REJECT")
