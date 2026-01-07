from __future__ import annotations

import re
from typing import Any

KNOWN_LABELS = [
    "Order of Worship",
    "Prelude",
    "Words of Welcome",
    "Call to Worship",
    "Opening Prayer",
    "Anthem",
    "Song",
    "Hymn",
    "Prayer Song",
    "Time With Young Disciples",
    "Scripture",
    "Message",
    "Reaffirmation of our Baptismal Vows",
    "Affirming Our Shared Faith",
    "Thanksgiving Over the Water and Renewing our Baptism",
    "Invitation to Generosity: Offering Our Gifts, Tithes, and Our Thanks",
    "Offertory",
    "Singing our Praise",
    "Prayer of Dedication",
    "Sharing of Joys and Concerns",
    "Pastoral Prayer",
    "The Lords Prayer (in your heart language)",
    "Sending Hymn",
    "Postlude",
    "Cover Image",
]


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _looks_like_label(text: str) -> bool:
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if not words:
        return False
    lower_ok = {"of", "and", "the", "to", "in", "our", "with", "for", "a", "an"}
    for word in words:
        if word.lower() in lower_ok:
            continue
        if not (word.isupper() or word[:1].isupper()):
            return False
    return True


def _detect_header(line: str) -> tuple[str, str, bool]:
    cleaned = line.strip().lstrip("*").strip()
    if not cleaned:
        return "", "", False
    normalized = _normalize(cleaned)
    for label in sorted(KNOWN_LABELS, key=len, reverse=True):
        if normalized.startswith(_normalize(label)):
            remainder = cleaned[len(label) :].strip()
            return label, remainder, True
    if line.strip().startswith("*"):
        return cleaned, "", True
    parts = re.split(r"\s{2,}", cleaned)
    if len(parts) >= 2 and len(parts[0]) <= 45:
        return parts[0].strip(), " ".join(parts[1:]).strip(), True
    if ":" in cleaned:
        label, title = cleaned.split(":", 1)
        if len(label.strip()) <= 45 and _looks_like_label(label):
            return label.strip(), title.strip(), True
    return "", cleaned, False


def parse_bulletin_text(text: str) -> list[dict[str, Any]]:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    preamble: list[str] = []
    saw_header = False

    for line in lines:
        if not line.strip():
            if current:
                current["body"].append("")
            elif preamble:
                preamble.append("")
            continue

        label, title, is_header = _detect_header(line)
        if is_header:
            saw_header = True
            if current:
                sections.append(current)
            if not current and preamble:
                preamble = []
            current = {"label": label, "title": title, "body": []}
            continue

        if current is None:
            preamble.append(line.strip())
        else:
            current["body"].append(line.strip())

    if current:
        sections.append(current)
    elif preamble and not saw_header:
        sections.append(
            {
                "label": "Bulletin",
                "title": preamble[0],
                "body": preamble[1:],
            }
        )

    return sections


def build_slide_specs(sections: list[dict[str, Any]], settings: dict[str, Any]) -> list[dict[str, Any]]:
    slide_specs: list[dict[str, Any]] = []
    skip_labels = {"orderofworship"}
    for section in sections:
        label = section.get("label", "").strip() or "Section"
        title = section.get("title", "").strip()
        body = section.get("body", [])
        label_norm = _normalize(label)

        if label_norm in skip_labels:
            continue

        has_body = any(line.strip() for line in body)
        person_title = bool(re.search(r"\b(rev\.|reverend|pastor|dr\.|bishop|elder)\b", title, re.IGNORECASE))
        display_title = title or label
        subtitle = ""
        if title and person_title:
            display_title = label
            subtitle = title

        if display_title or subtitle:
            slide_specs.append(
                {
                    "kind": "title",
                    "label": label,
                    "title": display_title,
                    "subtitle": subtitle,
                    "body": [],
                }
            )

        if has_body:
            slide_specs.append(
                {
                    "kind": "content",
                    "label": label,
                    "title": title,
                    "body": body,
                }
            )
    return slide_specs
