#!/usr/bin/env python3
from __future__ import annotations
import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PAT = re.compile(r"OpenClaw|openclaw|OPENCLAW|clawd|ClawHub|oc-")
ALLOW = [
    re.compile(r"^docs/legacy/"),
    re.compile(r"^PORTING\.md$"),
    re.compile(r"^homeops_ai/CHANGELOG\.md$"),
    re.compile(r"^scripts/validate_no_openclaw_user_surface\.py$"),
    re.compile(r"^scripts/validate_local\.sh$"),
]
SKIP_DIRS = {'.git','__pycache__','.pytest_cache','.mypy_cache','node_modules'}
SUFFIXES = {'.sh','.py','.yaml','.yml','.json','.md','.tpl','.html','.svg'}
errors=[]
for path in ROOT.rglob('*'):
    rel = path.relative_to(ROOT).as_posix()
    if any(part in SKIP_DIRS for part in path.parts):
        continue
    if not path.is_file() or path.suffix not in SUFFIXES:
        continue
    if any(rx.search(rel) for rx in ALLOW):
        continue
    try:
        text=path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        continue
    for i,line in enumerate(text.splitlines(),1):
        if PAT.search(line):
            errors.append(f"{rel}:{i}:{line.strip()}")
if errors:
    print('ERROR: legacy OpenClaw terminology found outside approved migration-history files:', file=sys.stderr)
    for e in errors[:100]: print(e, file=sys.stderr)
    raise SystemExit(1)
print('OK: no OpenClaw terminology on current user-facing/runtime surfaces')
