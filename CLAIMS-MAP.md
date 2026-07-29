# CLAIMS-MAP — `proof-carrying-ci`

**Tag: CLEAN.** This package does not practise any claim in the associated patent family.

## The boundary, and why this one needs care

This is the artifact in the portfolio that sits closest to the line, because a CI check *looks*
like a gate. The distinction that keeps it clean:

> The claims recite **refusing an operation in reliance on an evidence set**. This package
> **computes a verdict and returns an exit code**. Whether anything is refused is decided entirely
> by the surrounding pipeline, which this package does not ship, configure, or require.

| it does | it does not |
|---|---|
| run constituents and aggregate their verdicts | admit, refuse, provision or actuate anything |
| write SARIF, a job summary, and step outputs | block a merge, a deploy, or a release |
| return 0/1/2 | require anyone to honour that code |
| default to `fail-on: failure` | enforce any policy; every posture is the user's choice |

`fail-on` is a **reporting** control, not an enforcement one. Setting `fail-on: unverified` makes
the *step* exit non-zero; turning that into a blocked merge requires branch-protection rules that
live in the user's repository settings and are not shipped, generated or documented here.

## The step deliberately not taken

The family includes claims of the shape *assemble an evidence set, evaluate it against a policy,
and **withhold the operation** when the policy is not met.* This package performs the first two
and stops. It has no interface to a deployment system, no credential handling, and no mechanism by
which its result could withhold anything.

Adding a blocking mode that binds the refusal into a release record would cross the line. That is
the licensed side, and it stays there.

## Provenance

Written for this release. Constituent detection is delegated to `evidence` rather than
reimplemented, so no registry is duplicated here. No internal corpus is read and no file is
extracted from a licensed implementation.
