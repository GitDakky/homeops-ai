# AGENTS.md — docs

Documentation tree: knowledge bundle, assets, and migration history.

## Ownership

- `assets/` — README SVGs (banner, architecture, router-flow). SMIL
  animation only (GitHub strips scripts/foreignObject); relative paths in
  README; validate XML before commit.
- `knowledge/` — Agentic-OKF knowledge bundle for HomeOps AI (concepts +
  index). Authored via `aokf`; markdown is source of truth. Keep
  `aokf lint --profile okf --strict` clean. No secrets, IPs, or real
  household entity data in concepts.
- `legacy/OPENCLAW_CHANGELOG.md` — frozen history from the upstream fork.
  Never edit; the legacy-terminology guard allowlists this path only.

## Local Contracts

- Root `README.md` (owned by the root rail, rendered on GitHub) embeds
  `docs/assets/*.svg` — keep names stable or update README in the same
  change.
- User-facing configuration/troubleshooting lives in `../DOCS.md`
  (rendered inside HA); architecture/deep-dive material lives here.

## Verification

```sh
python3 - <<'PY'
from pathlib import Path
import xml.etree.ElementTree as ET
for p in Path('docs/assets').glob('*.svg'):
    ET.parse(p); print('ok', p)
PY
```
