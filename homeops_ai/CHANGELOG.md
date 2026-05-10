# Changelog

## [0.1.9]

### Added
- Starts the Hermes Agent dashboard UI alongside the gateway and proxies it inside Home Assistant Ingress at `/dashboard/`.
- Adds Home Assistant UI buttons for Hermes Workspace, Hermes Dashboard, Hermes API UI, and terminal access.

## [0.1.8]

### Added
- Adds product-level model routing settings for fast, complex, deep, and local/ultra-fast lanes so users can choose models from the Home Assistant settings UI.
- Documents the routed-agent architecture and guidance for large Home Assistant installations where full entity context makes agents slow.

## [0.1.7]

### Changed
- Removes inherited legacy-agent wording from current architecture assets and keeps old source-fork history in `docs/legacy/OPENCLAW_CHANGELOG.md`.
- Adds a validation guard so legacy OpenClaw terminology cannot reappear in current user-facing or runtime files outside approved migration-history docs.

## [0.1.6]

### Fixed
- Forces Hermes API Server adapter configuration to follow the HomeOps gateway port option, including migrated installs that still carry the old 18790 setting in persistent Hermes config.
- Prevents the Hermes gateway from restarting endlessly when an old OpenClaw add-on or stale config is still bound to 18790.

## [0.1.5]

### Fixed
- Fixes Home Assistant restart loops caused by stale in-container listeners holding the ingress, terminal, dashboard, Workspace, or Hermes gateway ports after watchdog restarts.
- Restores Hermes-native default gateway port handling to 8642 in the runtime script.
- Adds no-op compatibility wrappers for the removed OpenClaw gateway relay lifecycle so Hermes restarts do not fail on missing functions.

## [0.1.4]

### Fixed
- Fixed Dockerfile Workspace build shell precedence so `pnpm install` and `pnpm build` run inside `/opt/hermes-workspace` instead of falling back to the add-on build context.
- Pinned a compatible global pnpm for the bundled Hermes Workspace build.

## [0.1.3]

### Changed
- Reworked HomeOps AI settings, dashboard language, and docs to be Hermes Agent-first.
- Added heavier references to official Hermes Agent documentation.
- Replaced remaining user-facing OpenClaw terminology in the add-on interface with Hermes Workspace, Hermes gateway/API, and Hermes config concepts.
- Updated dashboard API defaults to prefer Hermes environment names while retaining fallback compatibility during the port.

## [0.1.2]

### Added
- Package Hermes Agent from the latest stable upstream release `v2026.5.7` instead of tracking `main`.
- Ship the official `hermes-paperclip-adapter` package in the add-on image.
- Bundle Hermes Workspace from `https://hermes-workspace.com/` / `outsourc-e/hermes-workspace` and add a managed Workspace launcher.
- Add Home Assistant options for enabling Workspace and selecting the Workspace port.

### Changed
- Keep HomeOps AI focused on Hermes-native runtime packaging rather than inherited OpenClaw runtime assumptions.

## [0.1.1]

### Added
- Added Home Assistant add-on options for Hermes LLM provider, model, and OpenRouter API key.
- Added `homeops-hermes` / `h` terminal launcher workflow for Hermes inside the add-on.

### Changed
- Reworked the managed runtime path to start `hermes gateway run` instead of the inherited OpenClaw gateway.
- Mapped add-on model/provider options into Hermes config at startup.
- Updated the GitHub Docker smoke test to verify `hermes` and `homeops-hermes`.

## [0.1.0]

### Changed
- Seeded HomeOps AI as a Hermes-first Home Assistant add-on scaffold.
- Switched add-on metadata and Dockerfile direction toward Hermes Agent.
