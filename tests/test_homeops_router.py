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
