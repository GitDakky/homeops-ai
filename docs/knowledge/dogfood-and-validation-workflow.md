---
type: Runbook
title: Dogfood and Validation Workflow
description: The test gauntlet every HomeOps AI change passes before push, and how to probe a live install read-only.
resource: https://github.com/GitDakky/homeops-ai/blob/main/scripts/dogfood_router.py
tags: [testing, dogfood, ci, runbook]
timestamp: 2026-07-05
aokf:
  provenance:
    method: agent-authored
    source: repo:scripts/dogfood_router.py
  verification: agent-checked
  confidence: high
  aliases: [testing workflow, validate_local, router e2e]
  relations:
    relates_to: [fast-lane-voice-router, release-and-versioning-rules]
---

Run from the repo root before every push (also enforced in CI):

```sh
bash scripts/validate_local.sh
```

That single gate runs: release metadata check, option/schema/translation
coupling check, legacy-terminology guard, bash syntax, Python compile,
legacy unittest suites, router pytest suite, the offline router dogfood,
and SVG parsing.

The dogfood harness (`scripts/dogfood_router.py`) is the end-to-end proof:
it boots the REAL [router](/fast-lane-voice-router.md) against fake
LLM/gateway/HA upstreams (stdlib HTTP servers, no network) and asserts 18
checks across four scenarios — fast-lane context dieting, tool round-trips
for out-of-context devices, escalation fidelity (original prompt reaches
the gateway verbatim), and stats hygiene (no secrets).

Against a running add-on, dogfood read-only:

```sh
python3 scripts/dogfood_router.py --live http://<ha-host>:8643
```

Live mode probes `/router/health`, `/router/stats`, and one harmless state
query; it never calls services. The same stats surface in the add-on UI's
Voice tab. This gauntlet is a hard prerequisite of the
[release and versioning rules](/release-and-versioning-rules.md).
