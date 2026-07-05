---
type: Policy
title: Release and Versioning Rules
description: Every Home-Assistant-visible change must bump the add-on version and changelog together, then be verified on GHCR before announcing.
resource: https://github.com/GitDakky/homeops-ai/blob/main/homeops_ai/config.yaml
tags: [release, versioning, policy]
timestamp: 2026-07-05
aokf:
  provenance:
    method: agent-authored
    source: repo:homeops_ai/CHANGELOG.md
  verification: agent-checked
  confidence: high
  aliases: [version bump, changelog rule, release checklist]
  relations:
    relates_to: [dogfood-and-validation-workflow, addon-runtime-lifecycle]
---

Home Assistant only offers an add-on update when `homeops_ai/config.yaml`
carries a higher plain SemVer version than the installed one. Therefore
every change users must see follows one atomic recipe:

1. Bump `version:` in `homeops_ai/config.yaml`.
2. Add a matching top entry in `homeops_ai/CHANGELOG.md` (user-facing,
   action-oriented wording).
3. Commit both together with the functional change; push to `main` so
   GitHub Actions builds and publishes the multi-arch image to GHCR.
4. Verify before announcing: raw `config.yaml` on GitHub shows the new
   version, the build workflow succeeded, and the GHCR manifest exists.
5. The user then refreshes the add-on repository in Home Assistant and
   updates. If HA does not show the version, run `ha store reload` on the
   HAOS host.

Companion rules: the repo is public, so no secrets/tokens/IPs/household
data in any commit; option changes must update schema + all six
translations + DOCS.md in the same change; and the
[validation gauntlet](/dogfood-and-validation-workflow.md) must pass
before every push. Version bumps matter because the
[add-on runtime lifecycle](/addon-runtime-lifecycle.md) only changes when
Home Assistant pulls a new image. The Home Assistant builder workflow is
the authoritative image build path — do not add duplicate hand-written
Docker smoke builds.
