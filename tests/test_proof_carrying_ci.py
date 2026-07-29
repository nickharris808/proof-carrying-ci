"""Tests for proof-carrying-ci.

The aggregation rule is the whole product, so most of these are about it. The rest are about the
two ways a CI integration lies: an empty SARIF that looks like a clean scan, and an exit code that
turns "could not check" into "checked and fine".
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from proof_carrying_ci import FAILED, PASSED, UNVERIFIED, Leg, Report, RunnerError, run_audit
from proof_carrying_ci.runner import _aggregate, to_markdown, to_sarif

PY = sys.executable


# ------------------------------------------------------------------ the aggregation rule

def test_the_aggregate_is_the_weakest_leg():
    agg = _aggregate([Leg("a", PASSED), Leg("b", PASSED), Leg("c", UNVERIFIED)], ".")
    assert agg.verdict == UNVERIFIED and agg.weakest == "c"


def test_failed_is_weaker_than_unverified():
    agg = _aggregate([Leg("a", UNVERIFIED), Leg("b", FAILED)], ".")
    assert agg.verdict == FAILED and agg.weakest == "b"


def test_no_number_of_passes_lifts_a_single_unverified():
    legs = [Leg(f"p{i}", PASSED) for i in range(50)] + [Leg("u", UNVERIFIED)]
    assert _aggregate(legs, ".").verdict == UNVERIFIED


def test_an_audit_over_zero_voting_legs_is_unverified():
    """`all([])` is True and this is exactly where that bug would land."""
    agg = _aggregate([Leg("a", PASSED, applicable=False),
                      Leg("b", PASSED, available=False)], ".")
    assert agg.verdict == UNVERIFIED
    assert agg.weakest is None
    assert any("not a pass" in n.lower() for n in agg.notes)


def test_an_audit_with_no_legs_at_all_is_unverified():
    assert _aggregate([], ".").verdict == UNVERIFIED


def test_na_and_missing_legs_do_not_vote():
    """Folding them in would make every repository permanently UNVERIFIED, and a warning nobody
    can clear is a warning everybody learns to ignore."""
    agg = _aggregate([Leg("a", PASSED), Leg("na", FAILED, applicable=False),
                      Leg("gone", FAILED, available=False)], ".")
    assert agg.verdict == PASSED


def test_exit_codes_follow_the_portfolio_dialect():
    assert Report(PASSED).exit_code == 0
    assert Report(FAILED).exit_code == 1
    assert Report(UNVERIFIED).exit_code == 2


# ------------------------------------------------------------------ fail-on

@pytest.mark.parametrize("verdict,fail_on,expect", [
    (PASSED, "failure", False), (FAILED, "failure", True), (UNVERIFIED, "failure", False),
    (PASSED, "unverified", False), (FAILED, "unverified", True), (UNVERIFIED, "unverified", True),
    (PASSED, "never", False), (FAILED, "never", False), (UNVERIFIED, "never", False),
])
def test_the_fail_on_matrix(verdict, fail_on, expect):
    assert Report(verdict).should_fail(fail_on) is expect


def test_the_default_does_not_redden_on_unverified_but_still_reports_it():
    """The deliberate tension, pinned. A red tick for 'a tool was missing' gets the check
    disabled; so the default stays green AND the verdict stays UNVERIFIED everywhere."""
    r = Report(UNVERIFIED, [Leg("x", UNVERIFIED)], "x")
    assert not r.should_fail("failure")
    assert r.verdict == UNVERIFIED
    assert r.to_dict()["verdict"] == UNVERIFIED
    assert "UNVERIFIED" in to_markdown(r)
    assert "UNVERIFIED" in to_sarif(r)


def test_an_invalid_fail_on_is_refused():
    r = subprocess.run([PY, "-m", "proof_carrying_ci.cli", "run", "--fail-on", "sometimes"],
                       capture_output=True, text=True)
    assert r.returncode == 2


# ------------------------------------------------------------------ SARIF

def test_sarif_emits_every_leg_including_the_passes():
    """An empty SARIF is indistinguishable from a run that checked nothing."""
    agg = _aggregate([Leg("a", PASSED), Leg("b", FAILED), Leg("c", UNVERIFIED)], ".")
    s = json.loads(to_sarif(agg))
    results = s["runs"][0]["results"]
    assert len(results) == 4                       # three legs plus the aggregate
    levels = {r["ruleId"]: r["level"] for r in results}
    assert levels["proof-carrying-ci/a"] == "note"
    assert levels["proof-carrying-ci/b"] == "error"
    assert levels["proof-carrying-ci/c"] == "warning"


def test_sarif_is_valid_json_and_declares_its_schema():
    s = json.loads(to_sarif(_aggregate([Leg("a", PASSED)], ".")))
    assert s["version"] == "2.1.0" and "$schema" in s
    assert s["runs"][0]["tool"]["driver"]["name"] == "proof-carrying-ci"


def test_a_missing_tool_is_a_warning_not_a_silent_omission():
    s = json.loads(to_sarif(_aggregate([Leg("a", PASSED), Leg("gone", PASSED, available=False)],
                                       ".")))
    gone = [r for r in s["runs"][0]["results"] if r["ruleId"].endswith("gone")][0]
    assert gone["level"] == "warning"
    assert "not installed" in gone["message"]["text"]


def test_the_aggregate_result_states_the_rule():
    s = json.loads(to_sarif(_aggregate([Leg("a", UNVERIFIED)], ".")))
    agg = [r for r in s["runs"][0]["results"] if r["ruleId"].endswith("aggregate")][0]
    assert "weakest leg, never the mean" in agg["message"]["text"]


# ------------------------------------------------------------------ markdown

def test_the_summary_is_actionable_for_someone_who_knows_none_of_the_tools():
    md = to_markdown(_aggregate([Leg("gridlock", FAILED, "cycle: a -> b -> a")], "."))
    assert "found a real defect" in md
    assert "gridlock" in md and "a -> b -> a" in md


def test_a_pipe_in_a_detail_cannot_break_the_table():
    md = to_markdown(_aggregate([Leg("x", FAILED, "a | b | c")], "."))
    row = [l for l in md.split("\n") if l.startswith("| `x`")][0]
    assert row.count("|") == 4 + 2, row      # 4 cell delimiters + the 2 escaped pipes
    assert "a \\| b \\| c" in row


# ------------------------------------------------------------------ the runner

def test_a_missing_directory_raises_rather_than_reporting_a_pass():
    with pytest.raises(RunnerError):
        run_audit("/definitely/not/a/real/path")


def test_without_evidence_installed_the_result_is_unverified(monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **kw):
        if name.split(".")[0] == "evidence":
            raise ImportError("blocked for the test")
        return real(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake)
    r = run_audit(".")
    assert r.verdict == UNVERIFIED
    assert any("NOTHING WAS CHECKED" in n for n in r.notes)


def test_a_real_audit_of_a_lock_inversion_fails(tmp_path):
    pytest.importorskip("evidence")
    pytest.importorskip("gridlock")
    src = tmp_path / "src"
    src.mkdir()
    (src / "pool.py").write_text(
        "import threading\n"
        "a = threading.Lock()\nb = threading.Lock()\n"
        "def f():\n    with a:\n        with b:\n            pass\n"
        "def g():\n    with b:\n        with a:\n            pass\n")
    r = run_audit(str(tmp_path))
    assert r.verdict == FAILED
    assert r.weakest and "gridlock" in r.weakest


# ------------------------------------------------------------------ CLI and Action

def _cli(*args, **kw):
    return subprocess.run([PY, "-m", "proof_carrying_ci.cli", *args], capture_output=True,
                          text=True, **kw)


def test_cli_selftest_passes():
    r = _cli("selftest")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "aggregation rule holds" in r.stdout


def test_cli_writes_sarif(tmp_path):
    out = tmp_path / "o.sarif"
    _cli("run", "--path", ".", "--sarif", str(out))
    assert out.exists()
    json.loads(out.read_text())


def test_cli_writes_github_outputs(tmp_path):
    gh = tmp_path / "gh_out"
    gh.write_text("")
    env = dict(os.environ, GITHUB_OUTPUT=str(gh))
    _cli("run", "--path", ".", env=env)
    body = gh.read_text()
    assert "verdict=" in body and "exit-code=" in body


def test_cli_writes_the_job_summary(tmp_path):
    gh = tmp_path / "summary.md"
    gh.write_text("")
    env = dict(os.environ, GITHUB_STEP_SUMMARY=str(gh))
    _cli("run", "--path", ".", "--summary", "true", env=env)
    assert "weakest leg" in gh.read_text()


def test_the_action_yml_matches_the_cli():
    """An action.yml that passes a flag the CLI does not accept is broken for every user and
    green in every test that never runs it."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    body = open(os.path.join(here, "action.yml"), encoding="utf-8").read()
    for flag in ("--path", "--fail-on", "--sarif", "--summary"):
        assert flag in body, f"action.yml never passes {flag}"
    from proof_carrying_ci.cli import build_parser
    run = build_parser()._subparsers._group_actions[0].choices["run"]
    known = {o for a in run._actions for o in a.option_strings}
    for flag in ("--path", "--fail-on", "--sarif", "--summary"):
        assert flag in known, f"the CLI does not accept {flag} but action.yml passes it"
    for out in ("verdict", "weakest", "exit-code"):
        assert f"{out}:" in body
