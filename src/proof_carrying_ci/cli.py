"""cli.py — proof-carrying-ci run | explain | selftest."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from .runner import (FAILED, PASSED, UNVERIFIED, Leg, Report, RunnerError, run_audit, to_markdown,
                     to_sarif)

FAIL_ON = ("failure", "unverified", "never")


def _gh_output(name: str, value: str) -> None:
    """Write a GitHub Actions output, if we are in one."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{name}={value}\n")


def _gh_summary(md: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(md + "\n")


def cmd_run(a: argparse.Namespace) -> int:
    if a.fail_on not in FAIL_ON:
        print(f"--fail-on must be one of {', '.join(FAIL_ON)}; got {a.fail_on!r}", file=sys.stderr)
        return 2
    try:
        report = run_audit(a.path)
    except RunnerError as e:
        print(str(e), file=sys.stderr)
        return 2

    md = to_markdown(report)
    if a.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(md)

    if a.sarif:
        with open(a.sarif, "w", encoding="utf-8") as fh:
            fh.write(to_sarif(report) + "\n")
        print(f"\nSARIF written to {a.sarif}", file=sys.stderr)
    if str(a.summary).lower() in ("1", "true", "yes"):
        _gh_summary(md)

    _gh_output("verdict", report.verdict)
    _gh_output("weakest", report.weakest or "")
    _gh_output("exit-code", str(report.exit_code))

    if report.should_fail(a.fail_on):
        return report.exit_code
    if report.verdict != PASSED:
        print(f"\nnot failing the job: --fail-on={a.fail_on} and the verdict is "
              f"{report.verdict}. The verdict is unchanged and appears in every output.",
              file=sys.stderr)
    return 0


def cmd_explain(a: argparse.Namespace) -> int:
    print(__doc__ or "")
    from .runner import __doc__ as rdoc
    print(rdoc)
    return 0


def cmd_selftest(a: argparse.Namespace) -> int:
    checks = []
    r = Report(UNVERIFIED, [], None, ".")
    checks.append((r.exit_code == 2, "UNVERIFIED exits 2, not 0"))

    empty = Report(PASSED, [Leg("x", PASSED, applicable=False)], None, ".")
    from .runner import _aggregate
    agg = _aggregate([Leg("x", PASSED, applicable=False), Leg("y", PASSED, available=False)], ".")
    checks.append((agg.verdict == UNVERIFIED,
                   "an audit where NOTHING voted is UNVERIFIED, not PASSED — `all([])` is True"))

    agg2 = _aggregate([Leg("a", PASSED), Leg("b", PASSED), Leg("c", UNVERIFIED)], ".")
    checks.append((agg2.verdict == UNVERIFIED and agg2.weakest == "c",
                   "two passes do not lift one unverified — the weakest leg wins"))

    agg3 = _aggregate([Leg("a", PASSED), Leg("b", FAILED), Leg("c", UNVERIFIED)], ".")
    checks.append((agg3.verdict == FAILED, "FAILED is weaker than UNVERIFIED"))

    checks.append((not agg2.should_fail("failure") and agg2.should_fail("unverified"),
                   "the default fail-on=failure does NOT redden on UNVERIFIED; "
                   "fail-on=unverified does"))
    checks.append((not agg3.should_fail("never"), "fail-on=never never reddens"))

    s = json.loads(to_sarif(agg2))
    ids = [x["ruleId"] for x in s["runs"][0]["results"]]
    checks.append((len(s["runs"][0]["results"]) == 4,
                   "SARIF emits EVERY leg including passes — an empty SARIF is "
                   "indistinguishable from a run that checked nothing"))
    lv = {x["ruleId"]: x["level"] for x in s["runs"][0]["results"]}
    checks.append((lv["proof-carrying-ci/c"] == "warning",
                   "an UNVERIFIED leg is a SARIF `warning`, never absent"))

    md = to_markdown(agg2)
    checks.append(("weakest leg" in md and "UNVERIFIED" in md,
                   "the summary states the rule and the verdict"))

    for ok, label in checks:
        print(f"  [{'ok  ' if ok else 'FAIL'}] {label}")
    bad = sum(1 for ok, _ in checks if not ok)
    print(f"\nRESULT: {'the aggregation rule holds' if not bad else f'{bad} FAILED'}")
    return 1 if bad else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="proof-carrying-ci",
        description="Run the verification portfolio over your repo. The aggregate is the weakest "
                    "leg, never the mean.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="audit a directory")
    r.add_argument("--path", default=".")
    r.add_argument("--fail-on", default="failure", choices=list(FAIL_ON))
    r.add_argument("--sarif", default="", help="write SARIF here")
    r.add_argument("--summary", default="false")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_run)

    e = sub.add_parser("explain", help="why fail-on defaults the way it does")
    e.set_defaults(func=cmd_explain)

    t = sub.add_parser("selftest", help="the aggregation rule, checked")
    t.set_defaults(func=cmd_selftest)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
