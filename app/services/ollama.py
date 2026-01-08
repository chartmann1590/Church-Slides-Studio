from __future__ import annotations

import base64
import logging
import json
import re
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    candidates: list[str] = []
    if text.startswith("{") and text.endswith("}"):
        candidates.append(text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])
    if not candidates:
        raise ValueError("No JSON object found.")
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            repaired = _repair_jsonish(candidate)
            if repaired != candidate:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError as exc2:
                    last_error = exc2
            parsed = _parse_jsonish(candidate)
            if parsed is not None:
                return parsed
    raise last_error or ValueError("No JSON object found.")


def _repair_jsonish(text: str) -> str:
    repaired = re.sub(r",\s*([}\]])", r"\1", text)
    repaired = re.sub(
        r'(\btrue\b|\bfalse\b|\bnull\b)\s+(")',
        r"\1, \2",
        repaired,
        flags=re.IGNORECASE,
    )
    repaired = re.sub(r'([}\]])\s+(")', r"\1, \2", repaired)
    repaired = re.sub(r'(")\s+(")', r"\1, \2", repaired)
    return repaired


def _extract_list_value(text: str, key: str) -> list[str]:
    string_match = re.search(
        rf'"{re.escape(key)}"\s*:\s*"([^"]*)"', text, flags=re.IGNORECASE
    )
    if string_match:
        return [string_match.group(1)]
    list_match = re.search(
        rf'"{re.escape(key)}"\s*:\s*\[(.*?)\]', text, flags=re.IGNORECASE | re.DOTALL
    )
    if not list_match:
        return []
    list_text = "[" + list_match.group(1) + "]"
    list_text = _repair_jsonish(list_text)
    try:
        parsed = json.loads(list_text)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        if isinstance(parsed, str):
            return [parsed]
    except json.JSONDecodeError:
        return [value.replace('\\"', '"') for value in re.findall(r'"([^"]+)"', list_text)]
    return []


def _parse_jsonish(text: str) -> dict[str, Any] | None:
    ok_match = re.search(r'"ok"\s*:\s*(true|false)', text, flags=re.IGNORECASE)
    issues = _extract_list_value(text, "issues")
    recommendations = _extract_list_value(text, "recommendations")
    if ok_match or issues or recommendations:
        ok_value = False
        if ok_match:
            ok_value = ok_match.group(1).strip().lower() == "true"
        return {
            "ok": ok_value,
            "issues": issues,
            "recommendations": recommendations,
        }
    return None


def verify_slide_image(image_path: str, settings: dict[str, Any]) -> dict[str, Any]:
    base_url = settings.get("ollama_base_url", "http://localhost:11434").rstrip("/")
    model = settings.get("ollama_model", "")
    prompt = settings.get("verify_prompt", "")
    logger.info(
        "Ollama verify start: model=%s url=%s image=%s",
        model or "none",
        base_url,
        image_path,
    )
    if not model:
        logger.warning("Ollama verify skipped: model not configured.")
        return {
            "ok": False,
            "issues": ["Ollama model not configured."],
            "recommendations": [],
            "raw": "",
        }

    image_bytes = Path(image_path).read_bytes()
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [encoded],
            }
        ],
        "stream": False,
    }
    try:
        response = requests.post(
            f"{base_url}/api/chat",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        raw = ""
        if isinstance(data, dict):
            message = data.get("message", {})
            if isinstance(message, dict):
                raw = message.get("content", "") or ""
            if not raw:
                raw = data.get("response", "") or ""
        logger.debug("Ollama verify raw response: %s", raw)
        parsed = _extract_json(raw)
        issues = parsed.get("issues", [])
        if isinstance(issues, str):
            issues = [issues]
        recommendations = parsed.get("recommendations", [])
        if isinstance(recommendations, str):
            recommendations = [recommendations]
        ok_value = parsed.get("ok", False)
        if isinstance(ok_value, str):
            ok_value = ok_value.strip().lower() == "true"
        logger.info(
            "Ollama verify complete: ok=%s issues=%s",
            ok_value,
            len(issues),
        )
        return {
            "ok": ok_value,
            "issues": issues,
            "recommendations": recommendations,
            "raw": raw,
        }
    except Exception as exc:
        logger.exception("Ollama verification failed for %s", image_path)
        return {
            "ok": False,
            "issues": [f"Ollama verification failed: {exc}"],
            "recommendations": [],
            "raw": raw if "raw" in locals() else "",
        }


def revise_slide_text(
    slide: dict[str, Any],
    recommendations: list[str] | str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    base_url = settings.get("ollama_base_url", "http://localhost:11434").rstrip("/")
    model = settings.get("ollama_model", "")
    if not model:
        return {"ok": False, "issues": ["Ollama model not configured."], "raw": ""}

    kind = slide.get("kind", "content")
    if isinstance(recommendations, str):
        recs = [line.strip() for line in recommendations.splitlines() if line.strip()]
    else:
        recs = [str(item).strip() for item in recommendations if str(item).strip()]

    body_lines = slide.get("body", [])
    if isinstance(body_lines, str):
        body_lines = [line for line in body_lines.splitlines()]

    prompt_lines = [
        "You are editing slide text based on layout recommendations.",
        "Make minimal edits to fix the issues while preserving meaning and tone.",
        "Return JSON only, with no extra commentary.",
    ]
    if kind == "title":
        prompt_lines.append('Return: {"title": "...", "subtitle": "..."}')
    else:
        prompt_lines.append('Return: {"title": "...", "body": ["..."]}')

    prompt_lines.append(f"Label: {slide.get('label', '')}")
    prompt_lines.append(f"Title: {slide.get('title', '')}")
    prompt_lines.append(f"Subtitle: {slide.get('subtitle', '')}")
    if body_lines:
        prompt_lines.append("Body lines:")
        prompt_lines.extend(f"- {line}" for line in body_lines)
    if recs:
        prompt_lines.append("Recommendations:")
        prompt_lines.extend(f"- {rec}" for rec in recs)

    payload = {
        "model": model,
        "prompt": "\n".join(prompt_lines),
        "stream": False,
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
        return {"ok": True, "slide": parsed, "raw": raw}
    except Exception as exc:
        return {"ok": False, "issues": [f"Ollama rewrite failed: {exc}"], "raw": ""}
