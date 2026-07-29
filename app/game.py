from __future__ import annotations

import random
import re
import uuid
from dataclasses import dataclass
from typing import Any

SAFE_EVENT_TYPES = {
    "wait",
    "chat-message",
    "clear-chat-message",
    "instruction",
    "metronome",
    "metronome-wait",
    "stroke",
    "stroke-tempo",
    "stroke-tempo-percent",
    "stroke-grip",
    "stroke-style",
    "stroke-hand",
    "stroke-clench",
    "stroke-double-speed",
    "stroke-acceleration",
    "stroke-red-light-green-light",
    "cluster-strokes",
    "teasing-strokes",
    "edge",
    "orgasm",
    "ruined-orgasm",
    "premature-ruin",
    "eyes",
    "audio",
    "media",
    "device",
    "status-effect",
    "interact",
    "reset",
    "thread",
    "game-over",
    # Adult optional categories present in the source site. These are user-authored only here.
    "anal",
    "cbt",
    "nipples",
    "mouth",
    "lungs",
    "moan",
    "cei",
}

EVENT_CATALOG = [
    {"type": "chat-message", "label": "Instructor message", "defaults": {"text": "Stay aware of your limits.", "speech": "Stay aware of your limits.", "duration": 4}},
    {"type": "instruction", "label": "Interactive instruction", "defaults": {"title": "Consent check", "description": "Pause or stop at any time.", "duration": 8, "options": [{"title": "Continue", "events": []}, {"title": "Slow down", "events": [{"type": "stroke-tempo", "tempo": 50}]}]}},
    {"type": "wait", "label": "Wait / rest", "defaults": {"duration": 10}},
    {"type": "metronome", "label": "Set metronome", "defaults": {"tempo": 70, "measure": "4/4"}},
    {"type": "stroke", "label": "Timed tempo segment", "defaults": {"tempo": 70, "duration": 20, "grip": "normal", "style": "full", "hand": "dominant"}},
    {"type": "stroke-tempo", "label": "Change tempo", "defaults": {"tempo": 90}},
    {"type": "stroke-grip", "label": "Change grip", "defaults": {"grip": "normal"}},
    {"type": "stroke-style", "label": "Change style", "defaults": {"style": "full"}},
    {"type": "metronome-wait", "label": "Count beats", "defaults": {"count": 16}},
    {"type": "edge", "label": "Edge marker", "defaults": {"duration": 15, "cooldown": 10}},
    {"type": "orgasm", "label": "Orgasm outcome", "defaults": {"orgasm": {"type": "deny", "edgeDuration": 15, "edgeCountdown": 5}}},
    {"type": "media", "label": "Remote media cue", "defaults": {"url": "", "mediaType": "video", "duration": 20}},
    {"type": "device", "label": "Device command", "defaults": {"command": {"action": "tempo", "tempo": 70}, "duration": 10}},
    {"type": "game-over", "label": "Game over", "defaults": {"message": "Complete"}},
]


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or uuid.uuid4().hex[:8]


def event_duration(event: dict[str, Any], tempo: int | float | None = None) -> int:
    typ = event.get("type")
    if isinstance(event.get("duration"), (int, float)):
        return max(0, int(event["duration"]))
    if typ == "wait":
        return int(event.get("duration", 0) or 0)
    if typ == "chat-message":
        text = event.get("speech") or event.get("text") or ""
        return int(event.get("duration") or max(3, min(20, len(str(text)) // 12)))
    if typ == "instruction":
        return int(event.get("duration") or 8)
    if typ == "metronome-wait":
        t = tempo or event.get("tempo") or 60
        count = event.get("count") or 4
        return int((60 / max(1, float(t))) * int(count))
    if typ in {"metronome", "stroke-tempo", "stroke-grip", "stroke-style", "stroke-hand", "clear-chat-message", "reset", "status-effect"}:
        return 1
    if typ == "game-over":
        return 0
    return 5


def compute_duration(events: list[dict[str, Any]]) -> int:
    total = 0
    tempo: int | float | None = 60
    for event in events:
        if event.get("type") in ("metronome", "stroke", "stroke-tempo") and event.get("tempo"):
            tempo = event.get("tempo")
        total += event_duration(event, tempo)
    return total


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError("Each event must be an object")
    typ = str(event.get("type", "")).strip()
    if typ not in SAFE_EVENT_TYPES:
        raise ValueError(f"Unsupported event type: {typ or '<missing>'}")
    out = dict(event)
    out["type"] = typ
    if "id" not in out:
        out["id"] = uuid.uuid4().hex[:12]
    if "duration" in out:
        try:
            out["duration"] = max(0, int(float(out["duration"])))
        except Exception:
            out["duration"] = 0
    if "tempo" in out:
        try:
            out["tempo"] = max(1, min(240, int(float(out["tempo"]))))
        except Exception:
            out["tempo"] = 60
    return out


def normalize_events(events: Any) -> list[dict[str, Any]]:
    if events is None:
        return []
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    return [normalize_event(e) for e in events]


@dataclass
class FunscriptAction:
    at: int
    pos: int


def events_to_funscript(events: list[dict[str, Any]]) -> dict[str, Any]:
    """A pragmatic FunScript export: tempo events become oscillating position actions."""
    actions: list[FunscriptAction] = []
    time_ms = 0
    tempo = 60
    pos_low, pos_high = 10, 90

    def add_segment(duration_s: int, bpm: int) -> None:
        nonlocal time_ms
        beat_ms = max(200, int(60000 / max(1, bpm)))
        end = time_ms + duration_s * 1000
        pos = pos_low
        while time_ms < end:
            actions.append(FunscriptAction(at=time_ms, pos=pos))
            pos = pos_high if pos == pos_low else pos_low
            time_ms += beat_ms // 2
        time_ms = end

    for event in events:
        typ = event.get("type")
        if typ in {"metronome", "stroke-tempo"} and event.get("tempo"):
            tempo = int(event["tempo"])
        if typ == "stroke":
            tempo = int(event.get("tempo") or tempo)
            add_segment(event_duration(event, tempo), tempo)
        elif typ == "device" and event.get("command", {}).get("tempo"):
            add_segment(event_duration(event, tempo), int(event["command"]["tempo"]))
        else:
            time_ms += event_duration(event, tempo) * 1000

    if not actions:
        actions = [FunscriptAction(at=0, pos=50), FunscriptAction(at=1000, pos=50)]
    return {
        "version": "1.0",
        "inverted": False,
        "range": 90,
        "metadata": {"generator": "fapinstructor-docker"},
        "actions": [a.__dict__ for a in actions],
    }


def generate_game_from_config(config: dict[str, Any], instructor: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rng = random.Random(config.get("seed") or random.randrange(1_000_000_000))
    duration_minutes = float(config.get("durationMinutes") or config.get("duration_minutes") or 8)
    min_tempo = int(config.get("minTempo") or config.get("min_tempo") or 45)
    max_tempo = int(config.get("maxTempo") or config.get("max_tempo") or 120)
    intensity = str(config.get("intensity") or "medium")
    include_edges = bool(config.get("includeEdges", True))
    include_media = bool(config.get("includeMedia", False))
    include_instructions = bool(config.get("includeInstructions", True))

    target = max(60, int(duration_minutes * 60))
    events: list[dict[str, Any]] = []
    name = (instructor or {}).get("name", "Instructor")
    events.append(normalize_event({"type": "chat-message", "text": f"{name}: session starting. Respect your limits and stop when needed.", "speech": "Session starting. Respect your limits and stop when needed.", "duration": 5}))
    elapsed = compute_duration(events)
    tempo = rng.randint(min_tempo, max_tempo)
    events.append(normalize_event({"type": "metronome", "tempo": tempo, "measure": "4/4"}))

    cycle = 0
    while elapsed < target - 20:
        cycle += 1
        tempo = rng.randint(min_tempo, max_tempo)
        stroke_duration = rng.randint(12, 35) if intensity != "low" else rng.randint(8, 22)
        events.append(normalize_event({"type": "stroke", "tempo": tempo, "duration": stroke_duration, "grip": rng.choice(["light", "normal", "firm"]), "style": rng.choice(["full", "short", "tip"])}))
        if rng.random() < 0.30:
            rest = rng.randint(5, 15)
            events.append(normalize_event({"type": "wait", "duration": rest}))
        if include_instructions and cycle % 3 == 0:
            events.append(normalize_event({
                "type": "instruction",
                "title": "Check-in",
                "description": "Adjust intensity, hydrate, or pause if you need to.",
                "duration": 6,
                "options": [
                    {"title": "Continue", "events": []},
                    {"title": "Slow tempo", "events": [{"type": "stroke-tempo", "tempo": max(min_tempo, tempo - 20)}]},
                ],
            }))
        if include_edges and cycle % 4 == 0:
            events.append(normalize_event({"type": "edge", "duration": rng.randint(10, 20), "cooldown": rng.randint(5, 15)}))
        if include_media and rng.random() < 0.15:
            events.append(normalize_event({"type": "media", "url": config.get("mediaUrl", ""), "mediaType": "video", "duration": 15}))
        elapsed = compute_duration(events)

    outcome = str(config.get("outcome") or rng.choice(["deny", "edge", "finish"])).lower()
    if outcome == "finish":
        events.append(normalize_event({"type": "orgasm", "orgasm": {"type": "cum", "edgeDuration": 20, "edgeCountdown": 5}}))
    elif outcome == "edge":
        events.append(normalize_event({"type": "orgasm", "orgasm": {"type": "edge", "edgeDuration": 20, "cooldown": 10}}))
    else:
        events.append(normalize_event({"type": "orgasm", "orgasm": {"type": "deny", "edgeDuration": 10, "edgeCountdown": 5}}))
    events.append(normalize_event({"type": "game-over", "message": "Complete"}))
    return events
