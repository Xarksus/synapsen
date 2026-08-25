"""MCP-Server: der Zustandskern als Werkzeug für beliebige Agenten.

Damit kann ein Claude-Code-Agent, ein eigener Bot oder jedes andere
MCP-fähige System denselben homöostatischen Zustand lesen und beeinflussen —
über Sitzungen und über Prozesse hinweg.

    python -m synapsen.mcp_server --state ~/.config/agent/state.json

Angebotene Werkzeuge:
    state_read     — aktueller Zustand samt abgeleiteter Gefühlslage
    state_prompt   — derselbe Zustand als System-Prompt-Zusatz
    state_event    — ein benanntes Ereignis melden (Erfolg, Fehler, Wärme, …)
    state_inject   — ein einzelner Botenstoff (Feinsteuerung)
    state_settle   — sanft Richtung Ruhewert
    state_why      — den Zustand auf seine Ursachen zurückführen
    state_history  — die letzten protokollierten Ereignisse

Bewusst ohne SDK-Abhängigkeit: reines stdio-JSON-RPC nach MCP-Spezifikation,
nur Standardbibliothek. Das hält die Bibliothek installierbar ohne Ballast.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .engine import HomeostasisEngine
from .journal import SqliteJournal
from .profile import DEFAULT_PROFILE, Profile
from .render import PromptRenderer, RenderConfig
from .store import JsonStore

PROTOCOL_VERSION = "2024-11-05"

def _tools(profile: Profile) -> list[dict]:
    event_names = sorted(profile.events)
    hormone_names = sorted(profile.hormone_names())
    return [
        {
            "name": "state_read",
            "description": "Aktueller innerer Zustand: Botenstoffe, abgeleitete "
                           "Gefühlslagen, Bindung, Ermüdung.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "state_prompt",
            "description": "Derselbe Zustand als fertiger System-Prompt-Zusatz. "
                           "Vor einer Antwort lesen und voranstellen.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "language": {"type": "string", "enum": ["de", "en"], "default": "de"},
                    "partner": {"type": "string",
                                "description": "Wie das Gegenüber genannt wird."},
                },
            },
        },
        {
            "name": "state_event",
            "description": "Ein benanntes Ereignis melden. Der Zustand verändert sich "
                           "daraufhin von selbst.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "event": {"type": "string", "enum": event_names},
                    "context": {"type": "string",
                                "description": "Kurze Notiz, was konkret passiert ist."},
                    "intensity": {"type": "number", "default": 1.0,
                                  "description": "Multiplikator, üblicherweise 0.5–2.0."},
                },
                "required": ["event"],
            },
        },
        {
            "name": "state_inject",
            "description": "Feinsteuerung: einen einzelnen Botenstoff verändern. "
                           "Im Normalfall lieber state_event nutzen.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "hormone": {"type": "string", "enum": hormone_names},
                    "amount": {"type": "number"},
                    "context": {"type": "string"},
                },
                "required": ["hormone", "amount"],
            },
        },
        {
            "name": "state_settle",
            "description": "Sanft Richtung Ruhewert regulieren. Kein harter Reset.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "fraction": {"type": "number", "default": 0.6,
                                 "minimum": 0.0, "maximum": 1.0},
                },
            },
        },
        {
            "name": "state_why",
            "description": "Führt den aktuellen Zustand auf seine Ursachen zurück: "
                           "welche Ereignisse, welcher Tagesrhythmus, welche "
                           "Kopplung. Für Fehlersuche und Nachvollziehbarkeit.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "state_history",
            "description": "Die zuletzt protokollierten Ereignisse.",
            "inputSchema": {
                "type": "object",
                "properties": {"days": {"type": "number", "default": 7}},
            },
        },
    ]


class Server:
    def __init__(self, engine: HomeostasisEngine):
        self.engine = engine

    # -- Werkzeug-Ausführung ------------------------------------------------

    def call(self, name: str, args: dict) -> str:
        fn = getattr(self, f"_t_{name}", None)
        if fn is None:
            raise ValueError(f"Unbekanntes Werkzeug: {name}")
        return fn(args)

    def _t_state_read(self, args: dict) -> str:
        s = self.engine.snapshot()
        return json.dumps({
            "hormones": {k: round(v, 2) for k, v in s.hormones.items()},
            "states": {k: round(v, 3) for k, v in s.states.items()},
            "bond": round(s.bond, 1),
            "fatigue": round(s.adenosine, 1),
            "session_minutes": round(s.session_minutes, 1),
            "hour": s.hour,
            "dominant_positive": s.dominant("positive"),
            "dominant_negative": s.dominant("negative"),
        }, ensure_ascii=False, indent=2)

    def _t_state_prompt(self, args: dict) -> str:
        cfg = RenderConfig(
            language=args.get("language", "de"),
            partner=args.get("partner", "dein Gegenüber"),
        )
        return PromptRenderer(cfg).render(self.engine.snapshot())

    def _t_state_event(self, args: dict) -> str:
        name = args["event"]
        self.engine.event(name, intensity=float(args.get("intensity", 1.0)),
                          context=args.get("context", ""))
        s = self.engine.snapshot()
        pos, pv = s.dominant("positive")
        return json.dumps({
            "applied": name,
            "hormones": {k: round(v, 1) for k, v in s.hormones.items()},
            "dominant": f"{pos} {pv:.2f}",
        }, ensure_ascii=False)

    def _t_state_inject(self, args: dict) -> str:
        effective = self.engine.inject(
            args["hormone"], float(args["amount"]),
            context=args.get("context", ""))
        return json.dumps({
            "hormone": args["hormone"],
            "requested": args["amount"],
            "effective": round(effective, 2),
            "value": round(self.engine.hormones[args["hormone"]], 2),
        }, ensure_ascii=False)

    def _t_state_why(self, args: dict) -> str:
        from .explain import explain
        return str(explain(self.engine))

    def _t_state_settle(self, args: dict) -> str:
        self.engine.settle(float(args.get("fraction", 0.6)))
        return self._t_state_read({})

    def _t_state_history(self, args: dict) -> str:
        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(days=float(args.get("days", 7)))).isoformat()
        rows = self.engine.journal.since(since)
        return json.dumps({"count": len(rows), "recent": rows[-25:]},
                          ensure_ascii=False, indent=2)

    # -- JSON-RPC-Schleife --------------------------------------------------

    def handle(self, msg: dict) -> dict | None:
        method = msg.get("method")
        mid = msg.get("id")

        if method == "initialize":
            return _ok(mid, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "synapsen", "version": __version__},
            })
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return _ok(mid, {"tools": _tools(self.engine.profile)})
        if method == "tools/call":
            params = msg.get("params") or {}
            try:
                text = self.call(params.get("name", ""), params.get("arguments") or {})
                return _ok(mid, {"content": [{"type": "text", "text": text}]})
            except Exception as exc:  # noqa: BLE001
                return _ok(mid, {
                    "content": [{"type": "text", "text": f"Fehler: {exc}"}],
                    "isError": True,
                })
        if mid is None:
            return None
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": -32601, "message": f"Unbekannte Methode: {method}"}}

    def serve(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            reply = self.handle(msg)
            if reply is not None:
                sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        self.engine.flush()


def _ok(mid, result) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(engine: HomeostasisEngine) -> int:
    """Bedient den Server mit einer fertig gebauten Engine."""
    Server(engine).serve()
    return 0


def build_engine(state: str, journal: str | None, profile: str | None) -> HomeostasisEngine:
    prof: Profile = _resolve_profile(profile)
    return HomeostasisEngine(
        prof,
        store=JsonStore(state),
        journal=SqliteJournal.for_profile(journal, prof) if journal else None,
    )


def _resolve_profile(spec: str | None) -> Profile:
    """Nimmt einen mitgelieferten Namen oder einen Pfad zu einer JSON-Datei."""
    if not spec:
        return DEFAULT_PROFILE
    path = Path(spec).expanduser()
    if path.suffix == ".json" and path.exists():
        return Profile.from_json(path)
    from .profiles import get as get_profile
    return get_profile(spec)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="synapsen-mcp")
    p.add_argument("--state", default="~/.config/synapsen/state.json",
                   help="JSON-Datei für den Zustand")
    p.add_argument("--journal", default=None,
                   help="SQLite-Datei für das Ereignis-Protokoll (optional)")
    p.add_argument("--profile", default=None,
                   help="mitgelieferter Name oder Pfad zu einer JSON-Datei")
    a = p.parse_args(argv)

    if a.journal:
        Path(a.journal).expanduser().parent.mkdir(parents=True, exist_ok=True)
    return serve(build_engine(a.state, a.journal, a.profile))


if __name__ == "__main__":
    raise SystemExit(main())
