"""
Household Agent — GUI Server
Run:  python server.py
Then open:  https://localhost:7437
"""

import sys
import os
import subprocess

# Auto-redirect to virtual environment if running outside it
VENV_PYTHON = os.path.normpath(r"c:\users\aztre\appdata\local\hermes\hermes-agent\venv\Scripts\python.exe")
if os.path.exists(VENV_PYTHON) and os.path.normpath(sys.executable).lower() != VENV_PYTHON.lower():
    res = subprocess.run([VENV_PYTHON] + sys.argv)
    sys.exit(res.returncode)

import json
import threading
import time
import webbrowser
import urllib.request
import urllib.parse
import argparse
import socket
import ssl
import os
import shutil
import subprocess
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
import pressure_engine as pe
import primitive_concept_engine as pc_module
import vision_sensor

# ── shared state ──────────────────────────────────────────────────────────────
_lock = threading.Lock()
_engine_lock = threading.Lock()

signals = {
    "user_stress":             0.10,
    "time_since_interaction":  0.00,
    "open_task_load":          0.40,
    "knowledge_gap":           0.30,
    "time_since_contribution": 0.00,
}

focus_subject   = "general household needs"
local_camera_allowed = True
tick_count      = 0
chat_messages   = []   # [{role, text, tick}]
edge_totals     = [0.0] * len(pe.CONFIG["edges"])


def _apply_presence_to_server_signals() -> float:
    strength = pe.visual_presence_strength(signals)
    if strength > 0.0:
        signals["time_since_interaction"] = 0.0
    return strength

STRESS_WORDS = {"stressed","overwhelmed","tired","exhausted","busy","worried","anxious",
                "behind","late","deadline","hard","struggling","too much","frustrated",
                "stuck","urgent","problem","broken","bad day","can't","cannot"}
CALM_WORDS   = {"good","great","fine","relaxed","calm","done","finished","better","thanks"}

def _infer_stress(text):
    words = set(text.lower().split())
    delta = len(words & STRESS_WORDS) * 0.12 - len(words & CALM_WORDS) * 0.10
    return round(max(0.0, min(1.0, signals["user_stress"] + delta)), 3)

def _do_tick(user_spoke=False, user_text=""):
    global tick_count, focus_subject
    direct_reply_sent = False
    with _lock:
        tick_count += 1
        current_tick = tick_count
        signals.update(vision_sensor.get_current_state())
        _apply_presence_to_server_signals()
        if user_spoke and user_text:
            signals["user_stress"] = _infer_stress(user_text)
            pe.push_chat_history("user", user_text, analyze=True, signals=dict(signals))
        signal_snapshot = dict(signals)
        focus_map = {n: focus_subject for n in pe.CONFIG["buckets"]}

    if user_spoke and user_text:
        reply = pe.handle_passive_response(signal_snapshot, user_text, focus_subject=focus_subject)
        if reply:
            with _lock:
                chat_messages.append({
                    "role": "agent",
                    "text": reply,
                    "tick": current_tick,
                    "bucket": None,
                    "action": "chat",
                })
                pe.push_chat_history("assistant", reply, signals=dict(signals))
                read_ticks = max(2, len(reply) // 250)
                pe.add_contract("user_reading", read_ticks, confidence=1.0)
                direct_reply_sent = True

    with _engine_lock:
        fired_log, eflows = pe.tick(signal_snapshot, focus_map)

    with _lock:
        for i, ef in enumerate(eflows):
            edge_totals[i] += ef
        if user_spoke:
            signals["time_since_interaction"] = 0.0
        elif pe.visual_presence_strength(signals) > 0.0:
            signals["time_since_interaction"] = 0.0
        else:
            signals["time_since_interaction"] = round(
                min(1.0, signals["time_since_interaction"] + 0.05), 3)
        visible_reply_sent = False
        for entry in fired_log:
            if not entry.get("blocked"):
                signals["time_since_contribution"] = round(
                    max(0.0, signals["time_since_contribution"] - 0.4), 3)
                payload = entry.get("payload", "")
                if payload:
                    atype = entry["action_type"]
                    # internal_thought is never shown to user — skip it
                    if atype == "internal_thought":
                        chat_messages.append({
                            "role": "thought",
                            "text": payload,
                            "tick": current_tick,
                            "bucket": entry["bucket"],
                            "action": atype,
                        })
                        visible_reply_sent = True
                        continue
                    if user_spoke:
                        continue
                    if pe.CONFIG["DRY_RUN"]:
                        if atype == "reach_out":
                            msg = f"[DRY RUN — reach_out] Would message you about: {focus_subject}"
                        else:
                            msg = f"[DRY RUN — research] Would research: {focus_subject}"
                    else:
                        if atype == "reach_out":
                            msg = payload
                        else:
                            digest = ""
                            for line in payload.splitlines():
                                if line.startswith("USER DIGEST:"):
                                    digest = line[12:].strip()
                            msg = f"[Research] {digest}" if digest else f"[Research] {payload[:300]}"
                    chat_messages.append({
                        "role": "agent",
                        "text": msg,
                        "tick": current_tick,
                        "bucket": entry["bucket"],
                        "action": atype,
                    })
                    visible_reply_sent = True
                    pe.push_chat_history("assistant", msg, signals=dict(signals))
                    read_ticks = max(2, len(msg) // 250)
                    pe.add_contract("user_reading", read_ticks, confidence=1.0)

        # Fallback for non-chat callers; normal user chat replies before pressure work.
        if user_spoke and user_text and not direct_reply_sent:
            reply = pe.handle_passive_response(dict(signals), user_text)
            if reply:
                chat_messages.append({
                    "role": "agent",
                    "text": reply,
                    "tick": current_tick,
                    "bucket": None,
                    "action": "passive",
                })
                pe.push_chat_history("assistant", reply, signals=dict(signals))

        return fired_log, eflows

def _do_charge_tick():
    """Fast UI tick: update bucket pressure/flow without firing model-backed actions."""
    global tick_count
    with _lock:
        tick_count += 1
        signals.update(vision_sensor.get_current_state())
        _apply_presence_to_server_signals()
        eflows = pe.charge_only_tick(dict(signals))
        for i, ef in enumerate(eflows):
            edge_totals[i] += ef
        if pe.visual_presence_strength(signals) > 0.0:
            signals["time_since_interaction"] = 0.0
        else:
            signals["time_since_interaction"] = round(
                min(1.0, signals["time_since_interaction"] + 0.05), 3)
        return eflows

def _do_reset():
    global tick_count, edge_totals
    with _lock:
        pe.reset()
        tick_count  = 0
        edge_totals = [0.0] * len(pe.CONFIG["edges"])
        chat_messages.clear()
        signals.update({
            "user_stress":0.10,"time_since_interaction":0.00,
            "open_task_load":0.40,"knowledge_gap":0.30,
            "time_since_contribution":0.00,
        })

def _do_clear_memory():
    global tick_count, edge_totals
    with _lock:
        pe.clear_memory()
        tick_count  = 0
        edge_totals = [0.0] * len(pe.CONFIG["edges"])
        chat_messages.clear()
        signals.update({
            "user_stress":0.10,"time_since_interaction":0.00,
            "open_task_load":0.40,"knowledge_gap":0.30,
            "time_since_contribution":0.00,
        })


def _fetch_ollama_models():
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            data = json.loads(r.read())
        return [m["name"] for m in data.get("models", [])
                if "embedding" not in m["name"].lower()]
    except Exception:
        return []

def _normalize_model_name(model, available):
    if model in available:
        return model
    latest = f"{model}:latest"
    if latest in available:
        return latest
    return model

def _configure_runtime(model=None, live=True, dry=False):
    if model:
        pe.CONFIG["OLLAMA_MODEL"] = model
    available = _fetch_ollama_models()
    pe.CONFIG["OLLAMA_MODEL"] = _normalize_model_name(pe.CONFIG["OLLAMA_MODEL"], available)
    if live:
        pe.CONFIG["DRY_RUN"] = False
    if dry:
        pe.CONFIG["DRY_RUN"] = True

def _get_lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"

# ── HTTP handler ──────────────────────────────────────────────────────────────
def _node_executable():
    bundled = os.path.join(
        os.path.expanduser("~"),
        ".cache", "codex-runtimes", "codex-primary-runtime",
        "dependencies", "node", "bin", "node.exe",
    )
    return os.environ.get("NODE_EXE") or shutil.which("node") or bundled

def _speak_edge_tts(text):
    text = (text or "").strip()
    if not text:
        raise ValueError("No text to speak")
    text = text[:5000]
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edge_tts_speak.js")
    voice = pe.CONFIG.get("TTS_VOICE", "en-IE-EmilyNeural")
    result = subprocess.run(
        [_node_executable(), script, text, voice],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        timeout=35,
        check=False,
    )
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace").strip() or "Edge TTS failed"
        raise RuntimeError(err)
    if not result.stdout:
        raise RuntimeError("Edge TTS returned no audio")
    return result.stdout

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass  # silence request logs

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, body):
        b = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(b))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _audio(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/" or path == "/index.html":
            self._html(HTML)
            return
        if path.startswith("/mobile"):
            self._html(MOBILE_HTML)
            return
        if path == "/api/state":
            with _lock:
                pressures  = pe.get_pressures()
                thresholds = {n: c["threshold"] for n, c in pe.CONFIG["buckets"].items()}
                journal    = pe.get_journal()[-20:]
                outbox     = pe.get_outbox()[-10:]
                ks         = pe.get_knowledge_store()
                cp         = pe.get_context_packet()
                ij         = pe.get_internal_journal()[-5:]
            self._json({
                "tick":       tick_count,
                "pressures":  pressures,
                "thresholds": thresholds,
                "signals":    signals,
                "vision":     vision_sensor.get_status(),
                "journal":    journal,
                "outbox":     outbox,
                "knowledge":  ks,
                "context_packet": cp,
                "internal_journal": ij,
                "primitive": {
                    **pc_module.get_state(),
                    "tentative_concepts": pe.graph.get_tentative_concepts()
                },
                "model_status": pe.get_model_status(),
                "graph_summary": pe.graph.summary_text(max_nodes=12),
                "graph_counts": {"nodes": len(pe.graph.nodes), "edges": len(pe.graph.edges)},
                "memory_field": pe.get_memory_field(),
                "messages":   chat_messages[-60:],
                "edge_totals": edge_totals,
                "edges": [[s,t,w,d,str(w/d)[:4]] for s,t,w,d in pe.CONFIG["edges"]],
                "config": {
                    "model":    pe.CONFIG["OLLAMA_MODEL"],
                    "dry_run":  pe.CONFIG["DRY_RUN"],
                    "focus":    focus_subject,
                    "release":  pe.CONFIG["RELEASE_FRACTION"],
                    "flow_rate":pe.CONFIG["FLOW_RATE"],
                    "cooldowns":pe.CONFIG["cooldowns"],
                    "budget":   pe.CONFIG["ACTION_BUDGET"],
                    "window":   pe.CONFIG["BUDGET_WINDOW"],
                    "voice":    pe.CONFIG.get("TTS_VOICE", "en-IE-EmilyNeural"),
                },
            })
            return
        if path == "/api/models":
            self._json({"models": _fetch_ollama_models()})
            return
        if path == "/api/graph":
            self._json(pe.graph.to_dict())
            return
        if path == "/api/memory_field":
            self._json(pe.get_memory_field())
            return
        if path == "/api/camera_feed":
            img_bytes = vision_sensor.get_latest_frame()
            if img_bytes:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", len(img_bytes))
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(img_bytes)
            else:
                self.send_response(404)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        global focus_subject, tick_count, local_camera_allowed
        length  = int(self.headers.get("Content-Length", 0))
        body    = json.loads(self.rfile.read(length) or b"{}")
        path    = self.path

        if path == "/api/chat":
            text = body.get("text", "").strip()
            if text:
                with _lock:
                    tick_count += 1
                    current_tick = tick_count
                    chat_messages.append({"role": "user", "text": text, "tick": current_tick})
                    signals["user_stress"] = _infer_stress(text)
                    signals["time_since_interaction"] = 0.0
                    signals.update(vision_sensor.get_current_state())
                    _apply_presence_to_server_signals()
                    pe.push_chat_history("user", text, analyze=True, signals=dict(signals))
                    reply_signals = dict(signals)
                try:
                    reply = pe.handle_passive_response(reply_signals, text, focus_subject=focus_subject)
                except Exception as exc:
                    reply = f"I'm trying to answer, but the model call failed: {type(exc).__name__}: {exc}"
                if reply:
                    with _lock:
                        chat_messages.append({
                            "role": "agent",
                            "text": reply,
                            "tick": current_tick,
                            "bucket": None,
                            "action": "chat",
                        })
                        pe.push_chat_history("assistant", reply, signals=dict(signals))
                        read_ticks = max(2, len(reply) // 250)
                        pe.add_contract("user_reading", read_ticks, confidence=1.0)
                        pe.save_state()
            self._json({"ok": True, "tick": tick_count})
            return

        if path == "/api/tick":
            _do_tick(user_spoke=False)
            self._json({"ok": True, "tick": tick_count})
            return

        if path == "/api/signals":
            with _lock:
                for k, v in body.items():
                    if k in signals:
                        signals[k] = round(float(v), 3)
            self._json({"ok": True})
            return

        if path == "/api/config":
            with _lock:
                if "model"    in body: pe.CONFIG["OLLAMA_MODEL"]    = body["model"]
                if "dry_run"  in body: pe.CONFIG["DRY_RUN"]         = bool(body["dry_run"])
                if "focus"    in body: focus_subject                 = body["focus"]
                if "release"  in body: pe.CONFIG["RELEASE_FRACTION"] = float(body["release"])
                if "flow_rate"in body: pe.CONFIG["FLOW_RATE"]        = float(body["flow_rate"])
                if "voice"    in body: pe.CONFIG["TTS_VOICE"]        = body["voice"]
            self._json({"ok": True})
            return

        if path == "/api/tts":
            try:
                self._audio(_speak_edge_tts(body.get("text", "")))
            except Exception as exc:
                self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)
            return

        if path == "/api/reset":
            _do_reset()
            self._json({"ok": True})
            return

        if path == "/api/clear_memory":
            _do_clear_memory()
            self._json({"ok": True})
            return


        if path == "/api/toggle_cam":
            if not local_camera_allowed:
                vision_sensor.set_idle("none", "")
                status = vision_sensor.get_status()
                self._json({
                    "enabled": False,
                    "status": status,
                    "message": "Server-local camera is disabled by default; use Browser Webcam from the user's device."
                })
                return
            if vision_sensor._running:
                vision_sensor.stop()
                status = vision_sensor.get_status()
            else:
                vision_sensor.start()
                time.sleep(0.25)
                status = vision_sensor.get_status()
            self._json({"enabled": bool(status.get("running")), "status": status})
            return
        if path == "/api/vision_state":
            try:
                vision_sensor.update_state(body)
                with _lock:
                    signals.update(vision_sensor.get_current_state())
                self._json({"ok": True})
            except Exception as exc:
                self._json({"error": f"{type(exc).__name__}: {exc}"}, 400)
            return

        if path == "/api/vision_frame":
            try:
                img_data = body.get("image", "")
                if "," in img_data:
                    img_data = img_data.split(",")[1]
                import base64
                import numpy as np
                import cv2
                img_bytes = base64.b64decode(img_data)
                nparr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if frame is not None:
                    new_state = vision_sensor.process_frame(frame)
                    with _lock:
                        signals.update(new_state)
                        _apply_presence_to_server_signals()
                    self._json({"ok": True, "state": new_state})
                else:
                    self._json({"error": "Failed to decode frame"}, 400)
            except Exception as exc:
                self._json({"error": f"{type(exc).__name__}: {exc}"}, 400)
            return

        self._json({"error": "not found"}, 404)


# ── HTML frontend ─────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Household Agent</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root{
    --bg:#0f0f11;--bg2:#17171a;--bg3:#1e1e23;--bg4:#26262d;
    --border:#2e2e38;--border2:#3a3a48;
    --text:#e8e8ee;--text2:#9898aa;--text3:#5a5a6e;
    --blue:#5b8af0;--blue2:#3a6ad4;--green:#4ecc8a;--amber:#e8a830;
    --purple:#9a78e8;--coral:#e87860;--red:#e85050;
    --radius:10px;--radius-sm:6px;
    --decompress:#4ecc8a;--contribute:#5b8af0;--learn:#e8a830;--connect:#9a78e8;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;height:100vh;display:flex;flex-direction:column;overflow:hidden}
  #topbar{display:flex;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid var(--border);background:var(--bg2);flex-shrink:0}
  #topbar h1{font-size:15px;font-weight:600;letter-spacing:.02em}
  .spacer{flex:1}
  .badge{font-size:11px;padding:3px 8px;border-radius:4px;font-weight:500}
  .badge-live{background:#1a3a1a;color:var(--green);border:1px solid #2a5a2a}
  .badge-dry{background:#2a2a1a;color:var(--amber);border:1px solid #4a4a2a}
  select,input[type=text],input[type=number]{background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:var(--radius-sm);padding:5px 8px;font-size:13px;outline:none}
  select:focus,input:focus{border-color:var(--blue)}
  button{background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:var(--radius-sm);padding:6px 12px;font-size:13px;cursor:pointer;transition:background .15s}
  button:hover{background:var(--bg4)}
  button.primary{background:var(--blue2);border-color:var(--blue);color:#fff}
  button.primary:hover{background:var(--blue)}
  button.danger{background:#2a1a1a;border-color:#5a2a2a;color:var(--coral)}
  #layout{display:grid;grid-template-columns:260px 1fr 280px;grid-template-rows:1fr;flex:1;overflow:hidden;gap:0}
  .panel{display:flex;flex-direction:column;overflow:hidden;border-right:1px solid var(--border)}
  .panel:last-child{border-right:none}
  .panel-head{padding:10px 14px;font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text3);border-bottom:1px solid var(--border);flex-shrink:0}
  .panel-body{flex:1;overflow-y:auto;padding:12px}
  .panel-body::-webkit-scrollbar{width:4px}
  .panel-body::-webkit-scrollbar-track{background:transparent}
  .panel-body::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}

  /* buckets */
  .bucket-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:12px;margin-bottom:10px}
  .bucket-header{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
  .bucket-name{font-weight:600;font-size:13px}
  .bucket-val{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}
  .bucket-thresh{font-size:11px;color:var(--text3)}
  .bar-track{height:6px;background:var(--bg4);border-radius:3px;margin-bottom:6px;overflow:hidden}
  .bar-fill{height:6px;border-radius:3px;transition:width .4s ease,background .4s}
  .bucket-meta{display:flex;justify-content:space-between;font-size:11px;color:var(--text3)}
  .fired-flash{animation:flash .6s ease-out}
  @keyframes flash{0%{background:#2a1e0a}100%{background:var(--bg2)}}

  /* signals */
  .signal-row{margin-bottom:10px}
  .signal-label{display:flex;justify-content:space-between;margin-bottom:4px;font-size:12px}
  .signal-label span:first-child{color:var(--text2)}
  .signal-label span:last-child{font-weight:600;font-variant-numeric:tabular-nums}
  input[type=range]{width:100%;accent-color:var(--blue);height:20px}

  /* flow graph */
  #flow-svg{width:100%;margin-bottom:12px}

  /* chat */
  #chat-panel{display:flex;flex-direction:column}
  #messages{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px}
  #messages::-webkit-scrollbar{width:4px}
  #messages::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}
  .msg{max-width:85%;padding:10px 13px;border-radius:var(--radius);font-size:13px;line-height:1.5}
  .msg-user{align-self:flex-end;background:var(--blue2);color:#fff;border-radius:var(--radius) var(--radius) 3px var(--radius)}
  .msg-agent{align-self:flex-start;background:var(--bg3);border:1px solid var(--border2)}
  .msg-thought{align-self:flex-start;background:#201d2a;border:1px dashed var(--purple);color:var(--text2);font-style:italic}
  .msg-system{align-self:center;font-size:11px;color:var(--text3);padding:4px 10px;background:transparent;border:none}
  .msg-meta{font-size:11px;margin-top:4px;opacity:.6}
  .msg-agent .msg-meta{color:var(--text3)}
  .msg-agent .msg-bucket{display:inline-block;font-size:10px;padding:1px 6px;border-radius:3px;margin-bottom:5px;font-weight:600}
  .msg-play-btn{background:transparent;border:none;color:inherit;cursor:pointer;font-size:11px;padding:2px 6px;margin-left:8px;opacity:.5;transition:opacity .2s,transform .2s;display:inline-flex;align-items:center;justify-content:center;border-radius:4px}
  .msg-play-btn:hover{opacity:1;transform:scale(1.15);background:rgba(255,255,255,0.1)}
  #input-row{display:flex;gap:8px;padding:12px;border-top:1px solid var(--border);flex-shrink:0}
  #chat-input{flex:1;background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:var(--radius-sm);padding:8px 12px;font-size:14px;outline:none;resize:none;height:40px}
  #chat-input:focus{border-color:var(--blue)}
  #tick-btn{background:var(--bg3);border:1px solid var(--border2);color:var(--text2);padding:0 12px;border-radius:var(--radius-sm);cursor:pointer;font-size:12px}
  #tick-btn:hover{background:var(--bg4)}

  /* right panel tabs */
  .tabs{display:flex;border-bottom:1px solid var(--border);flex-shrink:0}
  .tab{padding:9px 12px;font-size:12px;cursor:pointer;color:var(--text3);border-bottom:2px solid transparent;margin-bottom:-1px;white-space:nowrap}
  .tab.active{color:var(--text);border-bottom-color:var(--blue)}
  .tab-content{display:none;flex:1;overflow-y:auto;padding:12px}
  .tab-content.active{display:block}
  .tab-content::-webkit-scrollbar{width:4px}
  .tab-content::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}

  /* journal */
  .jentry{padding:8px 10px;border-radius:var(--radius-sm);background:var(--bg3);margin-bottom:6px;font-size:12px;border-left:3px solid transparent}
  .jentry.fired{border-left-color:var(--green)}
  .jentry.blocked{border-left-color:var(--border2);opacity:.7}
  .jentry-head{display:flex;gap:6px;align-items:center;margin-bottom:3px;flex-wrap:wrap}
  .pill{font-size:10px;padding:1px 6px;border-radius:3px;font-weight:600}
  .pill-research{background:#1a2a1a;color:var(--green)}
  .pill-reach{background:#1a1a2a;color:var(--blue)}
  .pill-blocked{background:#2a2a2a;color:var(--text3)}
  .jentry-signals{color:var(--text3);font-size:11px;margin-top:3px}

  /* config panel */
  .cfg-row{margin-bottom:14px}
  .cfg-label{font-size:12px;color:var(--text2);margin-bottom:5px}
  .cfg-row select,.cfg-row input{width:100%}
  .cfg-hint{font-size:11px;color:var(--text3);margin-top:3px}

  /* tick counter */
  #tick-display{font-size:12px;color:var(--text3);font-variant-numeric:tabular-nums}
  .dot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:5px;vertical-align:middle}
  .dot-green{background:var(--green)}
  .dot-amber{background:var(--amber)}

  /* knowledge store */
  .ks-entry{background:var(--bg3);border-radius:var(--radius-sm);padding:8px 10px;margin-bottom:6px;font-size:12px}
  .ks-focus{font-weight:600;margin-bottom:3px;color:var(--amber)}
  .ks-note{color:var(--text2);line-height:1.5}

  /* edge bars in graph tab */
  .edge-row{display:flex;align-items:center;gap:8px;margin-bottom:7px;font-size:12px}
  .edge-label{min-width:70px;color:var(--text2)}
  .edge-track{flex:1;height:4px;background:var(--bg4);border-radius:2px;overflow:hidden}
  .edge-bar{height:4px;background:var(--blue);border-radius:2px;transition:width .4s}
  .edge-cond{min-width:36px;color:var(--text3);text-align:right}

  /* primitive */
  .prim-card{background:var(--bg3);border-radius:var(--radius-sm);padding:8px 10px;margin-bottom:6px;font-size:12px}
  .prim-pattern{display:flex;justify-content:space-between;border-bottom:1px solid var(--border);padding-bottom:6px;margin-bottom:6px}
  .prim-stat{font-variant-numeric:tabular-nums;color:var(--amber)}
  .diff-bullet{color:var(--text2);margin-bottom:4px;line-height:1.4;display:list-item;margin-left:14px}
</style>
</head>
<body>

<div id="topbar">
  <h1>&#x2302; Household Agent</h1>
  <span id="mode-badge" class="badge badge-live">LIVE</span>
  <span id="model-status" style="font-size:11px;color:var(--text3)">model idle</span>
  <span id="tick-display">tick 0</span>
  <div class="spacer"></div>
  <select id="voice-select" style="width:140px;background:var(--bg3);color:var(--text1);border:1px solid var(--border1);border-radius:6px;padding:4px;margin-right:8px;" onchange="setVoice(this.value)">
    <option value="en-IE-EmilyNeural">Emily (Female)</option>
    <option value="en-US-AndrewNeural">Andrew (Male)</option>
    <option value="en-US-EmmaNeural">Emma (Female)</option>
    <option value="en-US-AvaNeural">Ava (Female)</option>
    <option value="en-GB-SoniaNeural">Sonia (UK Female)</option>
    <option value="en-GB-RyanNeural">Ryan (UK Male)</option>
  </select>
  <button onclick="toggleVoice()" id="voice-btn" title="Speak agent replies with Edge TTS">Voice on</button>
  <button onclick="toggleBrowserCam()" id="cam-btn" title="Use this browser device camera">Browser cam</button>
  <select id="model-select" style="width:200px" onchange="setModel(this.value)">
    <option value="">Loading models…</option>
  </select>
  <button onclick="toggleDryRun()" id="dry-btn">Enable dry run</button>
  <button class="danger" onclick="doClearMemory()" title="Clear semantic knowledge graph and episodic memory">Clear Memory</button>
  <button class="danger" onclick="doReset()">Reset</button>
</div>


<div id="layout">

  <!-- LEFT: buckets + signals -->
  <div class="panel">
    <div class="panel-head">Pressure buckets</div>
    <div class="panel-body">
      <div id="bucket-decompress" class="bucket-card">
        <div class="bucket-header">
          <span class="bucket-name" style="color:var(--decompress)">Decompress</span>
          <span class="bucket-thresh">thresh 0.60</span>
        </div>
        <div class="bucket-val" id="val-Decompress">0.000</div>
        <div class="bar-track" style="margin-top:6px"><div class="bar-fill" id="bar-Decompress" style="width:0%;background:var(--decompress)"></div></div>
        <div class="bucket-meta"><span>reach_out</span><span id="over-Decompress"></span></div>
      </div>
      <div id="bucket-contribute" class="bucket-card">
        <div class="bucket-header">
          <span class="bucket-name" style="color:var(--contribute)">Contribute</span>
          <span class="bucket-thresh">thresh 0.55</span>
        </div>
        <div class="bucket-val" id="val-Contribute">0.000</div>
        <div class="bar-track" style="margin-top:6px"><div class="bar-fill" id="bar-Contribute" style="width:0%;background:var(--contribute)"></div></div>
        <div class="bucket-meta"><span>research</span><span id="over-Contribute"></span></div>
      </div>
      <div id="bucket-learn" class="bucket-card">
        <div class="bucket-header">
          <span class="bucket-name" style="color:var(--learn)">Learn</span>
          <span class="bucket-thresh">thresh 0.60</span>
        </div>
        <div class="bucket-val" id="val-Learn">0.000</div>
        <div class="bar-track" style="margin-top:6px"><div class="bar-fill" id="bar-Learn" style="width:0%;background:var(--learn)"></div></div>
        <div class="bucket-meta"><span>research</span><span id="over-Learn"></span></div>
      </div>
      <div id="bucket-connect" class="bucket-card">
        <div class="bucket-header">
          <span class="bucket-name" style="color:var(--connect)">Connect</span>
          <span class="bucket-thresh">thresh 0.50</span>
        </div>
        <div class="bucket-val" id="val-Connect">0.000</div>
        <div class="bar-track" style="margin-top:6px"><div class="bar-fill" id="bar-Connect" style="width:0%;background:var(--connect)"></div></div>
        <div class="bucket-meta"><span>reach_out</span><span id="over-Connect"></span></div>
      </div>

      <div style="border-top:1px solid var(--border);margin:14px 0 12px"></div>
      <div style="font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text3);margin-bottom:10px">Signals</div>

      <div class="signal-row">
        <div class="signal-label"><span>user_stress</span><span id="sv-user_stress">0.10</span></div>
        <input type="range" min="0" max="1" step="0.01" value="0.10" id="sl-user_stress" oninput="setSig('user_stress',+this.value)">
      </div>
      <div class="signal-row">
        <div class="signal-label"><span>open_task_load</span><span id="sv-open_task_load">0.40</span></div>
        <input type="range" min="0" max="1" step="0.01" value="0.40" id="sl-open_task_load" oninput="setSig('open_task_load',+this.value)">
      </div>
      <div class="signal-row">
        <div class="signal-label"><span>knowledge_gap</span><span id="sv-knowledge_gap">0.30</span></div>
        <input type="range" min="0" max="1" step="0.01" value="0.30" id="sl-knowledge_gap" oninput="setSig('knowledge_gap',+this.value)">
      </div>
      <div class="signal-row">
        <div class="signal-label"><span>time_since_interaction</span><span id="sv-time_since_interaction">0.00</span></div>
        <input type="range" min="0" max="1" step="0.01" value="0.00" id="sl-time_since_interaction" oninput="setSig('time_since_interaction',+this.value)">
      </div>
      <div class="signal-row">
        <div class="signal-label"><span>time_since_contribution</span><span id="sv-time_since_contribution">0.00</span></div>
        <input type="range" min="0" max="1" step="0.01" value="0.00" id="sl-time_since_contribution" oninput="setSig('time_since_contribution',+this.value)">
      </div>

      <div style="border-top:1px solid var(--border);margin:14px 0 12px"></div>
      <div style="font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text3);margin-bottom:8px">Focus subject</div>
      <input type="text" id="focus-input" value="general household needs" style="width:100%;margin-bottom:6px" placeholder="what the agent is thinking about…">
      <button onclick="setFocus()" style="width:100%">Update focus</button>

      <div style="border-top:1px solid var(--border);margin:14px 0 12px"></div>
      <div style="font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text3);margin-bottom:8px">Browser Webcam</div>
      <div id="browser-cam-card" style="background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:10px;margin-bottom:10px">
        <div style="position:relative;width:100%;padding-top:75%;background:#000;border-radius:var(--radius-sm);overflow:hidden;margin-bottom:8px">
          <video id="browser-cam-video" autoplay playsinline muted style="position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;transform:scaleX(-1);display:none;"></video>
          <img id="browser-cam-feed" src="/api/camera_feed" style="position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;transform:scaleX(-1);display:none;">
          <div id="browser-cam-placeholder" style="position:absolute;top:0;left:0;width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--text3);font-size:12px;padding:12px;text-align:center;background:#000;">
            <span id="browser-cam-placeholder-title" style="font-weight:bold;margin-bottom:6px;">Camera Off</span>
            <span id="browser-cam-help-text" style="font-size:10px;color:var(--text2);display:none;line-height:1.3;">Webcam requires HTTPS or Localhost.<br>To test on LAN, open Chrome/Edge flags:<br><code style="color:var(--blue);word-break:break-all;font-size:9px;">chrome://flags/#unsafely-treat-insecure-origin-as-secure</code><br>add this origin, enable, and relaunch.</span>
          </div>
        </div>
        <div style="display:flex;gap:6px;margin-bottom:6px">
          <button id="browser-cam-btn" onclick="toggleBrowserCam()" style="width:100%" class="primary">Start Browser Cam</button>
        </div>
        <div style="font-size:11px;color:var(--text3);display:flex;flex-direction:column;gap:4px">
          <div style="display:flex;justify-content:space-between"><span>Status:</span><span id="browser-cam-status" style="font-weight:600">Inactive</span></div>
          <div style="display:flex;justify-content:space-between"><span>Source:</span><span id="browser-cam-source">-</span></div>
          <div style="display:flex;justify-content:space-between"><span>Light:</span><span id="browser-cam-light">-</span></div>
          <div style="display:flex;justify-content:space-between"><span>Faces:</span><span id="browser-cam-faces">-</span></div>
          <div style="display:flex;justify-content:space-between"><span>Motion:</span><span id="browser-cam-motion">-</span></div>
          <div style="display:flex;justify-content:space-between"><span>Attention:</span><span id="browser-cam-attention">-</span></div>
        </div>
      </div>
    </div>
  </div>

  <!-- CENTER: chat -->
  <div class="panel" id="chat-panel" style="border-right:1px solid var(--border)">
    <div class="panel-head" style="display:flex;justify-content:space-between;align-items:center">
      <span>Chat</span>
      <span style="font-size:11px;color:var(--text3);font-weight:400;text-transform:none;letter-spacing:0">messages appear here when a bucket fires</span>
    </div>
    <div id="messages">
      <div class="msg msg-system">Agent is running. Buckets are charging. Send a message or let it idle.</div>
    </div>
    <div id="input-row">
      <textarea id="chat-input" placeholder="Say something… (signals update from your words)" rows="1"
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendChat()}"></textarea>
      <button class="primary" onclick="sendChat()">Send</button>
      <button id="tick-btn" onclick="doTick()" title="Idle tick — let time pass without saying anything">Tick</button>
    </div>
  </div>

  <!-- RIGHT: tabs -->
  <div class="panel" style="border-right:none">
    <div class="tabs">
      <div class="tab active" onclick="switchTab('journal')">Journal</div>
      <div class="tab" onclick="switchTab('graph')">Graph</div>
      <div class="tab" onclick="switchTab('knowledge')">Knowledge</div>
      <div class="tab" onclick="switchTab('analyzer')">Analyzer</div>
      <div class="tab" onclick="switchTab('primitive')">Primitive</div>
      <div class="tab" onclick="switchTab('config')">Config</div>
    </div>

    <div id="tab-journal" class="tab-content active"></div>

    <div id="tab-graph" class="tab-content">
      <div style="font-size:12px;color:var(--text3);margin-bottom:12px">Directed edges — bar = conductance (weight/distance). Total flow this session shown right.</div>
      <div id="edge-rows"></div>
      <div style="border-top:1px solid var(--border);margin:14px 0 10px"></div>
      <div style="font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text3);margin-bottom:8px">Topology</div>
      <svg id="flow-svg" viewBox="0 0 240 200" style="max-height:200px">
        <!-- nodes -->
        <rect x="80" y="4"   width="80" height="28" rx="6" fill="#1e1e23" stroke="#4ecc8a" stroke-width="1.5"/>
        <text x="120" y="23" text-anchor="middle" fill="#4ecc8a" font-size="11" font-weight="600">Decompress</text>
        <rect x="4"   y="84"  width="80" height="28" rx="6" fill="#1e1e23" stroke="#9a78e8" stroke-width="1.5"/>
        <text x="44"  y="103" text-anchor="middle" fill="#9a78e8" font-size="11" font-weight="600">Connect</text>
        <rect x="156" y="84"  width="80" height="28" rx="6" fill="#1e1e23" stroke="#e8a830" stroke-width="1.5"/>
        <text x="196" y="103" text-anchor="middle" fill="#e8a830" font-size="11" font-weight="600">Learn</text>
        <rect x="80"  y="164" width="80" height="28" rx="6" fill="#1e1e23" stroke="#5b8af0" stroke-width="1.5"/>
        <text x="120" y="183" text-anchor="middle" fill="#5b8af0" font-size="11" font-weight="600">Contribute</text>
        <!-- edges (simplified arrows) -->
        <line x1="196" y1="84"  x2="140" y2="32"  stroke="#3a3a48" stroke-width="1.2" marker-end="url(#arr)"/>
        <line x1="84"  y1="84"  x2="108" y2="32"  stroke="#3a3a48" stroke-width="1.2" marker-end="url(#arr)"/>
        <line x1="120" y1="32"  x2="44"  y2="84"  stroke="#3a3a48" stroke-width="1.2" marker-end="url(#arr)"/>
        <line x1="120" y1="164" x2="196" y2="112" stroke="#3a3a48" stroke-width="1.2" marker-end="url(#arr)"/>
        <line x1="120" y1="164" x2="44"  y2="112" stroke="#3a3a48" stroke-width="1.2" marker-end="url(#arr)"/>
        <line x1="196" y1="112" x2="140" y2="164" stroke="#3a3a48" stroke-width="1.2" marker-end="url(#arr)"/>
        <defs><marker id="arr" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="#3a3a48"/></marker></defs>
      </svg>
    </div>

    <div id="tab-knowledge" class="tab-content">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <span style="font-size:12px;color:var(--text3)">Grows from conversation and research. No invented facts.</span>
        <span id="graph-counts" style="font-size:11px;color:var(--text3)">0 nodes · 0 edges</span>
      </div>
      <canvas id="kg-canvas" style="width:100%;height:260px;background:var(--bg2);border-radius:var(--radius);margin-bottom:10px"></canvas>
      <div id="kg-node-list" style="font-size:12px"></div>
      <div style="border-top:1px solid var(--border);margin:10px 0 8px"></div>
      <div style="font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text3);margin-bottom:6px">Research store</div>
      <div id="knowledge-list"><div style="color:var(--text3);font-size:12px">Nothing researched yet.</div></div>
    </div>

    <div id="tab-analyzer" class="tab-content">
      <div style="font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text3);margin-bottom:8px">Conversation Context Packet</div>
      <div id="analyzer-focus" style="font-size:13px;color:var(--amber);font-weight:600;margin-bottom:8px"></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
        <div>
          <div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">Active Topics</div>
          <div id="analyzer-topics" style="font-size:12px;line-height:1.7"></div>
        </div>
        <div>
          <div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">Emotional Charge</div>
          <div id="analyzer-charge" style="font-size:12px;line-height:1.7"></div>
        </div>
        <div>
          <div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">Unresolved Threads</div>
          <div id="analyzer-openings" style="font-size:12px;line-height:1.7"></div>
        </div>
        <div>
          <div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">Curiosity Targets</div>
          <div id="analyzer-curiosity" style="font-size:12px;line-height:1.7"></div>
        </div>
      </div>
      <div style="display:flex;gap:16px;margin-bottom:10px">
        <div style="flex:1">
          <div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">Depth</div>
          <div id="analyzer-depth-bar" style="height:6px;background:var(--bg3);border-radius:3px;overflow:hidden"><div id="analyzer-depth-fill" style="height:100%;background:var(--purple);width:0%;transition:width .4s"></div></div>
        </div>
        <div style="flex:1">
          <div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">Emotional Weight</div>
          <div id="analyzer-weight-bar" style="height:6px;background:var(--bg3);border-radius:3px;overflow:hidden"><div id="analyzer-weight-fill" style="height:100%;background:var(--amber);width:0%;transition:width .4s"></div></div>
        </div>
      </div>
      <div style="border-top:1px solid var(--border);margin:8px 0"></div>
      <div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Relationship State</div>
      <div id="analyzer-relstate" style="font-size:12px;line-height:1.7;margin-bottom:10px"></div>
      <div style="border-top:1px solid var(--border);margin:8px 0"></div>
      <div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Internal Thoughts</div>
      <div id="analyzer-thoughts" style="font-size:12px;line-height:1.7;color:var(--text2)"></div>
    </div>

    <div id="tab-primitive" class="tab-content">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <span style="font-size:12px;color:var(--text3)">Sub-cognitive concept formation. No LLM.</span>
      </div>

      <div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">Concept Pressure</div>
      <div style="height:6px;background:var(--bg3);border-radius:3px;margin-bottom:14px;overflow:hidden">
        <div id="prim-pressure-fill" style="height:100%;background:var(--coral);width:0%;transition:width .4s"></div>
      </div>

      <div style="font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text3);margin-bottom:6px">Tentative Concepts (<span id="prim-tentative-count">0</span>)</div>
      <div id="prim-tentatives" style="margin-bottom:14px">
        <div style="color:var(--text3);font-size:12px">None yet.</div>
      </div>

      <div style="font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text3);margin-bottom:6px">Active Patterns</div>
      <div id="prim-patterns" style="margin-bottom:14px">
        <div style="color:var(--text3);font-size:12px">None yet.</div>
      </div>

      <div style="font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text3);margin-bottom:6px">Recent Diffs</div>
      <div id="prim-diffs"></div>
    </div>

    <div id="tab-config" class="tab-content">
      <div class="cfg-row">
        <div class="cfg-label">Release fraction (discharge %)</div>
        <input type="range" min="0.1" max="0.9" step="0.05" id="cfg-release" value="0.55"
          oninput="document.getElementById('cfg-release-val').textContent=(+this.value*100).toFixed(0)+'%';postConfig({release:+this.value})">
        <div class="cfg-hint">Current: <span id="cfg-release-val">55%</span> — how much pressure drops when a bucket fires</div>
      </div>
      <div class="cfg-row">
        <div class="cfg-label">Flow rate (graph speed)</div>
        <input type="range" min="0.05" max="0.6" step="0.05" id="cfg-flow" value="0.30"
          oninput="document.getElementById('cfg-flow-val').textContent=(+this.value).toFixed(2);postConfig({flow_rate:+this.value})">
        <div class="cfg-hint">Current: <span id="cfg-flow-val">0.30</span> — how fast pressure bleeds between buckets</div>
      </div>
      <div class="cfg-row" style="border-top:1px solid var(--border);padding-top:12px;margin-top:6px">
        <div class="cfg-label">Guardrails (read-only)</div>
        <div style="font-size:12px;color:var(--text2);line-height:1.8">
          reach_out cooldown: <strong>8 ticks</strong><br>
          research cooldown: <strong>6 ticks</strong><br>
          action budget: <strong>4 per 15-tick window</strong><br>
          reach_out → in-app only, never external<br>
          research → read-only web, no forms/posts
        </div>
      </div>
      <div class="cfg-row" style="border-top:1px solid var(--border);padding-top:12px;margin-top:6px">
        <div class="cfg-label">How a tick works</div>
        <div style="font-size:12px;color:var(--text2);line-height:1.8">
          <strong style="color:var(--text)">Phase A</strong> — each bucket charges from signals, decays<br>
          <strong style="color:var(--text)">Phase B</strong> — pressure flows along graph edges<br>
          <strong style="color:var(--text)">Phase C</strong> — buckets above threshold fire actions<br><br>
          Graph inflow can push a bucket over threshold even when its own signals are quiet — that's emergent behavior.
        </div>
      </div>
    </div>
  </div>
</div>

<script>
const BUCKET_COLORS={Decompress:'var(--decompress)',Contribute:'var(--contribute)',Learn:'var(--learn)',Connect:'var(--connect)'};
const BUCKET_IDS={Decompress:'bucket-decompress',Contribute:'bucket-contribute',Learn:'bucket-learn',Connect:'bucket-connect'};
let lastTick=-1, dryRun=false, lastMsgSignature='', autoTickInFlight=false;
let voiceEnabled=true, currentAudio=null;
const spokenMessageKeys=new Set();

async function api(path,body){
  const opts=body
    ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'}
    : {cache:'no-store'};
  const r=await fetch(path,opts);
  if(!r.ok) throw new Error(`${path} returned ${r.status}`);
  return r.json();
}

function showStatus(text,isError=false){
  const el=document.getElementById('model-status');
  if(!el) return;
  el.textContent=text;
  el.style.color=isError?'var(--red)':'var(--text3)';
}

function toggleVoice(){
  voiceEnabled=!voiceEnabled;
  const btn=document.getElementById('voice-btn');
  if(btn) btn.textContent=voiceEnabled?'Voice on':'Voice off';
}

async function speakText(text, force = false){
  if((!force && !voiceEnabled) || !text) return;
  try{
    const r=await fetch('/api/tts',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text}),
      cache:'no-store'
    });
    if(!r.ok){
      let detail='speech returned '+r.status;
      try{
        const err=await r.json();
        if(err.error) detail=err.error;
      }catch(_){}
      throw new Error(detail);
    }
    const blob=await r.blob();
    const url=URL.createObjectURL(blob);
    if(currentAudio) currentAudio.pause();
    currentAudio=new Audio(url);
    currentAudio.onended=()=>URL.revokeObjectURL(url);
    await currentAudio.play();
  }catch(e){
    showStatus('speech failed: '+e.message,true);
  }
}

async function loadModels(activeModel){
  const data=await api('/api/models');
  const sel=document.getElementById('model-select');
  if(!sel) return;
  sel.innerHTML='';
  (data.models||[]).forEach(m=>{
    const o=document.createElement('option');
    o.value=m; o.textContent=m;
    if(activeModel && m===activeModel) o.selected=true;
    sel.appendChild(o);
  });
}

function setModel(v){postConfig({model:v})}
function setVoice(v){postConfig({voice:v})}

function toggleDryRun(){
  dryRun=!dryRun;
  postConfig({dry_run:dryRun});
  document.getElementById('dry-btn').textContent=dryRun?'Enable live':'Enable dry run';
  document.getElementById('mode-badge').className='badge '+(dryRun?'badge-dry':'badge-live');
  document.getElementById('mode-badge').textContent=dryRun?'DRY RUN':'LIVE';
}

async function postConfig(obj){await api('/api/config',obj)}

async function setSig(k,v){
  document.getElementById('sv-'+k).textContent=v.toFixed(2);
  await api('/api/signals',{[k]:v});
}

async function setFocus(){
  const f=document.getElementById('focus-input').value.trim();
  if(f) await postConfig({focus:f});
}

async function sendChat(){
  const el=document.getElementById('chat-input');
  const text=el.value.trim();
  el.value='';
  if(!text) return;
  appendMsg({role:'user',text,tick:lastTick});
  showStatus('sending...');
  try{
    await api('/api/chat',{text});
    await refresh();
  }catch(e){
    appendMsg({role:'system',text:'Chat request failed: '+e.message});
    showStatus('chat failed: '+e.message,true);
  }
}

async function doTick(){
  await api('/api/tick',{});
  await refresh();
}

async function doReset(){
  await api('/api/reset',{});
  spokenMessageKeys.clear();
  if(currentAudio) currentAudio.pause();
  document.getElementById('messages').innerHTML=
    '<div class="msg msg-system">Reset. Buckets cleared.</div>';
  lastMsgSignature='';
  await refresh();
}

async function doClearMemory(){
  if (!confirm("Are you sure you want to clear all semantic graph and episodic dialogue memory? This cannot be undone.")) return;
  await api('/api/clear_memory',{});
  spokenMessageKeys.clear();
  if(currentAudio) currentAudio.pause();
  document.getElementById('messages').innerHTML=
    '<div class="msg msg-system">Memory cleared. Knowledge graph and episodic dialogue wiped.</div>';
  lastMsgSignature='';
  await refresh();
}


function msgKey(m){
  return [m.role,m.tick||0,m.action||'',m.text||''].join('|');
}

function appendMsg(m, allowSpeech=true){
  const el=document.getElementById('messages');
  const div=document.createElement('div');
  if(m.role==='user'){
    div.className='msg msg-user';
    div.innerHTML=`<span class="msg-txt">${escHtml(m.text)}</span><button class="msg-play-btn" onclick="speakText(decodeURIComponent('${encodeURIComponent(m.text)}'), true)" title="Play message">▶</button>`;
  } else if(m.role==='agent'){
    div.className='msg msg-agent';
    const color=BUCKET_COLORS[m.bucket]||'var(--text2)';
    div.innerHTML=`<div class="msg-bucket" style="background:${color}22;color:${color}">${m.bucket||'agent'} / ${m.action||''}</div><span class="msg-txt">${escHtml(m.text)}</span><button class="msg-play-btn" onclick="speakText(decodeURIComponent('${encodeURIComponent(m.text)}'), true)" title="Play message">▶</button><div class="msg-meta">tick ${m.tick||0}</div>`;
  } else if(m.role==='thought'){
    div.className='msg msg-thought';
    div.innerHTML=`<div class="msg-meta">thought · tick ${m.tick||0}</div><span class="msg-txt">${escHtml(m.text)}</span><button class="msg-play-btn" onclick="speakText(decodeURIComponent('${encodeURIComponent(m.text)}'), true)" title="Play thought">▶</button>`;
  } else {
    div.className='msg msg-system';
    div.textContent=m.text;
  }
  el.appendChild(div);
  el.scrollTop=el.scrollHeight;
  if(m.role==='agent'){
    const key=msgKey(m);
    const isNew=!spokenMessageKeys.has(key);
    spokenMessageKeys.add(key);
    if(allowSpeech && isNew) speakText(m.text);
  }
}

function escHtml(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

async function refresh(){
  let state;
  try{
    state=await api('/api/state');
  }catch(e){
    showStatus('refresh failed: '+e.message,true);
    return;
  }
  if(!state) return;

  document.getElementById('tick-display').textContent='tick '+state.tick;
  lastTick=state.tick;
  dryRun=state.config.dry_run;
  document.getElementById('dry-btn').textContent=dryRun?'Enable live':'Enable dry run';
  document.getElementById('mode-badge').className='badge '+(dryRun?'badge-dry':'badge-live');
  document.getElementById('mode-badge').textContent=dryRun?'DRY RUN':'LIVE';
  const sel=document.getElementById('model-select');
  if(sel && state.config.model && sel.value!==state.config.model) sel.value=state.config.model;
  const vsel=document.getElementById('voice-select');
  if(vsel && state.config.voice && vsel.value!==state.config.voice) vsel.value=state.config.voice;
  const ms=state.model_status||{};
  const msEl=document.getElementById('model-status');
  if(msEl){
    if(ms.last_error){
      msEl.textContent='model error: '+ms.last_error.slice(0,120);
      msEl.style.color='var(--red)';
    } else if(ms.calls){
      msEl.textContent=`model calls ${ms.calls} · ${ms.last_model||state.config.model}`;
      msEl.style.color='var(--green)';
    } else {
      msEl.textContent='model idle';
      msEl.style.color='var(--text3)';
    }
  }

  const vision = state.vision || {};
  const camBtn = document.getElementById('cam-btn');
  if(camBtn){
    camBtn.textContent = browserCamStream ? 'Browser cam on' : 'Browser cam';
    camBtn.style.color = browserCamStream ? '' : 'var(--text1)';
    camBtn.title = 'Use this browser device camera';
  }
  if(!browserCamStream){
    const statusEl = document.getElementById('browser-cam-status');
    if(statusEl){
      if(vision.camera_error){
        statusEl.textContent = vision.camera_error;
        statusEl.style.color = 'var(--red)';
      } else if(vision.has_frame){
        statusEl.textContent = `${vision.camera_source || 'camera'} frame ${vision.frame_age_seconds ?? '?'}s`;
        statusEl.style.color = 'var(--green)';
      } else {
        statusEl.textContent = 'No frame';
        statusEl.style.color = 'var(--text3)';
      }
    }
    const faces = document.getElementById('browser-cam-faces');
    const source = document.getElementById('browser-cam-source');
    const light = document.getElementById('browser-cam-light');
    const motion = document.getElementById('browser-cam-motion');
    const attention = document.getElementById('browser-cam-attention');
    if(source) source.textContent = vision.camera_source || '-';
    if(light) light.textContent = Number(vision.brightness_level || 0).toFixed(2);
    if(faces) faces.textContent = vision.face_count ?? '-';
    if(motion) motion.textContent = Number(vision.motion_level || 0).toFixed(2);
    if(attention) attention.textContent = vision.attention_detected ? 'Yes' : 'No';
  }

  // buckets
  const p=state.pressures, t=state.thresholds;
  for(const [name,val] of Object.entries(p)){
    const thr=t[name]||0.5;
    const pct=Math.min(100,Math.round(val/Math.max(thr*1.5,val+0.001)*100));
    const valEl=document.getElementById('val-'+name);
    if(!valEl) continue;
    valEl.textContent=val.toFixed(3);
    const bar=document.getElementById('bar-'+name);
    if(!bar) continue;
    bar.style.width=pct+'%';
    const over=val>=thr;
    bar.style.background=over?'var(--red)':BUCKET_COLORS[name];
    const overEl=document.getElementById('over-'+name);
    if(overEl) overEl.textContent=over?'FIRING':'';
    const card=document.getElementById(BUCKET_IDS[name]);
    if(card && over) card.classList.add('fired-flash');
  }

  // signal sliders (only update display values, not slider positions, to avoid fighting user)
  for(const [k,v] of Object.entries(state.signals)){
    const lbl=document.getElementById('sv-'+k);
    if(lbl) lbl.textContent=(+v).toFixed(2);
  }

  // new messages
  const msgs=state.messages||[];
  const msgSignature=JSON.stringify(msgs.map(m=>[m.role,m.tick,m.action||'',m.text||'']));
  if(msgSignature!==lastMsgSignature){
    const allowSpeech=lastMsgSignature!=='';
    const el=document.getElementById('messages');
    el.innerHTML='';
    if(msgs.length){
      msgs.forEach(m=>appendMsg(m,allowSpeech));
    } else {
      appendMsg({role:'system',text:'Agent is running. Buckets are charging. Send a message or let it idle.'});
    }
    lastMsgSignature=msgSignature;
  }

  // journal
  const jel=document.getElementById('tab-journal');
  const journal=(state.journal||[]).slice().reverse();
  jel.innerHTML=journal.length?journal.map(e=>{
    const fired=e.dispatched;
    const pill=`<span class="pill ${fired?(e.action_type==='research'?'pill-research':'pill-reach'):'pill-blocked'}">${e.action_type}</span>`;
    const s=e.signals||{};
    return `<div class="jentry ${fired?'fired':'blocked'}">
      <div class="jentry-head">
        <span style="color:var(--text3);font-size:10px">t=${e.tick}</span>
        <span style="font-weight:600;color:${BUCKET_COLORS[e.bucket]||'var(--text)'}">${e.bucket}</span>
        ${pill}
        ${!fired?`<span style="font-size:10px;color:var(--text3)">${e.blocked_reason}</span>`:''}
      </div>
      <div style="font-size:11px;color:var(--text2);margin-bottom:2px">${escHtml(e.focus||'')}</div>
      <div class="jentry-signals">stress=${(s.user_stress||0).toFixed(2)} tasks=${(s.open_task_load||0).toFixed(2)} k_gap=${(s.knowledge_gap||0).toFixed(2)} t_int=${(s.time_since_interaction||0).toFixed(2)} · overshoot ${e.overshoot>0?'+':''}${(e.overshoot||0).toFixed(4)}</div>
    </div>`;
  }).join(''):'<div style="color:var(--text3);font-size:12px">No journal entries yet.</div>';

  // edge traffic
  const maxT=Math.max(...(state.edge_totals||[1]),1);
  const erows=document.getElementById('edge-rows');
  if(erows && state.edges){
    erows.innerHTML=state.edges.map((e,i)=>{
      const pct=Math.round((state.edge_totals[i]||0)/maxT*100);
      return `<div class="edge-row">
        <span class="edge-label">${e[0]}→${e[1]}</span>
        <div class="edge-track"><div class="edge-bar" style="width:${pct}%"></div></div>
        <span class="edge-cond">c=${e[4]}</span>
        <span style="min-width:44px;font-size:11px;color:var(--text3);text-align:right">${(state.edge_totals[i]||0).toFixed(3)}</span>
      </div>`;
    }).join('');
  }

  // knowledge store
  const ks=state.knowledge||{};
  const kel=document.getElementById('knowledge-list');
  const keys=Object.keys(ks);
  kel.innerHTML=keys.length?keys.map(k=>`<div class="ks-entry"><div class="ks-focus">${escHtml(k)}</div><div class="ks-note">${escHtml(ks[k])}</div></div>`).join('')
    :'<div style="color:var(--text3);font-size:12px">Nothing researched yet.</div>';

  // graph counts
  const gc = state.graph_counts||{nodes:0,edges:0};
  const gcel = document.getElementById('graph-counts');
  if(gcel) gcel.textContent = `${gc.nodes} nodes · ${gc.edges} edges`;

  // render knowledge graph canvas if tab is active
  if(document.getElementById('tab-knowledge').classList.contains('active')){
    renderKG();
  }

  // analyzer tab
  const cp = state.context_packet||{};
  const focusEl = document.getElementById('analyzer-focus');
  if(focusEl) focusEl.textContent = cp.focus_candidate ? `"${cp.focus_candidate}"` : '—';

  // primitive concept engine
  if(state.primitive){
    document.getElementById('prim-pressure-fill').style.width = (state.primitive.concept_pressure * 100) + '%';
    document.getElementById('prim-tentative-count').textContent = state.primitive.tentative_count;

    const tentEl = document.getElementById('prim-tentatives');
    if(tentEl){
        if(state.primitive.tentative_concepts.length === 0){
            tentEl.innerHTML = '<div style="color:var(--text3);font-size:12px">None yet.</div>';
        } else {
            tentEl.innerHTML = '';
            state.primitive.tentative_concepts.forEach(tc => {
                const c = document.createElement('div');
                c.className = 'ks-entry';
                c.innerHTML = `
                    <div class="ks-focus">${escHtml(tc.label)}</div>
                    <div class="ks-note">${tc.facts.map(escHtml).join('<br>')}</div>
                    <div style="display:flex;justify-content:space-between;color:var(--text3);font-size:10px;margin-top:4px">
                        <span>Conf: ${tc.confidence.toFixed(2)}</span>
                        <span>Support: ${tc.support_count}</span>
                    </div>
                `;
                tentEl.appendChild(c);
            });
        }
    }
  }

  const setList = (id, arr) => {
    const el = document.getElementById(id); if(!el) return;
    el.innerHTML = (arr&&arr.length) ? arr.map(t=>`<span style="display:inline-block;background:var(--bg3);border-radius:3px;padding:1px 6px;margin:1px 2px;font-size:11px">${escHtml(t)}</span>`).join('') : '<span style="color:var(--text3)">—</span>';
  };
  setList('analyzer-topics',   cp.active_topics);
  setList('analyzer-charge',   cp.emotional_charge);
  setList('analyzer-openings', cp.unresolved_openings);
  setList('analyzer-curiosity',cp.curiosity_targets);

  const depFill = document.getElementById('analyzer-depth-fill');
  if(depFill) depFill.style.width = ((cp.conversation_depth||0)*100)+'%';
  const wFill = document.getElementById('analyzer-weight-fill');
  if(wFill) wFill.style.width = ((cp.emotional_weight||0)*100)+'%';

  const relEl = document.getElementById('analyzer-relstate');
  if(relEl){
    const rel = cp.relationship_state||{};
    const keys = Object.keys(rel);
    relEl.innerHTML = keys.length ? keys.map(k=>{
      const v = rel[k];
      const col = v==='rising'?'var(--green)':v==='falling'?'#e87860':'var(--text3)';
      return `<span style="margin-right:10px"><span style="color:var(--text3)">${escHtml(k)}</span> <span style="color:${col}">${escHtml(v)}</span></span>`;
    }).join('') : '<span style="color:var(--text3)">—</span>';
  }

  const tEl = document.getElementById('analyzer-thoughts');
  if(tEl){
    const ij = state.internal_journal||[];
    tEl.innerHTML = ij.length ? ij.slice().reverse().map(t=>
      `<div style="margin-bottom:8px;padding:6px 8px;background:var(--bg2);border-radius:5px;border-left:2px solid var(--purple)">
        <div style="font-size:10px;color:var(--text3);margin-bottom:2px">tick ${t.tick} · ${escHtml(t.focus||'')}</div>
        <div>${escHtml(t.thought_note||'')}</div>
        ${t.possible_question?`<div style="color:var(--amber);margin-top:3px;font-size:11px">? ${escHtml(t.possible_question)}</div>`:''}
      </div>`
    ).join('') : '<span style="color:var(--text3)">No internal thoughts yet.</span>';
  }
}

let _kgData = {nodes:[], edges:[]};

async function renderKG(){
  try {
    const data = await api('/api/graph');
    _kgData = data;
  } catch(e){ return; }
  drawKG(_kgData);
  renderNodeList(_kgData);
}

function drawKG(data){
  const canvas = document.getElementById('kg-canvas');
  if(!canvas) return;
  const dpr = window.devicePixelRatio||1;
  const W = canvas.offsetWidth, H = canvas.offsetHeight||260;
  canvas.width = W*dpr; canvas.height = H*dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr,dpr);
  ctx.clearRect(0,0,W,H);

  const nodes = data.nodes||[], edges = data.edges||[];
  if(!nodes.length){
    ctx.fillStyle='#5a5a6e'; ctx.font='12px sans-serif'; ctx.textAlign='center';
    ctx.fillText('No knowledge nodes yet — start chatting.',W/2,H/2);
    return;
  }

  // simple force-directed layout (spring repulsion, baked into positions)
  const pos = {};
  // seed positions from node index
  nodes.forEach((n,i)=>{
    const angle = (i/nodes.length)*Math.PI*2;
    const r = Math.min(W,H)*0.32;
    pos[n.id]={x:W/2+r*Math.cos(angle), y:H/2+r*Math.sin(angle), vx:0, vy:0};
  });
  // iterate spring layout
  for(let iter=0;iter<80;iter++){
    // repulsion
    nodes.forEach(a=>{ nodes.forEach(b=>{
      if(a.id===b.id) return;
      const dx=pos[a.id].x-pos[b.id].x, dy=pos[a.id].y-pos[b.id].y;
      const d=Math.sqrt(dx*dx+dy*dy)||1;
      const f=600/(d*d);
      pos[a.id].vx+=dx/d*f; pos[a.id].vy+=dy/d*f;
    });});
    // attraction along edges
    edges.forEach(e=>{
      const s=pos[e.source], t=pos[e.target];
      if(!s||!t) return;
      const dx=t.x-s.x, dy=t.y-s.y, d=Math.sqrt(dx*dx+dy*dy)||1;
      const f=(d-70)*0.05;
      s.vx+=dx/d*f; s.vy+=dy/d*f;
      t.vx-=dx/d*f; t.vy-=dy/d*f;
    });
    // apply + dampen + clamp
    nodes.forEach(n=>{
      const p=pos[n.id];
      p.x+=p.vx*0.3; p.y+=p.vy*0.3;
      p.vx*=0.5; p.vy*=0.5;
      p.x=Math.max(36,Math.min(W-36,p.x));
      p.y=Math.max(16,Math.min(H-16,p.y));
    });
  }

  const TYPE_COLORS={'person':'#9a78e8','place':'#4ecc8a','topic':'#e8a830',
                     'object':'#5b8af0','event':'#e87860','concept':'#9898aa'};

  // draw edges
  edges.forEach(e=>{
    const s=pos[e.source], t=pos[e.target];
    if(!s||!t) return;
    ctx.beginPath();
    ctx.moveTo(s.x,s.y); ctx.lineTo(t.x,t.y);
    ctx.strokeStyle='#3a3a48'; ctx.lineWidth=1;
    ctx.stroke();
    // relation label at midpoint
    const mx=(s.x+t.x)/2, my=(s.y+t.y)/2;
    ctx.font='9px sans-serif'; ctx.fillStyle='#5a5a6e'; ctx.textAlign='center';
    ctx.fillText(e.relation, mx, my-3);
  });

  // draw nodes
  nodes.forEach(n=>{
    const p=pos[n.id]; if(!p) return;
    const color=TYPE_COLORS[n.type]||'#888780';
    const r=Math.max(14, Math.min(22, 12+n.facts.length*2));
    ctx.beginPath(); ctx.arc(p.x,p.y,r,0,Math.PI*2);
    ctx.fillStyle=color+'33'; ctx.fill();
    ctx.strokeStyle=color; ctx.lineWidth=1.5; ctx.stroke();
    ctx.font=`bold ${Math.min(11,Math.max(9,r-2))}px sans-serif`;
    ctx.fillStyle=color; ctx.textAlign='center'; ctx.textBaseline='middle';
    const lbl=n.label.length>10?n.label.slice(0,9)+'…':n.label;
    ctx.fillText(lbl, p.x, p.y);
  });
}

function renderNodeList(data){
  const el=document.getElementById('kg-node-list'); if(!el) return;
  const nodes=(data.nodes||[]).slice().sort((a,b)=>b.last_tick-a.last_tick);
  if(!nodes.length){ el.innerHTML=''; return; }
  el.innerHTML=nodes.slice(0,10).map(n=>{
    const facts=n.facts.slice(0,2).map(f=>`<span style="color:var(--text3)">${escHtml(f)}</span>`).join(' · ');
    return `<div style="display:flex;gap:6px;align-items:baseline;margin-bottom:4px;flex-wrap:wrap">
      <span style="font-weight:600;font-size:12px">${escHtml(n.label)}</span>
      <span style="font-size:10px;color:var(--amber);background:var(--bg3);padding:1px 5px;border-radius:3px">${n.type}</span>
      <span style="font-size:11px">${facts}</span>
    </div>`;
  }).join('');
}

function switchTab(name){
  document.querySelectorAll('.tab').forEach((t,i)=>{
    const names=['journal','graph','knowledge','analyzer','primitive','config'];
    t.classList.toggle('active',names[i]===name);
  });
  document.querySelectorAll('.tab-content').forEach(c=>{
    c.classList.toggle('active',c.id==='tab-'+name);
  });
}

// Auto ticks run the pressure system, including reach-out when a bucket crosses.
setInterval(async()=>{
  if(autoTickInFlight) return;
  autoTickInFlight=true;
  try{
    await api('/api/tick',{auto:true});
    await refresh();
  }catch(e){
    showStatus('tick failed: '+e.message,true);
  }finally{
    autoTickInFlight=false;
  }
},4000);

// poll for state every second
setInterval(()=>{ refresh(); },1000);

let browserCamStream = null;
let browserCamInterval = null;
let feedInterval = null;

function setBrowserCamPlaceholder(titleText, helpVisible=false) {
  const placeholder = document.getElementById('browser-cam-placeholder');
  const title = document.getElementById('browser-cam-placeholder-title');
  const help = document.getElementById('browser-cam-help-text');
  if (placeholder) placeholder.style.display = 'flex';
  if (title) title.textContent = titleText;
  if (help) help.style.display = helpVisible ? 'block' : 'none';
}

function setupFeedRefresh() {
  const img = document.getElementById('browser-cam-feed');
  const placeholder = document.getElementById('browser-cam-placeholder');
  if (!img) return;

  img.onload = () => {
    if (browserCamStream) return;
    img.style.display = 'block';
    if (placeholder) placeholder.style.display = 'none';
  };

  img.onerror = () => {
    if (browserCamStream) return;
    img.style.display = 'none';
    setBrowserCamPlaceholder('Camera Off');
  };

  if (!feedInterval) {
    feedInterval = setInterval(() => {
      if (browserCamStream) return;
      img.src = '/api/camera_feed?t=' + Date.now();
    }, 500);
  }
}

async function toggleBrowserCam() {
  const btn = document.getElementById('browser-cam-btn');
  const topBtn = document.getElementById('cam-btn');
  const video = document.getElementById('browser-cam-video');
  const feedImg = document.getElementById('browser-cam-feed');
  const placeholder = document.getElementById('browser-cam-placeholder');
  const statusEl = document.getElementById('browser-cam-status');

  if (browserCamStream) {
    stopBrowserCam();
    return;
  }

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    statusEl.textContent = 'Insecure Context';
    showStatus('browser camera requires HTTPS, localhost, or a trusted insecure-origin browser setting', true);
    setBrowserCamPlaceholder('Secure Context Required', true);
    if (feedImg) feedImg.style.display = 'none';
    stopBrowserCam();
    return;
  }

  statusEl.textContent = 'Requesting access...';
  try {
    browserCamStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 320 }, height: { ideal: 240 } }
    });
    video.srcObject = browserCamStream;
    video.style.display = 'block';
    if (feedImg) feedImg.style.display = 'none';
    placeholder.style.display = 'none';
    btn.textContent = 'Stop Browser Cam';
    btn.classList.add('danger');
    btn.classList.remove('primary');
    if (topBtn) topBtn.textContent = 'Browser cam on';
    statusEl.textContent = 'Active';

    const canvas = document.createElement('canvas');
    canvas.width = 160;
    canvas.height = 120;
    const ctx = canvas.getContext('2d');

    browserCamInterval = setInterval(async () => {
      if (!browserCamStream) return;
      try {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.6);
        const res = await api('/api/vision_frame', { image: dataUrl });
        if (res && res.state) {
          document.getElementById('browser-cam-faces').textContent = res.state.face_count;
          const srcEl = document.getElementById('browser-cam-source');
          const lightEl = document.getElementById('browser-cam-light');
          if(srcEl) srcEl.textContent = res.state.camera_source || 'browser';
          if(lightEl) lightEl.textContent = Number(res.state.brightness_level || 0).toFixed(2);
          document.getElementById('browser-cam-motion').textContent = res.state.motion_level.toFixed(2);
          document.getElementById('browser-cam-attention').textContent = res.state.attention_detected ? 'Yes' : 'No';
          statusEl.textContent = 'Streaming';
        }
      } catch (e) {
        console.error('Failed to send vision frame:', e);
        statusEl.textContent = 'Error';
      }
    }, 250);
  } catch (err) {
    console.error('Camera access failed:', err);
    statusEl.textContent = 'Failed';
    setBrowserCamPlaceholder(err && err.name === 'NotAllowedError' ? 'Access Denied' : 'Camera Failed');
    stopBrowserCam();
  }
}

function stopBrowserCam() {
  const btn = document.getElementById('browser-cam-btn');
  const video = document.getElementById('browser-cam-video');
  const feedImg = document.getElementById('browser-cam-feed');
  const placeholder = document.getElementById('browser-cam-placeholder');
  const statusEl = document.getElementById('browser-cam-status');

  if (browserCamInterval) {
    clearInterval(browserCamInterval);
    browserCamInterval = null;
  }
  if (browserCamStream) {
    browserCamStream.getTracks().forEach(track => track.stop());
    browserCamStream = null;
  }
  if (video) {
    video.srcObject = null;
    video.style.display = 'none';
  }
  if (feedImg) {
    feedImg.src = '/api/camera_feed?t=' + Date.now();
  }
  if (placeholder) {
    placeholder.style.display = 'flex';
    if (statusEl && statusEl.textContent !== 'Insecure Context') {
      setBrowserCamPlaceholder('Camera Off');
    }
  }
  if (btn) {
    btn.textContent = 'Start Browser Cam';
    btn.classList.remove('danger');
    btn.classList.add('primary');
  }
  const topBtn = document.getElementById('cam-btn');
  if (topBtn) topBtn.textContent = 'Browser cam';
  if (statusEl) statusEl.textContent = 'Inactive';

  const faces = document.getElementById('browser-cam-faces');
  const source = document.getElementById('browser-cam-source');
  const light = document.getElementById('browser-cam-light');
  const motion = document.getElementById('browser-cam-motion');
  const attention = document.getElementById('browser-cam-attention');
  if (source) source.textContent = '-';
  if (light) light.textContent = '-';
  if (faces) faces.textContent = '-';
  if (motion) motion.textContent = '-';
  if (attention) attention.textContent = '-';
}

async function init() {
  const state = await api('/api/state');
  const activeModel = (state && state.config) ? state.config.model : null;
  await loadModels(activeModel);
  await refresh();
  setupFeedRefresh();
}
init();
</script>
</body>
</html>
"""

# ── Mobile HTML frontend ───────────────────────────────────────────────────────────
MOBILE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Household Agent Chat</title>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<style>
  :root{
    --bg:#0f0f11;--bg2:#17171a;--bg3:#1e1e23;--bg4:#26262d;
    --border:#2e2e38;--border2:#3a3a48;
    --text:#e8e8ee;--text2:#9898aa;--text3:#5a5a6e;
    --blue:#5b8af0;--blue2:#3a6ad4;
    --purple:#9a78e8;
    --radius:12px;
  }
  *{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
  body{background:var(--bg);color:var(--text);height:100vh;height:100dvh;display:flex;flex-direction:column;overflow:hidden}

  #topbar{display:flex;align-items:center;justify-content:space-between;padding:12px;border-bottom:1px solid var(--border);background:var(--bg2);flex-shrink:0}
  #topbar h1{font-size:16px;font-weight:600;letter-spacing:.02em}
  .voice-btn{background:var(--bg3);border:1px solid var(--border2);color:var(--text2);border-radius:12px;padding:4px 10px;font-size:12px;cursor:pointer}
  .voice-btn.active{background:var(--blue2);color:#fff;border-color:var(--blue)}

  #messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
  #messages::-webkit-scrollbar{width:0px;background:transparent;} /* Hide scrollbar for mobile */

  .msg{max-width:88%;padding:12px 14px;border-radius:var(--radius);font-size:15px;line-height:1.4}
  .msg-user{align-self:flex-end;background:var(--blue2);color:#fff;border-radius:var(--radius) var(--radius) 4px var(--radius)}
  .msg-agent{align-self:flex-start;background:var(--bg3);border:1px solid var(--border2)}
  .msg-thought{align-self:flex-start;background:#201d2a;border:1px dashed var(--purple);color:var(--text2);font-style:italic;font-size:14px}
  .msg-play-btn{background:transparent;border:none;color:inherit;cursor:pointer;font-size:12px;padding:2px 6px;margin-left:8px;opacity:.5;transition:opacity .2s,transform .2s;display:inline-flex;align-items:center;justify-content:center;border-radius:4px}
  .msg-play-btn:hover{opacity:1;transform:scale(1.15);background:rgba(255,255,255,0.1)}


  #input-area{padding:12px;background:var(--bg2);border-top:1px solid var(--border);flex-shrink:0;padding-bottom:calc(12px + env(safe-area-inset-bottom));}
  .input-wrapper{display:flex;gap:8px;align-items:flex-end}
  textarea{flex:1;background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:20px;padding:10px 14px;font-size:16px;outline:none;resize:none;max-height:100px;min-height:42px;line-height:1.4}
  textarea:focus{border-color:var(--blue)}
  button{background:var(--blue2);border:none;color:#fff;border-radius:20px;height:42px;padding:0 18px;font-size:15px;font-weight:600;cursor:pointer}
  button:active{background:var(--blue)}
</style>
</head>
<body>

<div id="topbar">
  <h1>Household Agent</h1>
  <div style="display:flex;gap:6px;align-items:center">
    <select id="mobile-model-select" style="max-width:110px;background:var(--bg3);color:var(--text);border:1px solid var(--border2);border-radius:12px;padding:4px 8px;font-size:12px;outline:none;" onchange="setModel(this.value)">
      <option value="">Loading...</option>
    </select>
    <button id="mobile-voice-btn" class="voice-btn active" onclick="toggleVoice()">Voice on</button>
    <button id="mobile-cam-btn" class="voice-btn" onclick="toggleBrowserCam()">Cam off</button>
  </div>
</div>

<div id="mobile-cam-container" style="display:none;background:var(--bg2);border-bottom:1px solid var(--border);padding:10px;text-align:center">
  <div style="position:relative;width:160px;height:120px;background:#000;border-radius:var(--radius);overflow:hidden;margin:0 auto 8px">
    <video id="browser-cam-video" autoplay playsinline muted style="position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;transform:scaleX(-1);display:none;"></video>
    <img id="browser-cam-feed" src="/api/camera_feed" style="position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;transform:scaleX(-1);display:none;">
  </div>
  <div style="font-size:11px;color:var(--text2)">
    Source: <span id="browser-cam-source">-</span> | Light: <span id="browser-cam-light">-</span><br>
    Faces: <span id="browser-cam-faces">-</span> | Motion: <span id="browser-cam-motion">-</span> | Attention: <span id="browser-cam-attention">-</span>
  </div>
</div>

<div id="messages"></div>

<div id="input-area">
  <div class="input-wrapper">
    <textarea id="chat-input" placeholder="Message..." rows="1" oninput="this.style.height='';this.style.height=this.scrollHeight+'px'" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendChat()}"></textarea>
    <button onclick="sendChat()">Send</button>
  </div>
</div>

<script>
let lastTick = -1;
let voiceEnabled = true;
let currentAudio = null;
let lastMsgSignature = '';

function toggleVoice() {
  voiceEnabled = !voiceEnabled;
  const btn = document.getElementById('mobile-voice-btn');
  btn.textContent = voiceEnabled ? 'Voice on' : 'Voice off';
  btn.className = voiceEnabled ? 'voice-btn active' : 'voice-btn';

  // Unlock mobile audio context on first tap
  if (voiceEnabled && !currentAudio) {
    currentAudio = new Audio();
    currentAudio.play().catch(()=>{});
  }
}

async function api(path, body) {
  const opts = body
    ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body), cache: 'no-store'}
    : {cache: 'no-store'};
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${path} returned ${r.status}`);
  return r.json();
}

function escHtml(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function sendChat() {
  const inp = document.getElementById('chat-input');
  const text = inp.value.trim();
  if (!text) return;

  // Unlock mobile audio context on send tap
  if (voiceEnabled && !currentAudio) {
    currentAudio = new Audio();
    currentAudio.play().catch(()=>{});
  }

  inp.value = '';
  inp.style.height = '42px';

  // Optimistically add user message
  const msgEl = document.createElement('div');
  msgEl.className = 'msg msg-user';
  msgEl.innerHTML = `<span class="msg-txt">${escHtml(text)}</span><button class="msg-play-btn" onclick="speakText(decodeURIComponent('${encodeURIComponent(text)}'), true)" title="Play message">▶</button>`;
  document.getElementById('messages').appendChild(msgEl);
  scrollToBottom();

  try {
    await api('/api/chat', {text});
    refreshState();
  } catch (e) {
    console.error(e);
  }
}

async function speakText(text, force = false){
  if((!force && !voiceEnabled) || !text) return;
  try{
    const r=await fetch('/api/tts',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text}),
      cache:'no-store'
    });
    if(!r.ok) throw new Error('speech returned '+r.status);
    const blob=await r.blob();
    const url=URL.createObjectURL(blob);
    if(!currentAudio) currentAudio=new Audio();
    currentAudio.pause();
    currentAudio.src = url;
    currentAudio.onended=()=>URL.revokeObjectURL(url);
    await currentAudio.play();
  }catch(e){
    console.error('speech failed: '+e.message);
  }
}

function scrollToBottom() {
  const m = document.getElementById('messages');
  m.scrollTop = m.scrollHeight;
}

let lastMsgCount = -1;
let isScrolledUp = false;
document.getElementById('messages').addEventListener('scroll', (e) => {
    const el = e.target;
    isScrolledUp = (el.scrollHeight - el.scrollTop - el.clientHeight) > 20;
});

async function refreshState() {
  try {
    const data = await api('/api/state');
    const sel = document.getElementById('mobile-model-select');
    if (sel && data.config && data.config.model && sel.value !== data.config.model) {
      sel.value = data.config.model;
    }
    if (data.tick === lastTick && data.messages.length === lastMsgCount) return;
    lastTick = data.tick;
    lastMsgCount = data.messages.length;

    const m = document.getElementById('messages');
    m.innerHTML = '';

    data.messages.forEach(msg => {
      const d = document.createElement('div');
      if (msg.role === 'user') {
        d.className = 'msg msg-user';
        d.innerHTML = `<span class="msg-txt">${escHtml(msg.text).replace(/\n/g, '<br>')}</span><button class="msg-play-btn" onclick="speakText(decodeURIComponent('${encodeURIComponent(msg.text)}'), true)" title="Play message">▶</button>`;
      } else if (msg.role === 'thought') {
        d.className = 'msg msg-thought';
        d.innerHTML = `<span class="msg-txt">${escHtml(msg.text).replace(/\n/g, '<br>')}</span><button class="msg-play-btn" onclick="speakText(decodeURIComponent('${encodeURIComponent(msg.text)}'), true)" title="Play thought">▶</button>`;
      } else {
        d.className = 'msg msg-agent';
        d.innerHTML = `<span class="msg-txt">${escHtml(msg.text).replace(/\n/g, '<br>')}</span><button class="msg-play-btn" onclick="speakText(decodeURIComponent('${encodeURIComponent(msg.text)}'), true)" title="Play message">▶</button>`;
      }
      m.appendChild(d);
    });

    if (!isScrolledUp) scrollToBottom();

    // TTS trigger
    if(voiceEnabled && data.messages.length > 0){
      const last = data.messages[data.messages.length - 1];
      const sig = last.tick + '_' + last.role + '_' + last.text.length;
      if(last.role === 'agent' && sig !== lastMsgSignature){
        lastMsgSignature = sig;
        speakText(last.text);
      }
    }
  } catch (e) {
    console.error(e);
  }
}

let browserCamStream = null;
let browserCamInterval = null;
let feedInterval = null;

function setupFeedRefresh() {
  const img = document.getElementById('browser-cam-feed');
  const container = document.getElementById('mobile-cam-container');
  if (!img) return;

  img.onload = () => {
    if (browserCamStream) return;
    img.style.display = 'block';
    if (container) container.style.display = 'block';
  };

  img.onerror = () => {
    if (browserCamStream) return;
    img.style.display = 'none';
    if (container) container.style.display = 'none';
  };

  if (!feedInterval) {
    feedInterval = setInterval(() => {
      if (browserCamStream) return;
      img.src = '/api/camera_feed?t=' + Date.now();
    }, 500);
  }
}

async function toggleBrowserCam() {
  const btn = document.getElementById('mobile-cam-btn');
  const container = document.getElementById('mobile-cam-container');
  const video = document.getElementById('browser-cam-video');
  const feedImg = document.getElementById('browser-cam-feed');

  if (browserCamStream) {
    stopBrowserCam();
    return;
  }

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert('Webcam requires a Secure Context (HTTPS or localhost).\n\nTo enable on your laptop/phone:\n1. Open Chrome/Edge.\n2. Go to chrome://flags/#unsafely-treat-insecure-origin-as-secure\n3. Add ' + window.location.origin + ' and enable.\n4. Relaunch browser.');
    return;
  }

  try {
    browserCamStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 320 }, height: { ideal: 240 } }
    });
    video.srcObject = browserCamStream;
    container.style.display = 'block';
    video.style.display = 'block';
    if (feedImg) feedImg.style.display = 'none';
    btn.textContent = 'Cam on';
    btn.classList.add('active');

    const canvas = document.createElement('canvas');
    canvas.width = 160;
    canvas.height = 120;
    const ctx = canvas.getContext('2d');

    browserCamInterval = setInterval(async () => {
      if (!browserCamStream) return;
      try {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.6);
        const res = await api('/api/vision_frame', { image: dataUrl });
        if (res && res.state) {
          document.getElementById('browser-cam-faces').textContent = res.state.face_count;
          const srcEl = document.getElementById('browser-cam-source');
          const lightEl = document.getElementById('browser-cam-light');
          if(srcEl) srcEl.textContent = res.state.camera_source || 'browser';
          if(lightEl) lightEl.textContent = Number(res.state.brightness_level || 0).toFixed(2);
          document.getElementById('browser-cam-motion').textContent = res.state.motion_level.toFixed(2);
          document.getElementById('browser-cam-attention').textContent = res.state.attention_detected ? 'Yes' : 'No';
        }
      } catch (e) {
        console.error('Failed to send mobile vision frame:', e);
      }
    }, 250);
  } catch (err) {
    console.error('Mobile camera access failed:', err);
    alert('Failed to access camera: ' + err.message);
    stopBrowserCam();
  }
}

function stopBrowserCam() {
  const btn = document.getElementById('mobile-cam-btn');
  const container = document.getElementById('mobile-cam-container');
  const video = document.getElementById('browser-cam-video');
  const feedImg = document.getElementById('browser-cam-feed');

  if (browserCamInterval) {
    clearInterval(browserCamInterval);
    browserCamInterval = null;
  }
  if (browserCamStream) {
    browserCamStream.getTracks().forEach(track => track.stop());
    browserCamStream = null;
  }
  if (video) {
    video.srcObject = null;
    video.style.display = 'none';
  }
  if (feedImg) {
    feedImg.src = '/api/camera_feed?t=' + Date.now();
  } else if (container) {
    container.style.display = 'none';
  }
  if (btn) {
    btn.textContent = 'Cam off';
    btn.classList.remove('active');
  }

  const faces = document.getElementById('browser-cam-faces');
  const source = document.getElementById('browser-cam-source');
  const light = document.getElementById('browser-cam-light');
  const motion = document.getElementById('browser-cam-motion');
  const attention = document.getElementById('browser-cam-attention');
  if (source) source.textContent = '-';
  if (light) light.textContent = '-';
  if (faces) faces.textContent = '-';
  if (motion) motion.textContent = '-';
  if (attention) attention.textContent = '-';
}

async function loadModels(activeModel){
  try {
    const data = await api('/api/models');
    const sel = document.getElementById('mobile-model-select');
    if(!sel) return;
    sel.innerHTML = '';
    (data.models || []).forEach(m => {
      const o = document.createElement('option');
      o.value = m; o.textContent = m;
      if (activeModel && m === activeModel) o.selected = true;
      sel.appendChild(o);
    });
  } catch(e) {
    console.error(e);
  }
}

async function setModel(v) {
  try {
    await api('/api/config', {model: v});
  } catch(e) {
    console.error(e);
  }
}

async function init() {
  const state = await api('/api/state');
  const activeModel = (state && state.config) ? state.config.model : null;
  await loadModels(activeModel);
  await refreshState();
  setupFeedRefresh();
}

init();
setInterval(refreshState, 1500);
</script>
</body>
</html>
"""

class SafeThreadingHTTPServer(ThreadingHTTPServer):
    ssl_context = None

    def get_request(self):
        sock, addr = super().get_request()
        if self.ssl_context is not None:
            sock = self.ssl_context.wrap_socket(sock, server_side=True, do_handshake_on_connect=False)
        return sock, addr

    def handle_error(self, request, client_address):
        import sys
        exctype, value, tb = sys.exc_info()
        if exctype in (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, ssl.SSLError):
            return
        super().handle_error(request, client_address)

# ── main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Household Agent GUI server")
    parser.add_argument("--host", default="0.0.0.0", help="Host/interface to bind")
    parser.add_argument("--port", type=int, default=7437, help="Port to listen on")
    parser.add_argument("--model", default=None, help="Ollama model name")
    parser.add_argument("--live", action="store_true", help="Call the model (default for the web server)")
    parser.add_argument("--dry", action="store_true", help="Force dry-run mode")
    parser.add_argument("--local-cam", action="store_true", help="Use the server machine's local camera instead of browser camera input")
    parser.add_argument("--no-cam", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--http", action="store_true", help="Serve plain HTTP instead of HTTPS")
    parser.add_argument("--certfile", default=os.path.join("certs", "server.crt"), help="TLS certificate file for HTTPS")
    parser.add_argument("--keyfile", default=os.path.join("certs", "server.key"), help="TLS private key file for HTTPS")
    args = parser.parse_args()

    _configure_runtime(model=args.model, live=(args.live or not args.dry), dry=args.dry)
    if not pe.load_state():
        pe.reset()

    local_camera_allowed = bool(args.local_cam and not args.no_cam)
    if local_camera_allowed:
        vision_sensor.start()
    else:
        vision_sensor.set_idle("none", "")
        print("[Vision] Browser camera mode. Waiting for /api/vision_frame from the user's browser device.")
    HOST, PORT = args.host, args.port
    server = SafeThreadingHTTPServer((HOST, PORT), Handler)
    use_https = not args.http
    scheme = "https" if use_https else "http"
    if use_https:
        certfile = os.path.abspath(args.certfile)
        keyfile = os.path.abspath(args.keyfile)
        if not os.path.exists(certfile) or not os.path.exists(keyfile):
            raise FileNotFoundError(
                f"HTTPS certificate files are missing: {certfile} and {keyfile}. "
                "Create them or start with --http."
            )
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=certfile, keyfile=keyfile)
        server.ssl_context = ctx

    local_url = f"{scheme}://localhost:{PORT}"
    lan_ip = _get_lan_ip()
    lan_url = f"{scheme}://{lan_ip}:{PORT}"
    shown_url = lan_url if HOST in ("0.0.0.0", "", "::") else f"{scheme}://{HOST}:{PORT}"
    print(f"\nHousehold Agent running")
    print(f"Local : {local_url}", flush=True)
    print(f"Laptop: {shown_url}", flush=True)
    print(f"Camera: browser device camera over {'HTTPS' if use_https else 'HTTP'}")
    print(f"Model : {pe.CONFIG['OLLAMA_MODEL']}")
    print(f"Mode  : {'LIVE  (real model calls)' if not pe.CONFIG['DRY_RUN'] else 'DRY RUN  (switch to live in the GUI or pass --live)'}")
    print(f"\nPress Ctrl+C to stop.\n")
    threading.Timer(1.0, lambda: webbrowser.open(local_url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
