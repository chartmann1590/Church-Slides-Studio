from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import requests


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("No JSON object found.")


def verify_slide_image(image_path: str, settings: dict[str, Any]) -> dict[str, Any]:
    base_url = settings.get("ollama_base_url", "http://localhost:11434").rstrip("/")
    model = settings.get("ollama_model", "")
    prompt = settings.get("verify_prompt", "")
    if not model:
        return {"ok": False, "issues": ["Ollama model not configured."], "raw": ""}

    image_bytes = Path(image_path).read_bytes()
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "images": [encoded],
    }
    try:
        response = requests.post(
            f"{base_url}/api/generate",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        raw = data.get("response", "")
        parsed = _extract_json(raw)
        return {"ok": parsed.get("ok", False), "issues": parsed.get("issues", []), "raw": raw}
    except Exception as exc:
        return {"ok": False, "issues": [f"Ollama verification failed: {exc}"], "raw": ""}
