# Church Slides Studio

Self-hosted web app that converts bulletin text or documents into JPG slides (default 1920x1080, configurable). Upload title/content backgrounds, generate slides, and optionally verify them with a remote Ollama vision model.

## Setup

1. Create a virtual environment (optional).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and adjust values if needed.

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

On Windows, you can use `run.bat` to activate `.venv` and launch the same uvicorn command.

## Configuration

- `data/settings.json` stores UI-saved settings (including slide size).
- `.env` can override:
  - `OLLAMA_BASE_URL`
  - `OLLAMA_MODEL`
  - `TITLE_FONT_PATH`
  - `BODY_FONT_PATH`
  - `LABEL_FONT_PATH`
  - `SLIDE_WIDTH`
  - `SLIDE_HEIGHT`

## Notes

- Backgrounds are stored in `data/backgrounds`.
- Generated slides and ZIP downloads are stored in `data/jobs/<job_id>`.
- Slide layout values live in `data/settings.json` (positioning uses `[x, y, width, height]` for text boxes).
- Slides render at 1920x1080 by default and auto-wrap/paginate to keep text large and readable.
- Override slide size via the Slide Settings panel, `data/settings.json`, or `.env`.
- Treat `data/` and `.env` as local runtime state; avoid committing them.
