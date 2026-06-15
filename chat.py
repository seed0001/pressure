"""
Household agent — interactive chat loop.

Run:  python chat.py
      python chat.py --model mistral:latest
      python chat.py --model llama3.2 --live    (disables dry-run)

Each time you send a message the engine ticks once.
Type nothing and press Enter to let the engine tick on its own (idle tick).
Type /help for commands.
"""

import sys
import time
import argparse
import pressure_engine as pe

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── CLI args ─────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Household agent chat")
parser.add_argument("--model",  default=None, help="Ollama model name")
parser.add_argument("--live",   action="store_true", help="Disable DRY_RUN (make real model calls)")
parser.add_argument("--focus",  default="general household needs", help="Starting focus subject")
args = parser.parse_args()

if args.model:
    pe.CONFIG["OLLAMA_MODEL"] = args.model
if args.live:
    pe.CONFIG["DRY_RUN"] = False

# ── Signal state ──────────────────────────────────────────────────────────────
# These float between 0.0–1.0 and are updated each tick based on what's happening.
signals = {
    "user_stress":             0.1,
    "time_since_interaction":  0.0,   # resets on every user message
    "open_task_load":          0.4,
    "knowledge_gap":           0.3,
    "time_since_contribution": 0.0,   # resets when agent fires an action
}

# how fast time_since_interaction climbs per idle tick
INTERACTION_DRIFT = 0.06
CONTRIBUTION_DRIFT = 0.05

focus_subject = args.focus
tick_count = 0

# ── Simple stress heuristic from message text ─────────────────────────────────
STRESS_WORDS = {
    "stressed","overwhelmed","tired","exhausted","busy","worried","anxious",
    "behind","late","deadline","hard","struggling","too much","can't",
    "frustrated","stuck","help","urgent","problem","broken","bad day"
}
CALM_WORDS = {"good","great","fine","relaxed","calm","done","finished","better","thanks","thank"}

def infer_stress(text: str) -> float:
    words = set(text.lower().split())
    hits_stress = len(words & STRESS_WORDS)
    hits_calm   = len(words & CALM_WORDS)
    delta = (hits_stress - hits_calm) * 0.15
    return max(0.0, min(1.0, signals["user_stress"] + delta))

# ── Display helpers ───────────────────────────────────────────────────────────
BUCKET_COLORS = {
    "Decompress": "\033[32m",   # green
    "Contribute": "\033[34m",   # blue
    "Learn":      "\033[33m",   # amber
    "Connect":    "\033[35m",   # purple
}
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RED    = "\033[31m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"

BAR_WIDTH = 20

def pressure_bar(name: str, pressure: float, threshold: float) -> str:
    filled = int(min(pressure / max(threshold * 1.5, pressure + 0.01), 1.0) * BAR_WIDTH)
    bar    = "#" * filled + "-" * (BAR_WIDTH - filled)
    over   = pressure >= threshold
    color  = RED if over else BUCKET_COLORS.get(name, "")
    marker = " !" if over else "  "
    return f"  {color}{name:<12}{RESET} [{color}{bar}{RESET}] {pressure:.3f}/{threshold:.2f}{marker}"

def print_status():
    pressures = pe.get_pressures()
    thresholds = {n: c["threshold"] for n, c in pe.CONFIG["buckets"].items()}
    print(f"\n{DIM}── tick {tick_count} ──────────────────────────────────{RESET}")
    for name in pressures:
        print(pressure_bar(name, pressures[name], thresholds[name]))
    model = pe.CONFIG["OLLAMA_MODEL"]
    mode  = "LIVE" if not pe.CONFIG["DRY_RUN"] else "DRY RUN"
    print(f"{DIM}  model: {model}  mode: {mode}  focus: {focus_subject}{RESET}\n")

def print_agent_message(text: str):
    print(f"\n{CYAN}{BOLD}[agent]{RESET} {text}\n")

def print_system(text: str):
    print(f"{DIM}  {text}{RESET}")

def print_help():
    print(f"""
{BOLD}Commands{RESET}
  /stress <0-10>    set user stress manually (e.g. /stress 7)
  /tasks  <0-10>    set open task load
  /gap    <0-10>    set knowledge gap
  /focus  <text>    change what the agent is focused on
  /model  <name>    switch Ollama model mid-session
  /live             toggle dry-run off (enable real model calls)
  /dry              toggle dry-run on
  /status           show current bucket pressures
  /journal          dump the agent's journal
  /outbox           show messages queued for you
  /reset            reset all pressures to zero
  /quit             exit
  <Enter>           idle tick (agent thinks without your input)
""")

def handle_command(cmd: str) -> bool:
    """Returns True if the line was a command."""
    global focus_subject
    parts = cmd.strip().split(None, 1)
    word  = parts[0].lower()

    if word == "/help":
        print_help()
        return True

    if word == "/status":
        print_status()
        return True

    if word == "/stress" and len(parts) == 2:
        signals["user_stress"] = max(0.0, min(1.0, float(parts[1]) / 10))
        print_system(f"user_stress = {signals['user_stress']:.2f}")
        return True

    if word == "/tasks" and len(parts) == 2:
        signals["open_task_load"] = max(0.0, min(1.0, float(parts[1]) / 10))
        print_system(f"open_task_load = {signals['open_task_load']:.2f}")
        return True

    if word == "/gap" and len(parts) == 2:
        signals["knowledge_gap"] = max(0.0, min(1.0, float(parts[1]) / 10))
        print_system(f"knowledge_gap = {signals['knowledge_gap']:.2f}")
        return True

    if word == "/focus" and len(parts) == 2:
        focus_subject = parts[1]
        print_system(f"focus = {focus_subject!r}")
        return True

    if word == "/model" and len(parts) == 2:
        pe.CONFIG["OLLAMA_MODEL"] = parts[1]
        print_system(f"model = {parts[1]}")
        return True

    if word == "/live":
        pe.CONFIG["DRY_RUN"] = False
        print_system("DRY_RUN disabled — real model calls active")
        return True

    if word == "/dry":
        pe.CONFIG["DRY_RUN"] = True
        print_system("DRY_RUN enabled")
        return True

    if word == "/journal":
        journal = pe.get_journal()
        if not journal:
            print_system("Journal is empty.")
        for e in journal[-10:]:
            status = "fired" if e["dispatched"] else f"blocked ({e['blocked_reason']})"
            print(f"  t={e['tick']:>3} {e['bucket']:<12} {e['action_type']:<12} "
                  f"focus={e.get('focus','?')!r:<30} {status}")
        return True

    if word == "/outbox":
        outbox = pe.get_outbox()
        if not outbox:
            print_system("Outbox is empty.")
        for i, msg in enumerate(outbox[-5:], 1):
            snippet = msg[:120].replace("\n", " ")
            print(f"  [{i}] {snippet}")
        return True

    if word == "/reset":
        pe.reset()
        signals.update({"user_stress":0.1,"time_since_interaction":0.0,
                        "open_task_load":0.4,"knowledge_gap":0.3,
                        "time_since_contribution":0.0})
        print_system("Pressures reset.")
        return True

    if word in ("/quit", "/exit", "/q"):
        print_system("Goodbye.")
        sys.exit(0)

    return False

def do_tick(user_spoke: bool, user_text: str = ""):
    global tick_count, focus_subject
    tick_count += 1

    direct_reply_sent = False
    if user_spoke and user_text:
        reply = pe.handle_passive_response(dict(signals), user_text, focus_subject=focus_subject)
        if reply:
            print_agent_message(reply)
            pe.push_chat_history("assistant", reply)
            direct_reply_sent = True

    focus_map = {name: focus_subject for name in pe.CONFIG["buckets"]}
    fired_log, _ = pe.tick(signals, focus_map)

    # after tick: drift interaction gap up if user hasn't spoken
    if user_spoke:
        signals["time_since_interaction"] = 0.0
    else:
        signals["time_since_interaction"] = min(1.0,
            signals["time_since_interaction"] + INTERACTION_DRIFT)

    # surface any dispatched actions to the user
    visible_reply_sent = False
    for entry in fired_log:
        if entry.get("blocked"):
            continue
        payload = entry.get("payload", "")
        if not payload:
            continue

        action = entry["action_type"]
        bucket = entry["bucket"]

        if action == "internal_thought":
            print_system(f"[thought] {payload}")
            visible_reply_sent = True
            continue

        if user_spoke:
            continue

        if action == "reach_out":
            if pe.CONFIG["DRY_RUN"]:
                print_agent_message(
                    f"[DRY RUN] Would reach out ({bucket}) re: {focus_subject}"
                )
                visible_reply_sent = True
            else:
                # payload IS the model's message — surface it directly
                print_agent_message(payload)
                visible_reply_sent = True

        elif action == "research":
            if pe.CONFIG["DRY_RUN"]:
                print_agent_message(
                    f"[DRY RUN] Would research: {focus_subject}"
                )
                visible_reply_sent = True
            else:
                # extract USER DIGEST section if present
                digest = ""
                for line in payload.splitlines():
                    if line.startswith("USER DIGEST:"):
                        digest = line[len("USER DIGEST:"):].strip()
                if digest:
                    print_agent_message(f"[Research] {digest}")
                    visible_reply_sent = True
                else:
                    print_agent_message(f"[Research] {payload[:200]}")
                    visible_reply_sent = True

        # contribution lowers time_since_contribution
        signals["time_since_contribution"] = max(
            0.0, signals["time_since_contribution"] - 0.4
        )

    if user_spoke and user_text and not direct_reply_sent:
        reply = pe.handle_passive_response(dict(signals), user_text)
        if reply:
            print_agent_message(reply)
            pe.push_chat_history("assistant", reply)

# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    pe.reset()

    print(f"""
{BOLD}Household agent{RESET}
Model : {pe.CONFIG['OLLAMA_MODEL']}
Mode  : {'LIVE' if not pe.CONFIG['DRY_RUN'] else 'DRY RUN  (use --live or /live to enable real calls)'}
Focus : {focus_subject}

Type a message to chat. Press Enter alone for an idle tick.
Type /help for commands.
""")

    print_status()

    while True:
        try:
            raw = input(f"{BOLD}you >{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not raw:
            # idle tick — time passes, agent thinks
            print_system("(idle tick)")
            signals["time_since_contribution"] = min(
                1.0, signals["time_since_contribution"] + CONTRIBUTION_DRIFT
            )
            do_tick(user_spoke=False)
            print_status()
            continue

        if raw.startswith("/"):
            if handle_command(raw):
                continue
            else:
                print_system(f"Unknown command: {raw}  (type /help)")
                continue

        # it's a real message — update signals from content
        signals["user_stress"] = infer_stress(raw)

        # let the agent "hear" what was said by routing it as a user message
        # and noting it as a low-level focus update
        pe.push_chat_history("user", raw, analyze=True)
        if len(raw) > 10:
            # use the message as focus context if it looks substantive
            pass   # perception layer (Layer 4) will do this properly

        do_tick(user_spoke=True, user_text=raw)
        print_status()

if __name__ == "__main__":
    main()
