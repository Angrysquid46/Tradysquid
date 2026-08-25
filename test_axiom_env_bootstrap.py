"""Real tests for bots/claude/env_bootstrap.py - the import-order-safe
.env loader AXIOM's entry points use instead of the frozen run_with_env.py
(which structurally can't target anything under bots/claude/)."""

from __future__ import annotations

import os

import bots.claude.env_bootstrap as env_bootstrap


def test_load_env_sets_variables_from_a_real_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("AXIOM_TEST_VAR=hello\n# a comment\n\nAXIOM_TEST_VAR2=world\n", encoding="utf-8")
    monkeypatch.setattr(env_bootstrap, "ENV_PATH", env_file)
    monkeypatch.delenv("AXIOM_TEST_VAR", raising=False)
    monkeypatch.delenv("AXIOM_TEST_VAR2", raising=False)

    env_bootstrap.load_env()

    assert os.environ["AXIOM_TEST_VAR"] == "hello"
    assert os.environ["AXIOM_TEST_VAR2"] == "world"


def test_load_env_does_not_raise_when_env_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(env_bootstrap, "ENV_PATH", tmp_path / "nonexistent.env")
    env_bootstrap.load_env()  # must not raise - CI has no .env file at all


def test_load_env_skips_blank_lines_and_comments(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\n\nAXIOM_TEST_VAR3=value\n", encoding="utf-8")
    monkeypatch.setattr(env_bootstrap, "ENV_PATH", env_file)
    monkeypatch.delenv("AXIOM_TEST_VAR3", raising=False)

    env_bootstrap.load_env()

    assert os.environ["AXIOM_TEST_VAR3"] == "value"
