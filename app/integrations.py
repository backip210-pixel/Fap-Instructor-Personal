from __future__ import annotations

import os
import time
from typing import Any

import requests

REMOTE = os.getenv("ENABLE_REMOTE_INTEGRATIONS", "false").lower() == "true"
HANDY_API_BASE = os.getenv("HANDY_API_BASE", "https://www.handyfeeling.com/api/handy/v2").rstrip("/")
HANDY_SCRIPT_API = os.getenv("HANDY_SCRIPT_API", "https://scripts01.handyfeeling.com/api/script/v0").rstrip("/")
LOVENSE_BASIC_API = os.getenv("LOVENSE_BASIC_API", "https://api.lovense-api.com/api/basicApi").rstrip("/")
LOVENSE_API_TOKEN = os.getenv("LOVENSE_API_TOKEN", "")
AUTOBLOW_LATENCY_URL = os.getenv("AUTOBLOW_LATENCY_URL", "https://latency.autoblowapi.com/autoblow/connected")


def _mock(device_type: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "mock": True,
        "deviceType": device_type,
        "action": action,
        "payload": payload or {},
        "message": "Remote integrations are disabled; command was simulated and logged.",
    }


def _safe_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        resp = requests.request(method, url, timeout=12, **kwargs)
        content_type = resp.headers.get("content-type", "")
        body: Any
        if "json" in content_type:
            body = resp.json()
        else:
            body = resp.text[:2000]
        return {"ok": resp.ok, "status": resp.status_code, "body": body}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def test_device(device_type: str, config: dict[str, Any]) -> dict[str, Any]:
    device_type = device_type.lower()
    if not REMOTE:
        return _mock(device_type, "test", {"configKeys": sorted(config.keys())})

    if device_type == "handy":
        key = config.get("connectionKey") or config.get("connection_key")
        if not key:
            return {"ok": False, "error": "Missing Handy connection key"}
        return _safe_request("GET", f"{HANDY_API_BASE}/connected", headers={"X-Connection-Key": key})

    if device_type == "lovense":
        if not LOVENSE_API_TOKEN:
            return {"ok": False, "error": "LOVENSE_API_TOKEN is not configured"}
        uid = config.get("uid") or config.get("userId")
        if not uid:
            return {"ok": False, "error": "Missing Lovense uid/userId"}
        return _safe_request("POST", f"{LOVENSE_BASIC_API}/getToys", data={"token": LOVENSE_API_TOKEN, "uid": uid})

    if device_type == "autoblow":
        return _safe_request("GET", AUTOBLOW_LATENCY_URL)

    return {"ok": False, "error": f"Unknown device type: {device_type}"}


def send_device_command(device_type: str, config: dict[str, Any], command: dict[str, Any]) -> dict[str, Any]:
    device_type = device_type.lower()
    action = str(command.get("action") or "tempo")
    if not REMOTE:
        return _mock(device_type, action, command)

    if device_type == "handy":
        key = config.get("connectionKey") or config.get("connection_key")
        if not key:
            return {"ok": False, "error": "Missing Handy connection key"}
        headers = {"X-Connection-Key": key, "Content-Type": "application/json"}
        if action in {"tempo", "stroke", "velocity"}:
            tempo = int(command.get("tempo") or command.get("velocity") or 60)
            velocity = max(0, min(100, int((tempo / 180) * 100)))
            return _safe_request("PUT", f"{HANDY_API_BASE}/hamp/velocity", headers=headers, json={"velocity": velocity})
        if action == "stop":
            return _safe_request("PUT", f"{HANDY_API_BASE}/hamp/velocity", headers=headers, json={"velocity": 0})
        if action == "position":
            return _safe_request("PUT", f"{HANDY_API_BASE}/hdsp/xpt", headers=headers, json={"position": int(command.get("position", 50)), "duration": int(command.get("duration", 1000))})
        return _safe_request("POST", f"{HANDY_API_BASE}/command", headers=headers, json=command)

    if device_type == "lovense":
        if not LOVENSE_API_TOKEN:
            return {"ok": False, "error": "LOVENSE_API_TOKEN is not configured"}
        uid = config.get("uid") or config.get("userId")
        toy = config.get("toy") or config.get("toyId") or ""
        strength = int(command.get("strength") or min(20, max(1, int((int(command.get("tempo", 60)) / 120) * 20))))
        data = {
            "token": LOVENSE_API_TOKEN,
            "uid": uid,
            "command": command.get("lovenseCommand") or f"Vibrate:{strength}",
        }
        if toy:
            data["toy"] = toy
        return _safe_request("POST", f"{LOVENSE_BASIC_API}/sendCommand", data=data)

    if device_type == "autoblow":
        endpoint = config.get("endpoint")
        if not endpoint:
            return {"ok": False, "error": "Autoblow endpoint is not configured"}
        return _safe_request("POST", endpoint, json=command, headers={"Authorization": f"Bearer {config.get('token', '')}"} if config.get("token") else {})

    return {"ok": False, "error": f"Unknown device type: {device_type}"}


def upload_handy_script(config: dict[str, Any], funscript: dict[str, Any]) -> dict[str, Any]:
    if not REMOTE:
        return _mock("handy", "upload-script", {"actions": len(funscript.get("actions", []))})
    key = config.get("connectionKey") or config.get("connection_key")
    if not key:
        return {"ok": False, "error": "Missing Handy connection key"}
    # Script API accepts multipart in production; this endpoint intentionally keeps it generic.
    files = {"file": ("script.funscript", str(funscript).encode("utf-8"), "application/json")}
    data = {"name": f"fapinstructor-{int(time.time())}.funscript"}
    return _safe_request("POST", f"{HANDY_SCRIPT_API}/upload", headers={"X-Connection-Key": key}, data=data, files=files)
