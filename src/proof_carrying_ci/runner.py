"""runner.py — the four jobs, one command, and an exit code you can argue with.

WHAT THIS IS FOR. Every verification tool in this portfolio answers one question and prints one
verdict. In a pipeline you want them all, once, with a single answer and an artefact a reviewer
can open. This is that.

THE ONE DESIGN DECISION THAT MATTERS: `fail-on` DEFAULTS TO `failure`, NOT `unverified`.

A CI check that goes red because a tool could not run is a check that people disable. The default
therefore fails the job only on a check that RAN AND FAILED -- a real, actionable defect -- while
an `UNVERIFIED` aggregate is reported loudly in the summary, in SARIF, and in the outputs, and does
not by itself break the build. Teams that want the stricter posture opt into `fail-on: unverified`
deliberately.

This is a genuine tension and it is worth being explicit about which way it is resolved and why.
Failing open on "could not check" is exactly the defect this portfolio measures elsewhere. The
difference is that here nothing is being *reported as verified*: the verdict is UNVERIFIED
everywhere it appears, in every output format, and the only question is whether that turns the
tick red. Making unverified indistinguishable from failed in the UI is how both get ignored.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

__all__ = ["Report", "Leg", "run_audit", "to_sarif", "to_markdown", "RunnerError"]

PASSED, FAILED, UNVERIFIED = "PASSED", "FAILED", "UNVERIFIED"
# Weakest first. `min` over this ordering IS the aggregation rule.
ORDER = [FAILED, UNVERIFIED, PASSED]


class RunnerError(RuntimeError):
    """Something the runner itself could not do. Distinct from a check that failed."""


@dataclass
class Leg:
    name: str
    verdict: str
    detail: str = ""
    applicable: bool = True
    available: bool = True

    @property
    def votes(self) -> bool:
        """Only a leg that ran and had something to check moves the aggregate."""
        return self.applicable and self.available


@dataclass
class Report:
    verdict: str
    legs: List[Leg] = field(default_factory=list)
    weakest: Optional[str] = None
    path: str = "."
    notes: List[str] = field(default_factory=list)

    @property
    def voting(self) -> List[Leg]:
        return [l for l in self.legs if l.votes]

    @property
    def exit_code(self) -> int:
        return {PASSED: 0, FAILED: 1, UNVERIFIED: 2}[self.verdict]

    def should_fail(self, fail_on: str) -> bool:
        if fail_on == "never":
            return False
        if fail_on == "unverified":
            return self.verdict in (FAILED, UNVERIFIED)
        return self.verdict == FAILED

    def to_dict(self) -> Dict[str, Any]:
        return {"schema": "proof-carrying-ci/v1", "verdict": self.verdict,
                "weakest": self.weakest, "path": self.path,
                "legs": [{"name": l.name, "verdict": l.verdict, "detail": l.detail,
                          "applicable": l.applicable, "available": l.available}
                         for l in self.legs],
                "rule": "the aggregate is the weakest leg, never the mean",
                "notes": self.notes}


def _aggregate(legs: List[Leg], path: str) -> Report:
    voting = [l for l in legs if l.votes]
    if not voting:
        # `all([])` is True and this is where that bug would land. An audit that checked nothing
        # is UNVERIFIED, not PASSED, however many tools were installed.
        return Report(UNVERIFIED, legs, None, path,
                      ["no constituent had anything to check here, so nothing was verified. "
                       "This is not a pass."])
    worst = min(voting, key=lambda l: ORDER.index(l.verdict))
    return Report(worst.verdict, legs, worst.name, path,
                  [f"{len(voting)} constituent(s) voted; the aggregate is the weakest of them"])


def run_audit(path: str = ".") -> Report:
    """Run every applicable constituent over `path`.

    Delegates to `evidence` when it is installed, because that is where the constituent registry
    lives and duplicating it here would let the two drift. When it is not installed the result is
    UNVERIFIED with the remedy -- never an empty pass.
    """
    if not os.path.isdir(path):
        raise RunnerError(f"{path!r} is not a directory")
    try:
        from evidence import audit as _audit
    except ImportError:
        return Report(UNVERIFIED, [], None, path,
                      ["`evidence` is not installed, so no constituent could be run. "
                       "Install with `pip install \"proof-carrying-ci[all]\"`. "
                       "NOTHING WAS CHECKED — this is not a pass."])
    agg = _audit(path)
    legs: List[Leg] = []
    for l in getattr(agg, "legs", []):
        # Read `evidence`'s REAL field names. An earlier version used
        # `getattr(l, "name", "?")` as a defensive fallback; the field is `tool`, so every leg
        # came out named "?" -- in the summary table, in every SARIF ruleId, and in `weakest`.
        # The output was garbage and nothing failed. A defensive default that cannot be right is
        # worse than an exception, because the exception would have been fixed in a minute.
        missing = [f for f in ("tool", "verdict") if not hasattr(l, f)]
        if missing:
            raise RunnerError(
                f"`evidence` returned a leg without {missing}. This package reads that API "
                f"directly; if it has changed, proof-carrying-ci needs updating rather than "
                f"guessing. Refusing to emit a report built from fields that may not mean what "
                f"they are being read as.")
        v = str(l.verdict).upper()
        # `aggregating` is evidence's own answer to 'does this leg vote'. Recomputing it here
        # would let the two definitions drift, and the drift would be invisible.
        votes = bool(getattr(l, "aggregating", v in (PASSED, FAILED, UNVERIFIED)))
        legs.append(Leg(
            name=str(l.tool),
            verdict=v if v in (PASSED, FAILED, UNVERIFIED) else UNVERIFIED,
            detail=str(getattr(l, "detail", ""))[:300],
            applicable=votes and v != "NOT_APPLICABLE",
            available=v != "UNAVAILABLE",
        ))
    return _aggregate(legs, path)


# --------------------------------------------------------------------------- output formats

_SARIF_LEVEL = {FAILED: "error", UNVERIFIED: "warning", PASSED: "note"}


def to_sarif(report: Report) -> str:
    """SARIF for GitHub code scanning.

    A PASSING leg is emitted at `note` level rather than omitted. A SARIF file with no results is
    indistinguishable from a run that checked nothing, and those two must never look the same.
    An UNVERIFIED leg is a `warning`, never absent.
    """
    results = []
    for l in report.legs:
        if not l.available:
            level, text = "warning", f"{l.name} is not installed, so it checked nothing. {l.detail}"
        elif not l.applicable:
            level, text = "note", f"{l.name} found nothing here to check. {l.detail}"
        else:
            level = _SARIF_LEVEL.get(l.verdict, "warning")
            text = f"{l.name}: {l.verdict}. {l.detail}"
        results.append({
            "ruleId": f"proof-carrying-ci/{l.name}",
            "level": level,
            "message": {"text": text.strip()},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": report.path.lstrip("./") or "."}}}],
        })
    results.append({
        "ruleId": "proof-carrying-ci/aggregate",
        "level": _SARIF_LEVEL.get(report.verdict, "warning"),
        "message": {"text": f"AGGREGATE: {report.verdict}"
                            + (f" — weakest leg: {report.weakest}" if report.weakest else "")
                            + ". The aggregate is the weakest leg, never the mean."},
        "locations": [{"physicalLocation": {
            "artifactLocation": {"uri": report.path.lstrip("./") or "."}}}],
    })
    return json.dumps({
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "proof-carrying-ci",
                                "informationUri": "https://github.com/nickharris808/proof-carrying-ci",
                                "rules": []}},
            "results": results,
        }],
    }, indent=2)


_EMOJI = {PASSED: "✅", FAILED: "❌", UNVERIFIED: "⚠️"}


def to_markdown(report: Report) -> str:
    """The job summary. Written so a reader who knows none of these tools can act on it."""
    lines = [f"## {_EMOJI.get(report.verdict, '')} `{report.verdict}`", ""]
    if report.verdict == UNVERIFIED:
        lines.append("**Nothing here is claimed to be verified.** At least one applicable check "
                     "could not be completed. This is not the same as a failure, and it is not a "
                     "pass either.")
    elif report.verdict == FAILED and report.weakest:
        lines.append(f"**`{report.weakest}` found a real defect.** The aggregate is the weakest "
                     f"leg, so no number of passing checks lifts it.")
    else:
        lines.append("Every constituent that had something to check, checked it and the property "
                     "held.")
    lines += ["", "| check | verdict | detail |", "|---|---|---|"]
    for l in report.legs:
        if not l.available:
            v = "not installed"
        elif not l.applicable:
            v = "n/a"
        else:
            v = f"{_EMOJI.get(l.verdict, '')} {l.verdict}"
        # A pipe in a detail string would break the markdown table. Escaped outside the
        # f-string: a backslash inside an f-string expression is a syntax error before 3.12,
        # and this package supports 3.9.
        detail = l.detail[:110].replace("|", "\\|")
        lines.append(f"| `{l.name}` | {v} | {detail} |")
    lines += ["", "> The aggregate is the **weakest leg**, never the mean. `n/a` and "
                  "`not installed` do not vote — but an audit over **zero** checks is "
                  "`UNVERIFIED`, because `all([])` is `True`."]
    for n in report.notes:
        lines.append(f">")
        lines.append(f"> {n}")
    return "\n".join(lines)
