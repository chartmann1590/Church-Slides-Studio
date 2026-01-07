# Repository Guidelines

## Project Structure & Module Organization
- `app/main.py` is the FastAPI entrypoint and API routing.
- `app/services/` contains slide rendering, bulletin parsing, settings, and optional Ollama verification.
- `app/utils/` holds file and background helpers.
- `app/templates/` contains Jinja HTML templates; `app/static/` holds JS/CSS assets.
- `data/` is runtime state: `settings.json`, uploaded `backgrounds/`, and generated `jobs/<job_id>/`.
- `backgrounds/` stores local sample image assets (gitignored) and is separate from runtime uploads.

## Build, Test, and Development Commands
- `pip install -r requirements.txt` installs Python dependencies.
- `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` runs the dev server.
- `run.bat` (Windows) activates `.venv` and runs the same uvicorn command.

## Coding Style & Naming Conventions
- Use 4-space indentation; keep functions small and type-hinted where it adds clarity.
- Organize new functionality by responsibility (`app/services/` vs `app/utils/`).
- Prefer `snake_case` for functions/variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants.
- Keep JSON keys in `data/settings.json` as lower_snake_case.

## Testing Guidelines
- No automated tests are included in this repo today.
- If you add tests, use `pytest` and place them in `tests/` with names like `test_parser.py`.
- Note any manual validation steps for slide generation or downloads in your PR.

## Commit & Pull Request Guidelines
- This checkout has no Git history, so use short, imperative summaries (e.g., "Add background upload validation").
- PRs should describe behavior changes, list manual test steps, and include screenshots for UI changes in `app/templates/` or `app/static/`.

## Configuration & Data
- Copy `.env.example` to `.env` for overrides like `OLLAMA_BASE_URL`, font paths, and `SLIDE_WIDTH`/`SLIDE_HEIGHT`.
- Slide size can be set in the UI (saved to `data/settings.json`), with `.env` taking precedence.
- Treat `data/` (including `data/settings.json`, `data/jobs`, and `data/backgrounds`) and `.env` as runtime output; do not commit them.
