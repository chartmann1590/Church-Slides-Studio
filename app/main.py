from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.services.ollama import revise_slide_text, verify_slide_image
from app.services.parser import build_slide_specs, parse_bulletin_text
from app.services.render import render_single_slide, render_slide_images
from app.services.settings import get_settings, update_settings
from app.utils.files import (
    ensure_data_dirs,
    list_backgrounds,
    load_bulletin_file,
    save_background,
    sanitize_filename,
    zip_job_slides,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BACKGROUND_DIR = DATA_DIR / "backgrounds"
JOBS_DIR = DATA_DIR / "jobs"
logger = logging.getLogger(__name__)

ensure_data_dirs(DATA_DIR, BACKGROUND_DIR, JOBS_DIR)

app = FastAPI(title="Church Slides Studio")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")


def _load_job(job_id: str) -> tuple[Path, Path, dict[str, Any]]:
    job_dir = JOBS_DIR / job_id
    meta_path = job_dir / "job.json"
    if not job_dir.exists() or not meta_path.exists():
        raise HTTPException(status_code=404, detail="Job not found.")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Job metadata invalid: {exc}") from exc
    return job_dir, meta_path, meta


def _find_slide_meta(meta: dict[str, Any], filename: str) -> tuple[dict[str, Any], int]:
    slides = meta.get("slides", [])
    if isinstance(slides, list):
        for index, slide in enumerate(slides):
            if isinstance(slide, dict) and slide.get("filename") == filename:
                return slide, index
    raise HTTPException(status_code=404, detail="Slide metadata not found.")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    settings = get_settings(DATA_DIR)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "settings": settings,
        },
    )


@app.get("/api/settings", response_class=JSONResponse)
def api_get_settings() -> JSONResponse:
    return JSONResponse(get_settings(DATA_DIR))


@app.post("/api/settings", response_class=JSONResponse)
async def api_update_settings(request: Request) -> JSONResponse:
    payload = await request.json()
    settings = update_settings(DATA_DIR, payload)
    return JSONResponse(settings)


@app.get("/api/backgrounds", response_class=JSONResponse)
def api_list_backgrounds() -> JSONResponse:
    return JSONResponse(list_backgrounds(BACKGROUND_DIR))


@app.post("/api/backgrounds", response_class=JSONResponse)
async def api_upload_background(
    bg_type: str = Form(...),
    file: UploadFile = File(...),
) -> JSONResponse:
    if bg_type not in {"title", "content"}:
        raise HTTPException(status_code=400, detail="bg_type must be title or content.")
    filename = save_background(BACKGROUND_DIR, bg_type, file)
    return JSONResponse({"filename": filename})


@app.delete("/api/backgrounds/{filename}", response_class=JSONResponse)
def api_delete_background(filename: str) -> JSONResponse:
    target = BACKGROUND_DIR / sanitize_filename(filename)
    if target.exists():
        target.unlink()
    return JSONResponse({"ok": True})


@app.get("/api/backgrounds/{filename}")
def api_get_background(filename: str) -> FileResponse:
    target = BACKGROUND_DIR / sanitize_filename(filename)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Background not found.")
    return FileResponse(target)


@app.post("/api/generate", response_class=JSONResponse)
async def api_generate_slides(
    bulletin_text: str | None = Form(None),
    bulletin_file: UploadFile | None = File(None),
    title_background: str | None = Form(None),
    content_background: str | None = Form(None),
    verify_with_ollama: bool = Form(False),
) -> JSONResponse:
    if not bulletin_text and not bulletin_file:
        raise HTTPException(status_code=400, detail="Provide bulletin text or a file.")

    raw_text = bulletin_text or ""
    if bulletin_file:
        raw_text = load_bulletin_file(bulletin_file)
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Bulletin text is empty.")

    settings = get_settings(DATA_DIR)
    sections = parse_bulletin_text(raw_text)
    slide_specs = build_slide_specs(sections, settings)

    job_id = uuid.uuid4().hex[:10]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    title_background_name = sanitize_filename(title_background) if title_background else None
    content_background_name = sanitize_filename(content_background) if content_background else None
    title_bg_path = (
        BACKGROUND_DIR / title_background_name
        if title_background_name
        else None
    )
    content_bg_path = (
        BACKGROUND_DIR / content_background_name
        if content_background_name
        else None
    )

    generated = render_slide_images(
        slide_specs,
        job_dir,
        settings,
        title_bg_path=title_bg_path,
        content_bg_path=content_bg_path,
    )
    for slide in generated:
        slide["url"] = f"/api/jobs/{job_id}/slides/{slide['filename']}"

    verification: dict[str, Any] = {}

    slides_meta = []
    for slide in generated:
        slides_meta.append(
            {
                "filename": slide.get("filename"),
                "kind": slide.get("kind", ""),
                "label": slide.get("label", ""),
                "title": slide.get("title", ""),
                "subtitle": slide.get("subtitle", ""),
                "body": slide.get("body", []),
            }
        )

    meta_path = job_dir / "job.json"
    meta_path.write_text(
        json.dumps(
            {
                "id": job_id,
                "slides": slides_meta,
                "verification": verification,
                "title_background": title_background_name,
                "content_background": content_background_name,
                "render_settings": settings,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    zip_path = zip_job_slides(job_dir)

    return JSONResponse(
        {
            "job_id": job_id,
            "slides": generated,
            "verification": verification,
            "zip_url": f"/api/jobs/{job_id}/download",
        }
    )


@app.post("/api/jobs/{job_id}/slides/{filename}/verify", response_class=JSONResponse)
def api_verify_slide(job_id: str, filename: str) -> JSONResponse:
    job_dir, meta_path, meta = _load_job(job_id)
    safe_name = sanitize_filename(filename)
    slide_path = job_dir / safe_name
    if not slide_path.exists():
        raise HTTPException(status_code=404, detail="Slide not found.")
    settings = get_settings(DATA_DIR)
    logger.info("Verify request: job=%s slide=%s", job_id, safe_name)
    result = verify_slide_image(
        str(slide_path),
        settings=settings,
    )
    logger.info(
        "Verify result: job=%s slide=%s ok=%s",
        job_id,
        safe_name,
        result.get("ok"),
    )
    verification = meta.get("verification", {})
    verification[safe_name] = result
    meta["verification"] = verification
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return JSONResponse(result)


@app.post("/api/jobs/{job_id}/slides/{filename}/recreate", response_class=JSONResponse)
async def api_recreate_slide(job_id: str, filename: str, request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    recommendations = []
    if isinstance(payload, dict):
        recommendations = payload.get("recommendations") or payload.get("issues") or []

    job_dir, meta_path, meta = _load_job(job_id)
    safe_name = sanitize_filename(filename)
    slide_meta, slide_index = _find_slide_meta(meta, safe_name)
    slide_path = job_dir / safe_name
    if not slide_path.exists():
        raise HTTPException(status_code=404, detail="Slide not found.")

    render_settings = meta.get("render_settings") or get_settings(DATA_DIR)
    title_background = meta.get("title_background")
    content_background = meta.get("content_background")
    title_bg_path = (
        BACKGROUND_DIR / sanitize_filename(title_background)
        if title_background
        else None
    )
    content_bg_path = (
        BACKGROUND_DIR / sanitize_filename(content_background)
        if content_background
        else None
    )

    rewrite = revise_slide_text(slide_meta, recommendations, settings=get_settings(DATA_DIR))
    if not rewrite.get("ok"):
        issues = rewrite.get("issues", ["Ollama rewrite failed."])
        raise HTTPException(status_code=500, detail=" ".join(issues))

    updated_slide = dict(slide_meta)
    revised_payload = rewrite.get("slide", {})
    if isinstance(revised_payload, dict):
        if "title" in revised_payload:
            updated_slide["title"] = str(revised_payload.get("title", "")).strip()
        if "subtitle" in revised_payload:
            updated_slide["subtitle"] = str(revised_payload.get("subtitle", "")).strip()
        if "body" in revised_payload:
            body_value = revised_payload.get("body", [])
            if isinstance(body_value, str):
                updated_slide["body"] = [line for line in body_value.splitlines()]
            elif isinstance(body_value, list):
                updated_slide["body"] = [str(line) for line in body_value]

    render_single_slide(
        updated_slide,
        slide_path,
        render_settings,
        title_bg_path=title_bg_path,
        content_bg_path=content_bg_path,
    )

    slides = meta.get("slides", [])
    if isinstance(slides, list) and 0 <= slide_index < len(slides):
        slides[slide_index] = updated_slide
        meta["slides"] = slides
    verification = meta.get("verification", {})
    if isinstance(verification, dict):
        verification.pop(safe_name, None)
        meta["verification"] = verification
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    zip_job_slides(job_dir)

    updated_slide["url"] = f"/api/jobs/{job_id}/slides/{safe_name}"
    return JSONResponse({"slide": updated_slide})


@app.get("/api/jobs/{job_id}/slides/{filename}")
def api_get_slide(job_id: str, filename: str) -> FileResponse:
    slide_path = JOBS_DIR / job_id / sanitize_filename(filename)
    if not slide_path.exists():
        raise HTTPException(status_code=404, detail="Slide not found.")
    return FileResponse(slide_path)


@app.get("/api/jobs/{job_id}/download")
def api_download_zip(job_id: str) -> FileResponse:
    zip_path = JOBS_DIR / job_id / "slides.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="ZIP not found.")
    return FileResponse(zip_path, filename=f"{job_id}_slides.zip")
