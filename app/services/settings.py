from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

DEFAULT_SETTINGS: dict[str, Any] = {
    "ollama_base_url": "http://localhost:11434",
    "ollama_model": "llava",
    "verify_prompt": (
        "You are a strict slide QA reviewer. Check whether any text is cut off, "
        "missing, overlapping, or too close to the edges. Reply with JSON only: "
        '{"ok": true|false, "issues": ["..."], "recommendations": ["..."]}.'
    ),
    "title_font_path": "",
    "body_font_path": "",
    "label_font_path": "",
    "title_font_size": 112,
    "body_font_size": 84,
    "label_font_size": 56,
    "title_font_min": 70,
    "text_color": "#F8F7F2",
    "stroke_color": "#1A1A1A",
    "stroke_width": 8,
    "line_spacing": 0.2,
    "slide_width": 1920,
    "slide_height": 1080,
    "title_box": [140, 200, 1640, 680],
    "label_pos": [140, 110],
    "content_box": [140, 200, 1640, 800],
    "centered_sections": ["Hymn", "Song", "Prayer Song", "Sending Hymn"],
}


def _env_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _env_settings() -> dict[str, Any]:
    settings: dict[str, Any] = {}
    base_url = os.getenv("OLLAMA_BASE_URL")
    if base_url and base_url.strip():
        settings["ollama_base_url"] = base_url
    model = os.getenv("OLLAMA_MODEL")
    if model and model.strip():
        settings["ollama_model"] = model
    title_font = os.getenv("TITLE_FONT_PATH")
    if title_font and title_font.strip():
        settings["title_font_path"] = title_font
    body_font = os.getenv("BODY_FONT_PATH")
    if body_font and body_font.strip():
        settings["body_font_path"] = body_font
    label_font = os.getenv("LABEL_FONT_PATH")
    if label_font and label_font.strip():
        settings["label_font_path"] = label_font
    slide_width = _env_int("SLIDE_WIDTH")
    if slide_width is not None:
        settings["slide_width"] = slide_width
    slide_height = _env_int("SLIDE_HEIGHT")
    if slide_height is not None:
        settings["slide_height"] = slide_height
    return settings


def _settings_file(data_dir: Path) -> Path:
    return data_dir / "settings.json"


def get_settings(data_dir: Path) -> dict[str, Any]:
    load_dotenv()
    settings = dict(DEFAULT_SETTINGS)
    file_path = _settings_file(data_dir)
    if file_path.exists():
        stored = json.loads(file_path.read_text(encoding="utf-8"))
        settings.update(stored)
    settings.update(_env_settings())
    return settings


def update_settings(data_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = set(DEFAULT_SETTINGS.keys())
    current = dict(DEFAULT_SETTINGS)
    file_path = _settings_file(data_dir)
    if file_path.exists():
        stored = json.loads(file_path.read_text(encoding="utf-8"))
        current.update(stored)
    for key, value in payload.items():
        if key in allowed_keys:
            current[key] = value
    file_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return get_settings(data_dir)
