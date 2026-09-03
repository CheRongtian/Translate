from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles


FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def mount_frontend(app: FastAPI) -> None:
    assets = FRONTEND_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        index_file = FRONTEND_DIST / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        return HTMLResponse(
            "<h2>前端尚未构建</h2><p>请在 frontend 目录执行 npm install 和 npm run build，然后重新启动。</p>",
            status_code=503,
        )

    @app.get("/{path:path}", include_in_schema=False)
    def spa_fallback(path: str):
        requested = FRONTEND_DIST / path
        if requested.is_file():
            return FileResponse(requested)
        index_file = FRONTEND_DIST / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        return HTMLResponse("前端尚未构建。", status_code=503)
