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
    "stroke-grip",
    "stroke-style",
    "media",
    "game-over",
}

EVENT_CATALOG = [
    {"type": "chat-message", "label": "Message", "defaults": {"text": "Follow the timer.", "speech": "Follow the timer.", "duration": 4}},
    {"type": "instruction", "label": "Choice / check-in", "defaults": {"title": "Check in", "description": "Pause, slow down, or continue.", "duration": 8, "options": [{"title": "Continue", "events": []}, {"title": "Slow down", "events": [{"type": "stroke-tempo", "tempo": 50}]}]}},
    {"type": "wait", "label": "Wait / rest", "defaults": {"duration": 10}},
    {"type": "metronome", "label": "Set metronome", "defaults": {"tempo": 70, "measure": "4/4"}},
    {"type": "metronome-wait", "label": "Count beats", "defaults": {"count": 16}},
    {"type": "stroke", "label": "Timed tempo segment", "defaults": {"tempo": 70, "duration": 20, "grip": "normal", "style": "full"}},
    {"type": "stroke-tempo", "label": "Change tempo", "defaults": {"tempo": 90}},
    {"type": "stroke-grip", "label": "Change grip", "defaults": {"grip": "normal"}},
    {"type": "stroke-style", "label": "Change style", "defaults": {"style": "full"}},
    {"type": "media", "label": "Image / video cue", "defaults": {"url": "", "mediaType": "video", "duration": 20}},
    {"type": "game-over", "label": "Complete", "defaults": {"message": "Complete"}},
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
    if typ in {"metronome", "stroke-tempo", "stroke-grip", "stroke-style", "clear-chat-message"}:
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
    out.setdefault("id", uuid.uuid4().hex[:12])
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
        else:
            time_ms += event_duration(event, tempo) * 1000

    if not actions:
        actions = [FunscriptAction(at=0, pos=50), FunscriptAction(at=1000, pos=50)]
    return {"version": "1.0", "inverted": False, "range": 90, "metadata": {"generator": "fapinstructor-personal"}, "actions": [a.__dict__ for a in actions]}


def generate_game_from_config(config: dict[str, Any], instructor: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rng = random.Random(config.get("seed") or random.randrange(1_000_000_000))
    duration_minutes = float(config.get("durationMinutes") or config.get("duration_minutes") or 5)
    min_tempo = int(config.get("minTempo") or config.get("min_tempo") or 45)
    max_tempo = int(config.get("maxTempo") or config.get("max_tempo") or 120)
    intensity = str(config.get("intensity") or "medium")
    include_media = bool(config.get("includeMedia", False))
    include_instructions = bool(config.get("includeInstructions", True))

    target = max(60, int(duration_minutes * 60))
    events: list[dict[str, Any]] = [normalize_event({"type": "chat-message", "text": "Session starting. Follow the metronome and pause if needed.", "speech": "Session starting. Follow the metronome and pause if needed.", "duration": 5})]
    tempo = rng.randint(min_tempo, max_tempo)
    events.append(normalize_event({"type": "metronome", "tempo": tempo, "measure": "4/4"}))

    elapsed = compute_duration(events)
    cycle = 0
    while elapsed < target - 20:
        cycle += 1
        tempo = rng.randint(min_tempo, max_tempo)
        duration = rng.randint(12, 35) if intensity != "low" else rng.randint(8, 22)
        events.append(normalize_event({"type": "stroke", "tempo": tempo, "duration": duration, "grip": rng.choice(["light", "normal", "firm"]), "style": rng.choice(["full", "short"])}))
        if rng.random() < 0.30:
            events.append(normalize_event({"type": "wait", "duration": rng.randint(5, 15)}))
        if include_instructions and cycle % 3 == 0:
            events.append(normalize_event({"type": "instruction", "title": "Check in", "description": "Adjust the pace or continue.", "duration": 6, "options": [{"title": "Continue", "events": []}, {"title": "Slow tempo", "events": [{"type": "stroke-tempo", "tempo": max(min_tempo, tempo - 20)}]}]}))
        if include_media and rng.random() < 0.15:
            events.append(normalize_event({"type": "media", "url": config.get("mediaUrl", ""), "mediaType": "video", "duration": 15}))
        elapsed = compute_duration(events)

    events.append(normalize_event({"type": "game-over", "message": "Complete"}))
    return events
