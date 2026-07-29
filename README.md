# proof-carrying-ci

**The verification portfolio as one CI check. The aggregate is the weakest leg, never the mean.**

[![tests](https://github.com/nickharris808/proof-carrying-ci/actions/workflows/tests.yml/badge.svg)](https://github.com/nickharris808/proof-carrying-ci/actions/workflows/tests.yml)
[![licence](https://img.shields.io/badge/licence-Apache--2.0-blue.svg)](LICENSE)

A GitHub Action and a CLI that run every applicable verifier over your repository, combine them
under one rule, and write SARIF, a job summary and step outputs.

## Use it

```yaml
- uses: nickharris808/proof-carrying-ci@main
  id: audit

- uses: github/codeql-action/upload-sarif@v3
  if: always()
  with: { sarif_file: proof-carrying-ci.sarif }

- run: echo "verdict was ${{ steps.audit.outputs.verdict }}"
```

Or locally:

```bash
pip install "proof-carrying-ci[all]"
proof-carrying-ci run --path .
proof-carrying-ci selftest
```

## Worked example — a real lock-order inversion

Two locks taken in opposite orders in two functions:

```python
# src/pool.py
import threading
conn_lock, stats_lock = threading.Lock(), threading.Lock()

def checkout():
    with conn_lock:
        with stats_lock:
            pass

def report():
    with stats_lock:
        with conn_lock:
            pass
```

```console
$ proof-carrying-ci run --path .
## ❌ `FAILED`

**`gridlock` found a real defect.** The aggregate is the weakest leg, so no number of passing
checks lifts it.

| check | verdict | detail |
|---|---|---|
| `signoff-cert` | n/a | no signoff-cert/v1 certificates found |
| `honestbench` | n/a | no evidence manifest found |
| `sf-verify` | n/a | no hash-chained decision log (.jsonl with a `prev` field) found |
| `gridlock` | ❌ FAILED | WEDGES: conn_lock -> stats_lock -> conn_lock |
| `proof-drift` | n/a | no Lean sources, so there is no proof to drift from |

> The aggregate is the **weakest leg**, never the mean.
$ echo $?
1
```

## The one design decision worth arguing about

**`fail-on` defaults to `failure`, not `unverified`.**

By default the job goes red only for a check that **ran and failed** — a real, actionable defect.
An `UNVERIFIED` aggregate is reported loudly in the summary, in SARIF, and in the step outputs, and
does not by itself break the build.

This is in tension with the rest of this portfolio, which exists to stop "could not check" being
read as "fine", so it is worth being explicit about why it resolves this way. **Nothing is ever
reported as verified when it is not.** The verdict is `UNVERIFIED` in every output format; the only
question is whether that turns the tick red. A CI check that reddens because an optional tool was
missing is a check that gets deleted in a fortnight — and then nothing is reported at all.

Choose your posture:

| `fail-on` | job fails when |
|---|---|
| `failure` *(default)* | a check ran and **failed** |
| `unverified` | that, **or** a check could not be completed |
| `never` | never — the verdict lives in the summary and the SARIF only |

There is a test pinning all nine cells of that matrix.

## The verdict algebra

Weakest to strongest, and `min` over this ordering *is* the aggregation rule:

| verdict | means | exit |
|---|---|---:|
| `FAILED` | a check ran and the property does not hold | 1 |
| `UNVERIFIED` | a check could not be completed; nothing is known | 2 |
| `PASSED` | a check ran and the property holds | 0 |

`n/a` (nothing here to check) and `not installed` **do not vote** — folding them in would make
every repository permanently `UNVERIFIED`, and a warning nobody can ever clear is a warning
everybody learns to ignore.

**But an audit over zero voting legs is `UNVERIFIED`, always.** `all([])` is `True`, and a runner
that reports success because nothing objected is precisely the bug this portfolio exists to
prevent, reappearing one level up. There is a test for it.

## SARIF

Every leg is emitted, including the passes, at `note` level. **An empty SARIF file is
indistinguishable from a run that checked nothing**, and those two must never look the same. An
`UNVERIFIED` leg is a `warning`; a missing tool is a `warning` that says so.

## Inputs and outputs

| input | default | |
|---|---|---|
| `path` | `.` | directory to audit |
| `fail-on` | `failure` | `failure` · `unverified` · `never` |
| `sarif` | `proof-carrying-ci.sarif` | empty to skip |
| `summary` | `true` | write the job summary |
| `extras` | `all` | `all` · `core` · a pip spec |

| output | |
|---|---|
| `verdict` | `PASSED` · `FAILED` · `UNVERIFIED` |
| `weakest` | the constituent that determined the aggregate |
| `exit-code` | 0 · 1 · 2 |

## Library use

```python
from proof_carrying_ci import run_audit, to_sarif, to_markdown

report = run_audit(".")
report.verdict, report.weakest, report.exit_code
report.should_fail("unverified")
open("out.sarif", "w").write(to_sarif(report))
```

## Honest scope

A `PASSED` says *every constituent that had something to check, checked it and the property held.*
It does **not** say the constituents cover everything worth checking — an audit is exactly as broad
as the tools that ran, which is why coverage is printed next to the verdict. It inherits every
limit of every leg it summarises and adds no confidence of its own.

Constituent detection is delegated to [`evidence`](https://github.com/nickharris808/evidence)
rather than duplicated, so the two cannot drift. If `evidence` is not installed the result is
`UNVERIFIED` naming the remedy — never an empty pass.

## What this does not do

`proof-carrying-ci` **measures and reports**. Its exit code is advisory; nothing in the package
enforces it, and the decision to block a merge on it is yours. See [CLAIMS-MAP.md](CLAIMS-MAP.md).

## Development

```bash
pip install -e ".[dev]"
python -m pytest -q          # 32 tests
proof-carrying-ci selftest
```

One test asserts `action.yml` only passes flags the CLI actually accepts — an Action that passes an
unknown flag is broken for every user and green in every test that never runs it.

## License

Apache-2.0. See [LICENSE](LICENSE) and [CONTRIBUTING.md](CONTRIBUTING.md).

**Citing this?** Metadata is in [CITATION.cff](CITATION.cff) — GitHub's "Cite this repository" button reads it directly.

<!-- PORTFOLIO -->
---

## The rest of the portfolio

25 artifacts, one idea: **a measurement you cannot check is a press release.** Every tool
here reports; none of them gates.

**Tools**

| | |
|---|---|
| [`abstain-bench`](https://github.com/nickharris808/abstain-bench) | how often does a verifier pass input it could not check? |
| [`evidence`](https://github.com/nickharris808/evidence) | run the whole portfolio over your repo — the weakest leg, never the mean |
| [`floorgen`](https://github.com/nickharris808/floorgen) | what must your system remember? an exact lower bound |
| [`formal-proof-mcp`](https://github.com/nickharris808/formal-proof-mcp) | a proof kernel for your coding agent |
| [`gatecount`](https://github.com/nickharris808/gatecount) | exactly how many states does removing this check admit? |
| [`gridlock`](https://github.com/nickharris808/gridlock) | certify a wait-for relation cannot wedge |
| [`honestbench`](https://github.com/nickharris808/honestbench) | measure your CI's escape rate |
| [`kvleak`](https://github.com/nickharris808/kvleak) | cross-tenant leak scanner |
| [`kvprobe`](https://github.com/nickharris808/kvprobe) | model-substitution detector with a measured FPR |
| [`preregister`](https://github.com/nickharris808/preregister) | refuses to seal a plan whose conclusion is already fixed |
| [`proof-carrying-ci`](https://github.com/nickharris808/proof-carrying-ci) | the whole portfolio as one CI check, with SARIF ← you are here |
| [`proof-to-code-drift`](https://github.com/nickharris808/proof-to-code-drift) | fail the build when the proof stops matching |
| [`sf-verify`](https://github.com/nickharris808/sf-verify) | re-derive admission decisions offline |
| [`signoff-cert`](https://github.com/nickharris808/signoff-cert) | certificates that carry their own false-pass bound |
| [`tokencount`](https://github.com/nickharris808/tokencount) | a token count both parties can recompute |

**Benchmarks** — each recomputes one of our own published numbers from its certificate

| | |
|---|---|
| [`illusion-bench`](https://github.com/nickharris808/illusion-bench) | how many broken kernels does your oracle admit? |
| [`kv-reuse-econ-bench`](https://github.com/nickharris808/kv-reuse-econ-bench) | recompute our economics headline |
| [`llm-tenant-isolation-bench`](https://github.com/nickharris808/llm-tenant-isolation-bench) | recompute our isolation figures |

**Datasets**

| | |
|---|---|
| [`abstain-corpus`](https://huggingface.co/datasets/nickh007/abstain-corpus) | 32 inputs a verifier must NOT pass |
| [`kv-reuse-econ-traces`](https://huggingface.co/datasets/nickh007/kv-reuse-econ-traces) | per-workload reuse accounting + the closed form |
| [`kv-tenant-isolation-bench`](https://huggingface.co/datasets/nickh007/kv-tenant-isolation-bench) | isolation observations, uninterpretable rows included |
| [`llm-precision-fingerprints`](https://huggingface.co/datasets/nickh007/llm-precision-fingerprints) | precision-labelled logprobs with a negative control |

**Try it in a browser** — no install, no GPU

| | |
|---|---|
| [`negative-results-atlas`](https://huggingface.co/spaces/nickh007/negative-results-atlas) | ten claims we took back |
| [`tenant-leak-demo`](https://huggingface.co/spaces/nickh007/tenant-leak-demo) | the residency calculator |
| [`wait-for-visualiser`](https://huggingface.co/spaces/nickh007/wait-for-visualiser) | paste a wait-for graph, see the cycle |

### Documentation

Everything above, explained in one place: **<https://nickharris808.github.io/evidence-docs/>** —
the [tutorial](https://nickharris808.github.io/evidence-docs/start/tutorial/),
[what this proves and what it does not](https://nickharris808.github.io/evidence-docs/concepts/what-this-proves/),
and a [CLI reference](https://nickharris808.github.io/evidence-docs/reference/cli/) generated by
running `--help` on every published command.

### The commercial edition

Everything above is **measure-only** and Apache-2.0: it tells you what is true and never acts on
it. The **enforcement** side — binding a partition key at the admission decision, the compiled gate
corpus, and the certificate-*issuing* faucet — is covered by filed patents and licensed separately.

**Reading is free. Enforcing is licensed.**
<!-- /PORTFOLIO -->
