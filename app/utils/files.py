from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

from fastapi import UploadFile

try:
    import docx  # type: ignore
except Exception:  # pragma: no cover - optional import
    docx = None


def ensure_data_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def sanitize_filename(filename: str) -> str:
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_. ")
    cleaned = "".join(ch for ch in filename if ch in keep).strip()
    return cleaned or "file"


def list_backgrounds(background_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted(background_dir.glob("*")):
        if not path.is_file():
            continue
        bg_type = "content"
        if path.name.lower().startswith("title_"):
            bg_type = "title"
        results.append(
            {
                "filename": path.name,
                "type": bg_type,
                "url": f"/api/backgrounds/{path.name}",
            }
        )
    return results


def save_background(background_dir: Path, bg_type: str, upload: UploadFile) -> str:
    filename = sanitize_filename(upload.filename or "background.jpg")
    prefix = "title_" if bg_type == "title" else "content_"
    target = background_dir / f"{prefix}{filename}"
    data = upload.file.read()
    target.write_bytes(data)
    return target.name


def load_bulletin_file(upload: UploadFile) -> str:
    filename = (upload.filename or "").lower()
    data = upload.file.read()
    if filename.endswith(".docx") and docx is not None:
        with io.BytesIO(data) as file_stream:
            document = docx.Document(file_stream)
        return "\n".join(p.text for p in document.paragraphs if p.text is not None)
    return data.decode("utf-8", errors="ignore")


def zip_job_slides(job_dir: Path) -> Path:
    zip_path = job_dir / "slides.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for image_path in sorted(job_dir.glob("*.jpg")):
            archive.write(image_path, image_path.name)
    return zip_path
