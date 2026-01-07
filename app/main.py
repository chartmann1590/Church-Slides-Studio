from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.services.ollama import verify_slide_image
from app.services.parser import build_slide_specs, parse_bulletin_text
from app.services.render import render_slide_images
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

ensure_data_dirs(DATA_DIR, BACKGROUND_DIR, JOBS_DIR)

app = FastAPI(title="Church Slides Studio")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")


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
    if verify_with_ollama:
        for slide in generated:
            result = verify_slide_image(
                slide["path"],
                settings=settings,
            )
            verification[slide["filename"]] = result

    meta_path = job_dir / "job.json"
    meta_path.write_text(
        json.dumps(
            {
                "id": job_id,
                "slides": [slide["filename"] for slide in generated],
                "verification": verification,
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
