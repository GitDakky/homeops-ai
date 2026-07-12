#!/usr/bin/env python3
"""HomeOps AI conversation router — the fast lane.

An OpenAI-compatible /v1/chat/completions proxy that sits between Home
Assistant's conversation integration (extended_openai_conversation or any
OpenAI-shaped caller) and the model backends.

Why it exists
=============
Home Assistant serialises EVERY exposed entity into the system prompt on
every utterance.  On large installs (thousands of entities) that means tens
of thousands of tokens per turn, multi-second latency, and a big bill —
mostly describing devices irrelevant to the request.

The router fixes this with a *context diet + lazy loading* strategy:

1.  Parse the incoming request and locate the entity table HA injected.
2.  Score every entity against the user's utterance (name / id / alias /
    area / domain token overlap).
3.  Rebuild a slim system prompt containing only the top-K candidates
    (``MAX_FAST_ENTITIES``, default 20).
4.  Hand the fast model function tools — ``search_entities``,
    ``get_state``, ``call_service`` — so anything outside the candidate
    set is still reachable *on demand* against the full entity graph via
    the Home Assistant REST API.
5.  Requests that look complex (diagnostics, automations, multi-step
    reasoning) are escalated verbatim to the full Hermes Agent gateway.

The result: small context (fast + cheap) with full-house control.

Design constraints
==================
- stdlib only (mirrors dashboard_api.py) — no new Docker dependencies.
- never logs secrets or tokens.
- fail-open: any router-side error escalates to the full agent rather
  than dropping the request.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import unicodedata
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ------------------------------------------------------------------------
# Configuration (environment-driven; run.sh wires these from add-on options)
# ------------------------------------------------------------------------

ROUTER_PORT = int(os.environ.get("ROUTER_PORT", "8643"))
ROUTER_HOST = os.environ.get("ROUTER_HOST", "127.0.0.1")

# Full Hermes Agent gateway (the escalation target / complex lane).
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8642").rstrip("/")

# Fast lane model backend (OpenAI-compatible chat completions).
FAST_BASE_URL = os.environ.get(
    "FAST_LLM_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/")
FAST_MODEL = os.environ.get("FAST_LLM_MODEL", "google/gemini-3.1-flash-lite")
FAST_API_KEY = os.environ.get("FAST_LLM_API_KEY", "") or os.environ.get(
    "OPENROUTER_API_KEY", ""
)

# Home Assistant REST API (for on-demand tools).
HA_REST_BASE = os.environ.get("HA_REST_BASE_URL", "http://supervisor/core/api").rstrip("/")
HA_TOKEN_ENV_NAMES = ("SUPERVISOR_TOKEN", "HASS_TOKEN", "HA_TOKEN")

MAX_FAST_ENTITIES = max(1, min(100, int(os.environ.get("MAX_FAST_ENTITIES", "20"))))
SERVICE_CALLS_ENABLED = re.match(
    r"^(1|true|yes|on)$", os.environ.get("ENABLE_HA_SERVICE_CALLS", "false"), re.I
) is not None

TOOL_LOOP_LIMIT = int(os.environ.get("ROUTER_TOOL_LOOP_LIMIT", "5"))
FAST_TIMEOUT = float(os.environ.get("ROUTER_FAST_TIMEOUT", "30"))
ESCALATE_TIMEOUT = float(os.environ.get("ROUTER_ESCALATE_TIMEOUT", "120"))

ROUTER_VERSION = "0.2.0"

# ------------------------------------------------------------------------
# Stats (dogfooding surface — /router/stats)
# ------------------------------------------------------------------------

_stats_lock = threading.Lock()
STATS: dict[str, Any] = {
    "started_at": time.time(),
    "requests": 0,
    "fast_lane": 0,
    "escalated": 0,
    "errors": 0,
    "tool_calls": 0,
    "entities_seen_last": 0,
    "entities_sent_last": 0,
    "last_latency_ms": None,
    "latencies_ms": [],  # rolling window
}


def _record(key: str, value: Any = 1) -> None:
    with _stats_lock:
        if key == "latency":
            STATS["last_latency_ms"] = value
            STATS["latencies_ms"].append(value)
            if len(STATS["latencies_ms"]) > 200:
                STATS["latencies_ms"] = STATS["latencies_ms"][-200:]
        elif isinstance(STATS.get(key), (int, float)) and isinstance(value, (int, float)):
            STATS[key] += value
        else:
            STATS[key] = value


def _ha_token() -> str:
    for name in HA_TOKEN_ENV_NAMES:
        value = os.environ.get(name, "")
        if value:
            return value
    return ""


# ------------------------------------------------------------------------
# Entity table extraction
# ------------------------------------------------------------------------
#
# extended_openai_conversation's default prompt embeds a CSV-ish block:
#
#     An overview of the areas and the devices in this smart home:
#     ```csv
#     entity_id,name,state,aliases
#     light.kitchen,Kitchen Light,off,
#     ...
#     ```
#
# Other prompt templates embed plain lines of `domain.object_id` rows.  The
# parser is deliberately tolerant: it finds any contiguous run of lines that
# start with a valid entity_id, however the template formatted them.

ENTITY_ROW_RE = re.compile(r"^\s*([a-z_]+\.[a-z0-9_]+)\s*[,|\t: ]?\s*(.*)$")
KNOWN_DOMAINS_HINT = {
    "light", "switch", "climate", "cover", "fan", "lock", "sensor",
    "binary_sensor", "media_player", "scene", "script", "automation",
    "vacuum", "camera", "alarm_control_panel", "humidifier",
    "input_boolean", "button", "number", "select", "weather", "person",
    "device_tracker", "todo", "timer", "counter", "siren", "valve",
    "water_heater", "remote", "wake_word", "stt", "tts", "update",
}


def parse_entity_block(text: str) -> tuple[list[dict[str, str]], list[tuple[int, int]]]:
    """Extract entity rows from a system prompt.

    Returns (entities, spans) where spans are (start_line, end_line) index
    ranges of the contiguous entity blocks found, so the caller can excise
    them from the prompt.
    """
    lines = text.splitlines()
    entities: list[dict[str, str]] = []
    spans: list[tuple[int, int]] = []
    block_start: int | None = None
    block_rows = 0

    def close_block(end_idx: int) -> None:
        nonlocal block_start, block_rows
        if block_start is not None and block_rows >= 3:
            spans.append((block_start, end_idx))
        block_start = None
        block_rows = 0

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped in {"```csv", "```", "entity_id,name,state,aliases"}:
            # part of a block wrapper — attach to a block if one is open
            if block_start is None:
                block_start = idx
            continue
        match = ENTITY_ROW_RE.match(line)
        domain = match.group(1).split(".")[0] if match else ""
        if match and domain in KNOWN_DOMAINS_HINT:
            if block_start is None:
                block_start = idx
            block_rows += 1
            entity_id = match.group(1)
            rest = match.group(2).strip()
            parts = [p.strip() for p in rest.split(",")] if rest else []
            entities.append(
                {
                    "entity_id": entity_id,
                    "name": parts[0] if parts else "",
                    "state": parts[1] if len(parts) > 1 else "",
                    "aliases": ",".join(parts[2:]) if len(parts) > 2 else "",
                    "raw": line,
                }
            )
        else:
            close_block(idx - 1)
    close_block(len(lines) - 1)
    return entities, spans


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return re.sub(r"[^a-z0-9\s]", " ", text)


STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "to", "of",
    "in", "on", "at", "it", "its", "my", "me", "i", "you", "your", "please",
    "can", "could", "would", "will", "turn", "set", "make", "what", "whats",
    "how", "and", "or", "for", "with", "do", "does", "off", "on",
}

DOMAIN_KEYWORDS = {
    "light": {"light", "lights", "lamp", "lamps", "brightness", "dim"},
    "climate": {"heat", "heating", "temperature", "thermostat", "cool",
                "cooling", "hvac", "warm", "warmer", "cooler", "degrees"},
    "cover": {"blind", "blinds", "curtain", "curtains", "shutter", "shutters",
              "garage", "gate", "cover"},
    "lock": {"lock", "unlock", "locked", "door"},
    "media_player": {"music", "play", "pause", "volume", "speaker", "tv",
                     "television", "spotify", "song"},
    "switch": {"switch", "plug", "socket", "outlet"},
    "fan": {"fan", "ventilation"},
    "scene": {"scene", "mood"},
    "vacuum": {"vacuum", "hoover", "clean"},
    "camera": {"camera", "cctv"},
    "sensor": {"sensor", "humidity", "battery", "power", "energy"},
    "alarm_control_panel": {"alarm", "arm", "disarm"},
}

# Specific fixture nouns. When the user names one of these, they mean a
# particular fixture ("the lamps", "the downlights"), NOT the room's group
# entity. Entities whose *name* contains the fixture word get a strong
# boost so they outrank same-room group entities (e.g. a Hue room group
# called "Family Room" must not swallow "turn on the lamps in the family
# room"). Seen live at Longueville: the group was on, the Lamps circuit was
# off, and the assistant wrongly said "already on".
FIXTURE_WORDS = {
    "lamp", "lamps", "downlight", "downlights", "pendant", "pendants",
    "spot", "spots", "spotlight", "spotlights", "strip", "strips",
    "chandelier", "sconce", "sconces", "uplighter", "uplighters",
    "feature", "wallwash", "task", "reading",
}

# Different words people use for the same physical fixture. Folded on both
# the utterance and entity-name sides before matching, so "turn on the
# chandelier" finds an entity named "Pendant" (Longueville: the Orangery
# chandelier is the Lutron zone named "Pendant").
FIXTURE_SYNONYMS = {
    "chandelier": "pendant",
    "chandeliers": "pendant",
    "spotlight": "spot",
    "spotlights": "spot",
    "downlighter": "downlight",
    "downlighters": "downlight",
}


def score_entities(
    entities: list[dict[str, str]], utterance: str
) -> list[tuple[float, dict[str, str]]]:
    """Score entities against the utterance; higher = more relevant."""

    def _deplural(tok: str) -> str:
        # cheap singular/plural folding: lamps==lamp, downlights==downlight
        tok = FIXTURE_SYNONYMS.get(tok, tok)
        return tok[:-1] if len(tok) > 3 and tok.endswith("s") else tok

    tokens = {t for t in _normalise(utterance).split() if t and t not in STOPWORDS}
    tokens_folded = {_deplural(t) for t in tokens}
    wanted_domains: set[str] = set()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if tokens & keywords:
            wanted_domains.add(domain)

    scored: list[tuple[float, dict[str, str]]] = []
    fixture_asked = tokens & FIXTURE_WORDS
    for ent in entities:
        eid = ent["entity_id"]
        domain = eid.split(".")[0]
        hay_tokens = set(_normalise(
            " ".join((eid.replace(".", " ").replace("_", " "),
                      ent.get("name", ""), ent.get("aliases", "")))
        ).split())
        hay_folded = {_deplural(t) for t in hay_tokens}
        overlap = tokens_folded & hay_folded
        score = 3.0 * len(overlap)
        if domain in wanted_domains:
            score += 1.5
        # exact name phrase bonus
        name_norm = _normalise(ent.get("name", ""))
        if name_norm and name_norm.strip() and name_norm.strip() in _normalise(utterance):
            score += 4.0
        # Fixture-word bonus: "the lamps" must rank the Lamps circuit above
        # a room group that merely matches the room name. Weight must beat
        # the room-name exact-phrase bonus (+4) plus its token overlap —
        # live case: "Family Room" group scored 11.5 vs Lamps 10.5 with a
        # 6.0 bonus, so the group still won. 9.0 makes fixtures decisive.
        fixture_folded = {_deplural(t) for t in fixture_asked}
        if fixture_asked:
            if fixture_folded & hay_folded:
                score += 9.0
            else:
                # The user asked for a specific fixture and this entity is
                # not it — cancel the room-phrase advantage of group/room
                # entities so they cannot swallow fixture requests.
                score -= 3.0
        # Availability tiebreaker: many estates carry dead duplicates of the
        # same fixture name (old integrations, unplugged bridges). Prefer a
        # live entity over an unavailable one with the same name.
        if ent.get("state") in ("unavailable", "unknown", ""):
            score -= 1.0
        if score > 0:
            scored.append((score, ent))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


# ------------------------------------------------------------------------
# Lane classification
# ------------------------------------------------------------------------

ESCALATE_PATTERNS = re.compile(
    r"\b(automation|automations|script|scripts|scene editor|dashboard|"
    r"diagnos|debug|error|log|logs|why|investigate|analy[sz]e|history|"
    r"trend|graph|configure|configuration|install|update|upgrade|backup|"
    r"restore|integration|add-?on|yaml|template|create|build|write|"
    r"schedule|remind|every day|each day|daily|weekly|research|explain|"
    r"compare|summari[sz]e)\b",
    re.I,
)


def classify(utterance: str, has_entities: bool) -> str:
    """Return 'fast' or 'escalate'."""
    if not utterance:
        return "escalate"
    if len(utterance) > 280:
        return "escalate"
    if ESCALATE_PATTERNS.search(utterance):
        return "escalate"
    if not has_entities:
        # No entity table to diet — nothing for the fast lane to leverage;
        # but short device-ish commands can still run fast with live search.
        tokens = set(_normalise(utterance).split())
        domainish = any(tokens & kw for kw in DOMAIN_KEYWORDS.values())
        return "fast" if domainish else "escalate"
    return "fast"


# ------------------------------------------------------------------------
# Home Assistant REST helpers (lazy-loading tools)
# ------------------------------------------------------------------------


def ha_request(path: str, method: str = "GET", body: dict | None = None,
               timeout: float = 10.0) -> Any:
    token = _ha_token()
    if not token:
        raise RuntimeError("No Home Assistant API token available to the router")
    url = f"{HA_REST_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode() or "null")


def _edit_distance(a: str, b: str, cap: int = 2) -> int:
    """Levenshtein distance with early-exit cap."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = cur[0]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
            best = min(best, cur[j])
        if best > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def _fuzzy_token(query_tok: str, area_tok: str) -> bool:
    """Does a query token plausibly refer to an area-name token?

    Exact match; prefix match when the shared prefix is >=5 chars
    ("orange" -> "orangery", but "hall" (4) cannot fire on "hallway");
    or edit-distance <=2 for tokens >=6 chars ("orangary" -> "orangery").
    """
    if query_tok == area_tok:
        return True
    if len(query_tok) >= 5 and area_tok.startswith(query_tok):
        return True
    if len(area_tok) >= 5 and query_tok.startswith(area_tok):
        return True
    if len(query_tok) >= 6 and len(area_tok) >= 6:
        return _edit_distance(query_tok, area_tok) <= 2
    return False


_AREAS_CACHE: dict[str, Any] = {"at": 0.0, "areas": []}
_AREAS_TTL = 300.0


def _all_areas() -> list[dict[str, Any]]:
    """Area registry as [{id, tokens}] — name + alias token sets, cached."""
    now = time.time()
    if now - _AREAS_CACHE["at"] < _AREAS_TTL and _AREAS_CACHE["areas"]:
        return _AREAS_CACHE["areas"]
    tpl = (
        "[{% for a in areas() %}"
        "{\"id\": {{ a | to_json }}, \"name\": {{ (area_name(a) or '') | to_json }}}"
        "{{ \",\" if not loop.last }}{% endfor %}]"
    )
    rendered = ha_request("/template", "POST", {"template": tpl})
    raw = json.loads(rendered) if isinstance(rendered, str) else rendered
    areas = []
    for a in raw or []:
        tokens = [t for t in _normalise(a.get("name", "")).split()
                  if t and t not in STOPWORDS]
        areas.append({"id": a["id"], "tokens": tokens})
    _AREAS_CACHE["at"] = now
    _AREAS_CACHE["areas"] = areas
    return areas


def tool_search_entities(args: dict, table: list[dict[str, str]]) -> dict:
    query = str(args.get("query", "")).strip()
    domain = str(args.get("domain", "")).strip().lower()
    limit = max(1, min(50, int(args.get("limit", 10) or 10)))
    results: list[dict[str, str]] = []

    candidates = table
    if not candidates:
        # Live fallback: pull states from HA (full graph — not just exposed).
        try:
            states = ha_request("/states")
            candidates = [
                {
                    "entity_id": s.get("entity_id", ""),
                    "name": (s.get("attributes") or {}).get("friendly_name", ""),
                    "state": s.get("state", ""),
                    "aliases": "",
                }
                for s in states
            ]
        except Exception as exc:  # noqa: BLE001
            return {"error": f"live entity search unavailable: {exc}"}

    scored = score_entities(candidates, query) if query else [
        (0.0, c) for c in candidates
    ]
    for _score, ent in scored:
        if domain and not ent["entity_id"].startswith(domain + "."):
            continue
        results.append(
            {k: ent[k] for k in ("entity_id", "name", "state") if k in ent}
        )
        if len(results) >= limit:
            break

    # Area-first injection: fixtures are usually named for WHAT they are
    # ("Lamps", "Downlights", "Pendant"), not WHERE they are, so a room
    # query like "lights in the family room" matches nothing by name.
    # Resolve any area whose name appears in the query — with fuzzy token
    # matching, because voice STT mangles room names ("Orangery" arrives
    # as "orange room" / "orange tree" / "orangary") — and inject its
    # entities at the top. Matching is per-area-token: every token of the
    # area name must fuzzy-match a query token (exact, prefix ≥5 chars,
    # or edit-distance ≤2 for tokens ≥6 chars). "Hall" (4 chars) cannot
    # prefix-fire on "hallway"; "orange" (6) prefix-matches "orangery".
    if query:
        try:
            q_tokens = [t for t in _normalise(query).split() if t]
            matched_areas = [
                a["id"] for a in _all_areas()
                if a["tokens"] and all(
                    any(_fuzzy_token(q, at) for q in q_tokens)
                    for at in a["tokens"]
                )
            ]
            area_ents: list = []
            if matched_areas:
                tpl = (
                    "{% set ns = namespace(ids=[]) %}"
                    "{% for a in " + json.dumps(matched_areas) + " %}"
                    "{% set ns.ids = ns.ids + area_entities(a) %}"
                    "{% endfor %}"
                    "[{% for i in ns.ids %}"
                    "{\"entity_id\": {{ i | to_json }}, \"state\": {{ states(i) | to_json }},"
                    " \"name\": {{ (state_attr(i, 'friendly_name') or '') | to_json }}}"
                    "{{ \",\" if not loop.last }}{% endfor %}]"
                )
                rendered = ha_request("/template", "POST", {"template": tpl})
                area_ents = json.loads(rendered) if isinstance(rendered, str) else rendered
            if isinstance(area_ents, list) and area_ents:
                # Order injected entities by the domain the query implies
                # ("lights in the family room" → light.* first) so an
                # area's switches/selects/trackers can't crowd the
                # relevant fixtures out of the limit window.
                q_set = set(q_tokens)
                wanted = {
                    d for d, kws in DOMAIN_KEYWORDS.items() if q_set & kws
                }
                def _inj_rank(ent: dict) -> int:
                    dom = str(ent.get("entity_id", "")).split(".")[0]
                    return 0 if (not wanted or dom in wanted) else 1
                area_ents = sorted(area_ents, key=_inj_rank)
                seen = {r["entity_id"] for r in results}
                injected = []
                for ent in area_ents:
                    eid = ent.get("entity_id", "")
                    if not eid or eid in seen:
                        continue
                    if domain and not eid.startswith(domain + "."):
                        continue
                    if ent.get("state") in ("unavailable", "unknown"):
                        continue
                    injected.append(
                        {"entity_id": eid, "name": ent.get("name", ""),
                         "state": ent.get("state", "")}
                    )
                    seen.add(eid)
                if injected:
                    results = (injected + results)[:limit]
        except Exception:  # noqa: BLE001
            pass  # area injection is best-effort

    # Enrich with area names so same-named fixtures in different rooms are
    # distinguishable ("Lamps" exists in several rooms at Longueville; the
    # utterance says WHICH room, the entity name alone does not). One
    # template render resolves all results in a single HA round trip.
    if results:
        try:
            tpl = ("{% set ids = [" +
                   ",".join(f"'{r['entity_id']}'" for r in results) +
                   "] %}{{ ids | map('area_name') | list | to_json }}")
            rendered = ha_request("/template", "POST", {"template": tpl})
            areas = json.loads(rendered) if isinstance(rendered, str) else rendered
            if isinstance(areas, list) and len(areas) == len(results):
                for r, area in zip(results, areas):
                    if area:
                        r["area"] = area
                # Re-rank: results whose area matches the query outrank the
                # rest ("lamps in the family room" → Family Room's Lamps
                # first, Cinema's Lamps second). Stable sort preserves the
                # existing name-relevance order within each tier, and live
                # entities outrank unavailable ones in the same tier.
                q_tokens = set(_normalise(query).split())
                def _rank(r: dict) -> tuple[int, int]:
                    area_tokens = set(_normalise(r.get("area", "")).split())
                    area_hit = 1 if area_tokens and area_tokens <= q_tokens else 0
                    alive = 0 if r.get("state") in ("unavailable", "unknown") else 1
                    return (area_hit, alive)
                results.sort(key=_rank, reverse=True)
        except Exception:  # noqa: BLE001
            pass  # area enrichment is best-effort

    return {"results": results, "count": len(results)}


def tool_get_state(args: dict) -> dict:
    entity_id = str(args.get("entity_id", "")).strip()
    if not re.match(r"^[a-z_]+\.[a-z0-9_]+$", entity_id):
        return {"error": f"invalid entity_id: {entity_id!r}"}
    try:
        state = ha_request(f"/states/{entity_id}")
    except HTTPError as exc:
        return {"error": f"HA returned {exc.code} for {entity_id}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    attrs = state.get("attributes") or {}
    slim_attrs = {
        k: v for k, v in attrs.items()
        if k in {
            "friendly_name", "brightness", "color_temp_kelvin", "rgb_color",
            "current_temperature", "temperature", "hvac_action", "hvac_modes",
            "percentage", "current_position", "media_title", "volume_level",
            "unit_of_measurement", "device_class",
        }
    }
    out = {
        "entity_id": entity_id,
        "state": state.get("state"),
        "attributes": slim_attrs,
        "last_changed": state.get("last_changed"),
    }
    # Group entities (Hue rooms, HA light groups) report the group's
    # last-known state even when every member is unreachable. Surface the
    # members' live availability so the model can catch stale group state
    # instead of telling the user "it's already on" about dead bulbs.
    members = attrs.get("entity_id")
    if isinstance(members, list) and members:
        member_states = []
        unreachable = 0
        for mid in members[:10]:
            try:
                ms = ha_request(f"/states/{mid}")
                mstate = ms.get("state")
            except Exception:  # noqa: BLE001
                mstate = "unknown"
            if mstate in ("unavailable", "unknown"):
                unreachable += 1
            member_states.append({"entity_id": mid, "state": mstate})
        out["group_members"] = member_states
        if unreachable == len(member_states):
            out["warning"] = (
                "ALL member devices of this group are unreachable; the "
                "group state shown is stale. Tell the user the lights look "
                "powered off or offline."
            )
        elif unreachable:
            out["warning"] = (
                f"{unreachable} of {len(member_states)} member devices are "
                "unreachable; group state may be partly stale."
            )
    return out


def tool_call_service(args: dict) -> dict:
    if not SERVICE_CALLS_ENABLED:
        return {
            "error": "Service calls are disabled by the add-on configuration "
                     "(enable_ha_service_calls: false)."
        }
    domain = str(args.get("domain", "")).strip().lower()
    service = str(args.get("service", "")).strip().lower()
    entity_id = str(args.get("entity_id", "")).strip()
    data = args.get("data") or {}
    if not re.match(r"^[a-z_]+$", domain) or not re.match(r"^[a-z_]+$", service):
        return {"error": "invalid domain/service"}
    if entity_id and not re.match(r"^[a-z_]+\.[a-z0-9_]+$", entity_id):
        return {"error": f"invalid entity_id: {entity_id!r}"}
    payload = dict(data) if isinstance(data, dict) else {}
    if entity_id:
        payload["entity_id"] = entity_id
    try:
        result = ha_request(f"/services/{domain}/{service}", "POST", payload,
                            timeout=15.0)
    except HTTPError as exc:
        return {"error": f"HA returned {exc.code} for {domain}.{service}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    changed = [s.get("entity_id") for s in result] if isinstance(result, list) else []
    return {"ok": True, "changed": changed}


ROUTER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_entities",
            "description": (
                "Search the home's device/entity registry by name, area, or "
                "keyword. Use when the target device is not in your context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "search words"},
                    "domain": {
                        "type": "string",
                        "description": "optional domain filter, e.g. 'light'",
                    },
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_state",
            "description": "Get the live state and key attributes of one entity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string"},
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_service",
            "description": (
                "Perform an action on a device (turn_on, turn_off, "
                "set_temperature, etc.). Confirm the entity via search_entities "
                "or context first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "service": {"type": "string"},
                    "entity_id": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["domain", "service"],
            },
        },
    },
]


def run_tool(name: str, args: dict, table: list[dict[str, str]]) -> dict:
    _record("tool_calls")
    if name == "search_entities":
        return tool_search_entities(args, table)
    if name == "get_state":
        return tool_get_state(args)
    if name == "call_service":
        return tool_call_service(args)
    return {"error": f"unknown tool {name!r}"}


# ------------------------------------------------------------------------
# Prompt slimming
# ------------------------------------------------------------------------

FAST_SYSTEM_PREAMBLE = """\
You are a fast, precise smart-home voice assistant.
Rules:
- Answer in one or two short sentences. No preamble, no reasoning aloud.
- Never speak entity IDs, job IDs, or internal identifiers.
- The device list below contains only the LIKELY targets for this request.
  It is NOT the whole home. If the device you need is not listed, call
  search_entities before saying it does not exist.
- Use get_state for live values and call_service to act.
- A state of 'unavailable' or 'unknown' means the device is UNREACHABLE
  (powered off, offline, or its integration is down). Never treat a stale
  or unavailable state as the current truth. Say the device looks
  unreachable and suggest checking its power — do not claim it is
  already on/off.
- If the user names a specific fixture (lamps, downlights, pendant,
  spots, strip...), target the entity whose NAME matches that fixture —
  not a room group entity that merely matches the room name. The same
  fixture name can exist in several rooms: match the `area` field from
  search_entities against the room the user said. Prefer entities whose
  state is not 'unavailable' when duplicates exist.
- After call_service, if the result includes changed=[] (no entities
  changed), the action likely failed or the device was already in that
  state — verify with get_state before claiming success.
- If the request is ambiguous, pick the most likely device and say what \
you did."""


def build_slim_prompt(
    original_system: str,
    entities: list[dict[str, str]],
    spans: list[tuple[int, int]],
    utterance: str,
) -> tuple[str, int]:
    """Return (slim_system_prompt, candidates_sent)."""
    lines = original_system.splitlines()
    keep: list[str] = []
    excised = {i for start, end in spans for i in range(start, end + 1)}
    for idx, line in enumerate(lines):
        if idx not in excised:
            keep.append(line)
    trimmed_instructions = "\n".join(keep).strip()

    scored = score_entities(entities, utterance)
    top = [ent for _s, ent in scored[:MAX_FAST_ENTITIES]]
    if not top:
        # Nothing matched — send a small area-agnostic sample of actionable
        # domains so the model still has *something*, and rely on tools.
        actionable = [
            e for e in entities
            if e["entity_id"].split(".")[0] in
            {"light", "switch", "climate", "cover", "lock", "media_player",
             "scene", "fan"}
        ]
        top = actionable[:MAX_FAST_ENTITIES]

    table_lines = ["entity_id,name,state"]
    for ent in top:
        table_lines.append(
            f"{ent['entity_id']},{ent.get('name', '')},{ent.get('state', '')}"
        )

    parts = [FAST_SYSTEM_PREAMBLE]
    if trimmed_instructions:
        parts.append(trimmed_instructions)
    parts.append("Likely target devices:\n```csv\n" + "\n".join(table_lines) + "\n```")
    return "\n\n".join(parts), len(top)


# ------------------------------------------------------------------------
# Upstream chat completion helpers
# ------------------------------------------------------------------------


def openai_chat(base_url: str, api_key: str, body: dict, timeout: float) -> dict:
    req = Request(f"{base_url}/chat/completions", data=json.dumps(body).encode(),
                  method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def last_user_message(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, list):
                return " ".join(
                    p.get("text", "") for p in content if isinstance(p, dict)
                )
            return str(content or "")
    return ""


def fast_lane(body: dict, entities: list[dict[str, str]],
              spans: list[tuple[int, int]]) -> dict:
    messages = list(body.get("messages") or [])
    utterance = last_user_message(messages)

    system_text = ""
    system_idx = None
    for idx, msg in enumerate(messages):
        if msg.get("role") == "system":
            system_text = str(msg.get("content") or "")
            system_idx = idx
            break

    slim_system, sent = build_slim_prompt(system_text, entities, spans, utterance)
    _record("entities_seen_last", len(entities))
    _record("entities_sent_last", sent)

    if system_idx is not None:
        messages[system_idx] = {"role": "system", "content": slim_system}
    else:
        messages.insert(0, {"role": "system", "content": slim_system})

    request_body = {
        "model": FAST_MODEL,
        "messages": messages,
        "tools": ROUTER_TOOLS,
        "temperature": body.get("temperature", 0.2),
        "max_tokens": body.get("max_tokens", 400),
    }

    for _round in range(TOOL_LOOP_LIMIT):
        response = openai_chat(FAST_BASE_URL, FAST_API_KEY, request_body,
                               FAST_TIMEOUT)
        choice = (response.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return response
        request_body["messages"] = request_body["messages"] + [message]
        for call in tool_calls:
            fn = (call.get("function") or {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = run_tool(name, args, entities)
            request_body["messages"].append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(result),
                }
            )
    # Tool loop exhausted — return a graceful failure the TTS can speak.
    return {
        "id": "router-loop-limit",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "Sorry, I couldn't complete that quickly — "
                               "try asking the full assistant.",
                },
            }
        ],
    }


def escalate(body: dict, raw: bytes) -> tuple[int, dict[str, str], bytes]:
    """Forward the ORIGINAL request unchanged to the Hermes gateway."""
    req = Request(f"{GATEWAY_URL}/v1/chat/completions", data=raw, method="POST")
    req.add_header("Content-Type", "application/json")
    auth = os.environ.get("GATEWAY_API_KEY", "")
    if auth:
        req.add_header("Authorization", f"Bearer {auth}")
    try:
        with urlopen(req, timeout=ESCALATE_TIMEOUT) as resp:
            headers = {
                "Content-Type": resp.headers.get("Content-Type",
                                                 "application/json")
            }
            return resp.status, headers, resp.read()
    except HTTPError as exc:
        return exc.code, {"Content-Type": "application/json"}, exc.read()


# ------------------------------------------------------------------------
# HTTP server
# ------------------------------------------------------------------------


class RouterHandler(BaseHTTPRequestHandler):
    server_version = f"HomeOpsRouter/{ROUTER_VERSION}"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        print(f"[router] {self.address_string()} {format % args}")

    def _send_json(self, status: int, payload: Any,
                   extra_headers: dict[str, str] | None = None) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/router/health":
            self._send_json(200, {"ok": True, "version": ROUTER_VERSION})
            return
        if self.path == "/router/stats":
            with _stats_lock:
                snapshot = dict(STATS)
                lat = snapshot.pop("latencies_ms")
            if lat:
                ordered = sorted(lat)
                snapshot["p50_ms"] = ordered[len(ordered) // 2]
                snapshot["p95_ms"] = ordered[int(len(ordered) * 0.95) - 1]
            snapshot["max_fast_entities"] = MAX_FAST_ENTITIES
            snapshot["fast_model"] = FAST_MODEL
            snapshot["service_calls_enabled"] = SERVICE_CALLS_ENABLED
            self._send_json(200, snapshot)
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in ("/v1/chat/completions", "/chat/completions"):
            self._send_json(404, {"error": "not found"})
            return
        started = time.time()
        _record("requests")
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            _record("errors")
            self._send_json(400, {"error": "invalid JSON"})
            return

        lane = "escalate"
        try:
            messages = body.get("messages") or []
            system_text = next(
                (str(m.get("content") or "") for m in messages
                 if m.get("role") == "system"), "",
            )
            entities, spans = parse_entity_block(system_text)
            utterance = last_user_message(messages)
            lane = classify(utterance, bool(entities))
            if body.get("stream"):
                # Streaming is only supported on the escalation path today.
                lane = "escalate"

            if lane == "fast":
                _record("fast_lane")
                response = fast_lane(body, entities, spans)
                elapsed = int((time.time() - started) * 1000)
                _record("latency", elapsed)
                self._send_json(200, response, {
                    "X-HomeOps-Lane": "fast",
                    "X-HomeOps-Latency-Ms": str(elapsed),
                })
                return
        except Exception as exc:  # noqa: BLE001
            print(f"[router] fast lane error, escalating: {exc}")
            _record("errors")

        _record("escalated")
        status, headers, payload = escalate(body, raw)
        elapsed = int((time.time() - started) * 1000)
        _record("latency", elapsed)
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("X-HomeOps-Lane", "escalate")
        self.send_header("X-HomeOps-Latency-Ms", str(elapsed))
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    server = ThreadingHTTPServer((ROUTER_HOST, ROUTER_PORT), RouterHandler)
    print(
        f"[router] HomeOps router v{ROUTER_VERSION} listening on "
        f"{ROUTER_HOST}:{ROUTER_PORT} — fast model {FAST_MODEL}, "
        f"max_fast_entities={MAX_FAST_ENTITIES}, "
        f"service_calls={'on' if SERVICE_CALLS_ENABLED else 'off'}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
