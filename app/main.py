"""FastAPI entrypoint for Bank Account Opening Verification."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware

from app import config
from app.db import init_db
from app.logging_config import setup_logging
from app.routes.applications import router as applications_router
from app.routes.auth import router as auth_router
from app.routes.branch import router as branch_router
from app.routes.health import router as health_router
from app.routes.signatures import router as signatures_router
from app.routes.verification import router as verification_router

setup_logging()

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
FRONTEND_ASSETS = FRONTEND_DIST / "assets"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    from app.services.analysis_queue import analysis_queue
    from app.services.email_queue import email_queue
    from app.services.workflow_queue import workflow_queue

    analysis_queue.start()
    email_queue.start()
    workflow_queue.start()
    yield


app = FastAPI(
    title="Cognexa — Document and Verification System",
    description=(
        "Cognexa stores customer applications for branch review; "
        "branch users run Cognexa AI verification and decide."
    ),
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET,
    session_cookie="documentscan_session",
    same_site="lax",
    https_only=False,
)

app.include_router(health_router)
app.include_router(applications_router)
app.include_router(auth_router)
app.include_router(branch_router)
app.include_router(signatures_router)
app.include_router(verification_router)


def _spa_index() -> Path:
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return index_path
    raise HTTPException(
        status_code=503,
        detail="Frontend not built. Run: cd frontend && npm install && npm run build",
    )


def _safe_file(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if not str(candidate).startswith(str(root_resolved)):
        raise HTTPException(status_code=404, detail="Not Found")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Not Found")
    return candidate


@app.get("/assets/{file_path:path}")
def frontend_assets(file_path: str):
    """Serve Vite build assets (explicit route — reliable under uvicorn --reload)."""
    if not FRONTEND_ASSETS.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend assets missing. Run: cd frontend && npm run build",
        )
    return FileResponse(_safe_file(FRONTEND_ASSETS, file_path))


@app.get("/favicon.svg")
def favicon():
    path = FRONTEND_DIST / "favicon.svg"
    if path.exists():
        return FileResponse(path)
    raise HTTPException(status_code=404, detail="favicon missing")


@app.get("/ubl-logo.png")
def ubl_logo():
    path = FRONTEND_DIST / "ubl-logo.png"
    if path.exists():
        return FileResponse(path, media_type="image/png")
    raise HTTPException(status_code=404, detail="logo missing")


@app.get("/app-bg.jpg")
def app_background():
    path = FRONTEND_DIST / "app-bg.jpg"
    if path.exists():
        return FileResponse(path, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="background missing")


@app.get("/bg-mesh.avif")
def background_mesh():
    path = FRONTEND_DIST / "bg-mesh.avif"
    if path.exists():
        return FileResponse(path, media_type="image/avif")
    raise HTTPException(status_code=404, detail="background missing")


@app.get("/")
def index():
    return FileResponse(_spa_index())


@app.get("/branch/login")
@app.get("/branch")
@app.get("/branch/queue")
@app.get("/branch/history")
@app.get("/branch/audit")
@app.get("/branch/scan")
@app.get("/branch/signatures")
@app.get("/branch/applications/{application_id}")
def spa_routes(application_id: str | None = None):
    return FileResponse(_spa_index())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
