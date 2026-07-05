#!/usr/bin/env python3
"""HomeOps router dogfood harness.

Spins up the REAL router process with FAKE upstreams (fake fast-LLM, fake
Hermes gateway, fake Home Assistant REST API), then drives realistic voice
requests through it and asserts on lane choice, context diet, tool use, and
latency headers.

Two modes:
  offline (default) : everything faked, runs anywhere in ~2s. CI-safe.
  --live            : points at a real router (ROUTER_URL) and only runs
                      read-only probes (/router/health, /router/stats and a
                      harmless "what is the state of..." query). For
                      dogfooding against the live add-on.

Usage:
  python3 scripts/dogfood_router.py            # offline e2e
  python3 scripts/dogfood_router.py --live http://192.0.2.1:8643
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "homeops_ai" / "homeops_router.py"

FAKE_LLM_PORT = 48611
FAKE_GW_PORT = 48612
FAKE_HA_PORT = 48613
ROUTER_PORT = 48614

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


class FakeUpstream(BaseHTTPRequestHandler):
    """One handler class, three personalities, chosen by server.role."""

    def log_message(self, format, *args):  # noqa: A002  silence
        pass

    def _json(self, code: int, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        role = getattr(self.server, "role", "")
        if role == "ha" and self.path.startswith("/states/"):
            entity_id = self.path.rsplit("/", 1)[-1]
            self._json(200, {
                "entity_id": entity_id, "state": "on",
                "attributes": {"friendly_name": "Fake Device",
                               "brightness": 200},
                "last_changed": "2026-07-05T12:00:00+00:00",
            })
            return
        if role == "ha" and self.path == "/states":
            self._json(200, [
                {"entity_id": "light.attic_light",
                 "state": "off",
                 "attributes": {"friendly_name": "Attic Light"}},
            ])
            return
        self._json(404, {"error": "nope"})

    def do_POST(self):
        role = getattr(self.server, "role", "")
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        self.server.captured.append((self.path, body))  # type: ignore[attr-defined]

        if role == "llm":
            # First call: if tools offered and utterance mentions attic,
            # exercise the tool loop once. Otherwise reply directly.
            msgs = body.get("messages") or []
            user = ""
            for m in reversed(msgs):
                if m.get("role") == "user":
                    user = str(m.get("content") or "")
                    break
            has_tool_result = any(m.get("role") == "tool" for m in msgs)
            if "attic" in user.lower() and not has_tool_result:
                self._json(200, {"choices": [{"index": 0, "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{"id": "t1", "type": "function",
                                    "function": {"name": "search_entities",
                                                 "arguments": json.dumps({"query": "attic light"})}}],
                }, "finish_reason": "tool_calls"}]})
                return
            self._json(200, {"choices": [{"index": 0, "message": {
                "role": "assistant", "content": "Done, the light is on."},
                "finish_reason": "stop"}]})
            return

        if role == "gw":
            self._json(200, {"choices": [{"index": 0, "message": {
                "role": "assistant",
                "content": "Full agent handled this complex request."},
                "finish_reason": "stop"}]})
            return

        if role == "ha" and self.path.startswith("/services/"):
            self._json(200, [{"entity_id": "light.kitchen_main"}])
            return
        self._json(404, {"error": "nope"})


def start_fake(port: int, role: str):
    srv = ThreadingHTTPServer(("127.0.0.1", port), FakeUpstream)
    srv.role = role  # type: ignore[attr-defined]
    srv.captured = []  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def post(url: str, payload: dict) -> tuple[int, dict, dict]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, dict(resp.headers), json.loads(resp.read())


def get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.status, json.loads(resp.read())


SYSTEM_PROMPT = """You are a voice assistant.
An overview of the areas and the devices in this smart home:
```csv
entity_id,name,state,aliases
light.kitchen_main,Kitchen Light,off,
light.hall_lamp,Hall Lamp,on,
climate.living_room,Living Room Thermostat,heat,
cover.garage_door,Garage Door,closed,
media_player.kitchen_speaker,Kitchen Speaker,idle,
sensor.outside_temperature,Outside Temperature,12.4,
switch.pond_pump,Pond Pump,on,
lock.front_door,Front Door,locked,
```
"""


def chat_body(utterance: str) -> dict:
    return {"model": "homeops", "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": utterance}]}


def run_offline() -> int:
    print("== offline dogfood: starting fake upstreams ==")
    llm = start_fake(FAKE_LLM_PORT, "llm")
    gw = start_fake(FAKE_GW_PORT, "gw")
    ha = start_fake(FAKE_HA_PORT, "ha")

    env = dict(os.environ)
    env.update({
        "ROUTER_PORT": str(ROUTER_PORT),
        "GATEWAY_URL": f"http://127.0.0.1:{FAKE_GW_PORT}",
        "FAST_LLM_BASE_URL": f"http://127.0.0.1:{FAKE_LLM_PORT}",
        "FAST_LLM_MODEL": "fake/fast-model",
        "FAST_LLM_API_KEY": "dogfood-not-a-secret",
        "HA_REST_BASE_URL": f"http://127.0.0.1:{FAKE_HA_PORT}",
        "HA_TOKEN": "dogfood-not-a-secret",
        "MAX_FAST_ENTITIES": "3",
        "ENABLE_HA_SERVICE_CALLS": "true",
    })
    proc = subprocess.Popen([sys.executable, str(ROUTER)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{ROUTER_PORT}"
    try:
        for _ in range(40):
            try:
                get(f"{base}/router/health")
                break
            except Exception:
                time.sleep(0.25)
        else:
            print("router never came up; output:")
            print(proc.stdout.read().decode() if proc.stdout else "")
            return 1

        print("== scenario 1: simple device command -> fast lane, dieted context ==")
        status, headers, body = post(f"{base}/v1/chat/completions",
                                     chat_body("turn on the kitchen light"))
        check("http 200", status == 200)
        check("fast lane", headers.get("X-HomeOps-Lane") == "fast",
              str(headers.get("X-HomeOps-Lane")))
        sent = llm.captured[-1][1]  # type: ignore[attr-defined]
        sys_msg = next(m["content"] for m in sent["messages"]
                       if m["role"] == "system")
        check("context dieted (<=3 rows + header)",
              sys_msg.count("\n") < 40 and "pond_pump" not in sys_msg,
              f"len={len(sys_msg)}")
        check("kitchen light survived diet", "light.kitchen_main" in sys_msg)
        check("tools offered", bool(sent.get("tools")))
        check("spoken reply", "Done" in json.dumps(body))

        print("== scenario 2: unknown device -> tool loop via fake HA ==")
        status, headers, body = post(f"{base}/v1/chat/completions",
                                     chat_body("turn on the attic light"))
        check("http 200", status == 200)
        check("fast lane", headers.get("X-HomeOps-Lane") == "fast")
        paths = [p for p, _ in llm.captured]  # type: ignore[attr-defined]
        check("llm called twice (tool round-trip)", len(paths) >= 3)

        print("== scenario 3: complex request -> escalated to gateway ==")
        status, headers, body = post(
            f"{base}/v1/chat/completions",
            chat_body("why did my heating automation fail last night?"))
        check("http 200", status == 200)
        check("escalate lane", headers.get("X-HomeOps-Lane") == "escalate",
              str(headers.get("X-HomeOps-Lane")))
        check("gateway answered",
              "Full agent" in json.dumps(body))
        check("gateway got ORIGINAL fat prompt",
              "pond_pump" in json.dumps(gw.captured[-1][1]))  # type: ignore[attr-defined]

        print("== scenario 4: stats endpoint ==")
        status, stats = get(f"{base}/router/stats")
        check("stats http 200", status == 200)
        check("stats counted requests", stats.get("requests", 0) >= 3, str(stats))
        check("stats has lanes", stats.get("fast_lane", 0) >= 2
              and stats.get("escalated", 0) >= 1)
        check("entity diet visible",
              stats.get("entities_seen_last", 0) > stats.get("entities_sent_last", 0))
        check("no secrets in stats",
              "dogfood-not-a-secret" not in json.dumps(stats))
    finally:
        proc.terminate()
        for srv in (llm, gw, ha):
            srv.shutdown()

    print(f"\n== dogfood result: {PASS} passed, {FAIL} failed ==")
    return 1 if FAIL else 0


def run_live(base: str) -> int:
    print(f"== live dogfood against {base} (read-only) ==")
    status, health = get(f"{base}/router/health")
    check("health 200", status == 200 and health.get("ok") is True)
    status, stats = get(f"{base}/router/stats")
    check("stats 200", status == 200)
    print(json.dumps(stats, indent=2))
    status, headers, body = post(f"{base}/v1/chat/completions", {
        "model": "homeops",
        "messages": [{"role": "user",
                      "content": "what is the outside temperature?"}]})
    check("query 200", status == 200)
    print("lane:", headers.get("X-HomeOps-Lane"),
          "latency:", headers.get("X-HomeOps-Latency-Ms"), "ms")
    print(f"\n== dogfood result: {PASS} passed, {FAIL} failed ==")
    return 1 if FAIL else 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--live":
        sys.exit(run_live(sys.argv[2].rstrip("/")))
    sys.exit(run_offline())
