"""proof-carrying-ci — the verification portfolio as one CI check.

    from proof_carrying_ci import run_audit, to_sarif, to_markdown

    report = run_audit(".")
    report.verdict          # PASSED | FAILED | UNVERIFIED
    report.weakest          # the constituent that determined it
    report.exit_code        # 0 | 1 | 2
"""
from .runner import (FAILED, PASSED, UNVERIFIED, Leg, Report, RunnerError, run_audit, to_markdown,
                     to_sarif)

__version__ = "0.1.0"
__all__ = ["run_audit", "to_sarif", "to_markdown", "Report", "Leg", "RunnerError",
           "PASSED", "FAILED", "UNVERIFIED", "__version__"]
