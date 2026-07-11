"""Unit tests for homeops_router — entity parsing, scoring, lane routing.

Offline: no network, no Home Assistant. Run with:
    python3 -m pytest tests/test_homeops_router.py -q
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "homeops_router", ROOT / "homeops_ai" / "homeops_router.py"
)
assert spec is not None and spec.loader is not None
router = importlib.util.module_from_spec(spec)
sys.modules["homeops_router"] = router
spec.loader.exec_module(router)


SAMPLE_PROMPT = """You are a voice assistant for Home Assistant.
Answer questions about the world truthfully.

An overview of the areas and the devices in this smart home:
```csv
entity_id,name,state,aliases
light.kitchen_main,Kitchen Light,off,
light.hall_lamp,Hall Lamp,on,hallway light
climate.living_room,Living Room Thermostat,heat,
cover.garage_door,Garage Door,closed,
media_player.kitchen_speaker,Kitchen Speaker,idle,
sensor.outside_temperature,Outside Temperature,12.4,
switch.pond_pump,Pond Pump,on,
lock.front_door,Front Door,locked,
```

Do not restate or appreciate what the user says."""


def test_parse_entity_block_extracts_rows():
    entities, spans = router.parse_entity_block(SAMPLE_PROMPT)
    ids = {e["entity_id"] for e in entities}
    assert "light.kitchen_main" in ids
    assert "lock.front_door" in ids
    assert len(entities) == 8
    assert spans, "expected at least one excisable span"


def test_parse_entity_block_ignores_prose():
    entities, spans = router.parse_entity_block(
        "You are helpful.\nAnswer briefly.\nNo devices here."
    )
    assert entities == []
    assert spans == []


def test_scoring_prefers_named_entity():
    entities, _ = router.parse_entity_block(SAMPLE_PROMPT)
    scored = router.score_entities(entities, "turn on the kitchen light")
    assert scored, "expected matches"
    assert scored[0][1]["entity_id"] == "light.kitchen_main"


def test_scoring_domain_keywords():
    entities, _ = router.parse_entity_block(SAMPLE_PROMPT)
    scored = router.score_entities(entities, "make it warmer in here")
    ids = [e["entity_id"] for _s, e in scored]
    assert "climate.living_room" in ids


def test_classify_fast_for_device_commands():
    assert router.classify("turn on the kitchen light", True) == "fast"
    assert router.classify("is the garage door closed", True) == "fast"


def test_classify_escalates_complex():
    assert router.classify("why did my automation fail last night", True) == "escalate"
    assert router.classify("create a script that dims the lights at sunset", True) == "escalate"
    assert router.classify("", True) == "escalate"
    long = "word " * 100
    assert router.classify(long, True) == "escalate"


def test_slim_prompt_caps_entities(monkeypatch):
    monkeypatch.setattr(router, "MAX_FAST_ENTITIES", 3)
    entities, spans = router.parse_entity_block(SAMPLE_PROMPT)
    slim, sent = router.build_slim_prompt(
        SAMPLE_PROMPT, entities, spans, "turn on the kitchen light"
    )
    assert sent <= 3
    assert "light.kitchen_main" in slim
    # the excised full table must be gone
    assert "sensor.outside_temperature" not in slim
    # original non-table instructions survive
    assert "Do not restate" in slim


def test_slim_prompt_no_match_falls_back_to_actionable():
    entities, spans = router.parse_entity_block(SAMPLE_PROMPT)
    slim, sent = router.build_slim_prompt(SAMPLE_PROMPT, entities, spans, "zzz qqq")
    assert sent > 0
    assert "search_entities" in slim or "Likely target devices" in slim


def test_tool_search_entities_uses_table():
    entities, _ = router.parse_entity_block(SAMPLE_PROMPT)
    out = router.tool_search_entities({"query": "pond", "limit": 5}, entities)
    assert out["count"] == 1
    assert out["results"][0]["entity_id"] == "switch.pond_pump"


def test_tool_search_entities_domain_filter():
    entities, _ = router.parse_entity_block(SAMPLE_PROMPT)
    out = router.tool_search_entities(
        {"query": "kitchen", "domain": "media_player"}, entities
    )
    ids = [r["entity_id"] for r in out["results"]]
    assert ids == ["media_player.kitchen_speaker"]


def test_call_service_blocked_when_disabled(monkeypatch):
    monkeypatch.setattr(router, "SERVICE_CALLS_ENABLED", False)
    out = router.tool_call_service(
        {"domain": "light", "service": "turn_on", "entity_id": "light.x"}
    )
    assert "error" in out


def test_call_service_validates_input(monkeypatch):
    monkeypatch.setattr(router, "SERVICE_CALLS_ENABLED", True)
    bad = router.tool_call_service(
        {"domain": "light; rm -rf /", "service": "turn_on"}
    )
    assert "error" in bad
    bad2 = router.tool_call_service(
        {"domain": "light", "service": "turn_on", "entity_id": "not-an-entity"}
    )
    assert "error" in bad2


def test_get_state_validates_entity_id():
    out = router.tool_get_state({"entity_id": "DROP TABLE"})
    assert "error" in out


def test_fixture_word_beats_room_group():
    """'the lamps in the family room' must target the Lamps circuit, not the
    room group entity that merely matches the room name (live bug: Hue group
    'Family Room' swallowed the request while the Lutron 'Lamps' was off)."""
    entities = [
        {"entity_id": "light.family_room", "name": "Family Room", "state": "on", "aliases": ""},
        {"entity_id": "light.lamps_2", "name": "Lamps", "state": "off", "aliases": ""},
        {"entity_id": "light.downlights_28", "name": "Downlights", "state": "off", "aliases": ""},
    ]
    scored = router.score_entities(entities, "turn on the lamps in the family room")
    assert scored[0][1]["entity_id"] == "light.lamps_2"


def test_fixture_word_downlights():
    entities = [
        {"entity_id": "light.family_room", "name": "Family Room", "state": "on", "aliases": ""},
        {"entity_id": "light.downlights_28", "name": "Downlights", "state": "off", "aliases": ""},
    ]
    scored = router.score_entities(entities, "family room downlights on please")
    assert scored[0][1]["entity_id"] == "light.downlights_28"


def test_preamble_covers_unavailable_and_fixtures():
    p = router.FAST_SYSTEM_PREAMBLE
    assert "unavailable" in p
    assert "unreachable" in p.lower()
    assert "lamps" in p.lower()
    assert "changed=[]" in p


def test_get_state_group_member_warning(monkeypatch):
    """Group entity whose members are all unavailable must carry a warning."""
    calls = {}

    def fake_ha_request(path, method="GET", body=None, timeout=10.0):
        calls[path] = True
        if path == "/states/light.family_room":
            return {
                "entity_id": "light.family_room",
                "state": "on",
                "last_changed": "2026-07-11T19:47:28+00:00",
                "attributes": {
                    "friendly_name": "Family Room",
                    "entity_id": ["light.hue_iris_1", "light.table_lamp"],
                },
            }
        return {"entity_id": path.split("/")[-1], "state": "unavailable", "attributes": {}}

    monkeypatch.setattr(router, "ha_request", fake_ha_request)
    out = router.tool_get_state({"entity_id": "light.family_room"})
    assert out["state"] == "on"
    assert "warning" in out
    assert "stale" in out["warning"]
    assert len(out["group_members"]) == 2


def test_get_state_group_partial_warning(monkeypatch):
    def fake_ha_request(path, method="GET", body=None, timeout=10.0):
        if path == "/states/light.family_room":
            return {
                "entity_id": "light.family_room",
                "state": "on",
                "last_changed": "x",
                "attributes": {
                    "friendly_name": "Family Room",
                    "entity_id": ["light.a", "light.b"],
                },
            }
        state = "on" if path.endswith("light.a") else "unavailable"
        return {"entity_id": path.split("/")[-1], "state": state, "attributes": {}}

    monkeypatch.setattr(router, "ha_request", fake_ha_request)
    out = router.tool_get_state({"entity_id": "light.family_room"})
    assert "1 of 2" in out.get("warning", "")


def test_get_state_non_group_no_warning(monkeypatch):
    def fake_ha_request(path, method="GET", body=None, timeout=10.0):
        return {"entity_id": "light.solo", "state": "off", "last_changed": "x",
                "attributes": {"friendly_name": "Solo"}}

    monkeypatch.setattr(router, "ha_request", fake_ha_request)
    out = router.tool_get_state({"entity_id": "light.solo"})
    assert "warning" not in out
    assert "group_members" not in out


def test_unavailable_duplicate_loses_to_live_entity():
    """Dead duplicates (old integrations) must rank below live same-name entities."""
    entities = [
        {"entity_id": "light.lamps", "name": "Lamps", "state": "unavailable", "aliases": ""},
        {"entity_id": "light.lamps_2", "name": "Lamps", "state": "off", "aliases": ""},
    ]
    scored = router.score_entities(entities, "turn on the lamps")
    assert scored[0][1]["entity_id"] == "light.lamps_2"


def test_search_entities_area_enrichment(monkeypatch):
    def fake_ha_request(path, method="GET", body=None, timeout=10.0):
        if path == "/template":
            return '["Family Room", "Kitchen"]'
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(router, "ha_request", fake_ha_request)
    table = [
        {"entity_id": "light.lamps_2", "name": "Lamps", "state": "off", "aliases": ""},
        {"entity_id": "light.lamps_3", "name": "Lamps", "state": "off", "aliases": ""},
    ]
    out = router.tool_search_entities({"query": "lamps"}, table)
    assert out["count"] == 2
    assert out["results"][0].get("area") in ("Family Room", "Kitchen")


def test_search_entities_area_enrichment_failure_is_soft(monkeypatch):
    def fake_ha_request(path, method="GET", body=None, timeout=10.0):
        raise RuntimeError("template api down")

    monkeypatch.setattr(router, "ha_request", fake_ha_request)
    table = [{"entity_id": "light.lamps_2", "name": "Lamps", "state": "off", "aliases": ""}]
    out = router.tool_search_entities({"query": "lamps"}, table)
    assert out["count"] == 1
    assert "area" not in out["results"][0]
