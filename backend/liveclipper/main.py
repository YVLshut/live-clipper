"""Application FastAPI : API REST + WebSocket + fichiers du front."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, db, paths
from .errors import UserError, humanize
from .events import bus, dumps
from .logging_setup import setup_logging

log = logging.getLogger("liveclipper")


def create_app(start_workers: bool = True) -> FastAPI:
    setup_logging()
    paths.setup_dll_dirs()
    from .api import routes_clips, routes_settings
    from .services import job_queue

    extra_routers = []
    try:
        from .api import routes_accounts, routes_publications, routes_setup
        extra_routers = [routes_accounts.router, routes_accounts.oauth_router,
                         routes_publications.router, routes_setup.router]
    except ImportError:  # modules ajoutés dans les phases suivantes
        pass

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bus.attach(asyncio.get_running_loop())
        db.engine()
        if start_workers:
            job_queue.start()
            try:
                from .services import start_publishing
                start_publishing()
            except ImportError:
                pass
        log.info("Live Clipper %s démarré (données : %s)", __version__, paths.home())
        yield
        if start_workers:
            job_queue.stop()
            try:
                from .services import stop_publishing
                stop_publishing()
            except ImportError:
                pass

    app = FastAPI(title="Live Clipper", version=__version__, lifespan=lifespan)

    @app.exception_handler(UserError)
    async def _user_error(_req: Request, exc: UserError):
        return JSONResponse({"detail": exc.message, "code": exc.code}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_req: Request, exc: RequestValidationError):
        errs = exc.errors()
        field = ".".join(str(x) for x in errs[0]["loc"][1:]) if errs else ""
        return JSONResponse({"detail": f"Valeur invalide pour « {field} »."}, status_code=422)

    @app.exception_handler(Exception)
    async def _any_error(_req: Request, exc: Exception):
        log.exception("Erreur API")
        return JSONResponse({"detail": humanize(exc)}, status_code=500)

    @app.get("/api/health")
    def health():
        return {"app": "LiveClipper", "version": __version__}

    app.include_router(routes_clips.router)
    app.include_router(routes_settings.router)
    for r in extra_routers:
        app.include_router(r)

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        q = bus.subscribe()
        try:
            await websocket.send_text(dumps({"type": "hello", "data": {"version": __version__}}))
            while True:
                msg = await q.get()
                await websocket.send_text(dumps(msg))
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            bus.unsubscribe(q)

    dist = paths.frontend_dist()
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith(("api/", "oauth/", "ws")):
                return JSONResponse({"detail": "Introuvable."}, status_code=404)
            f = (dist / full_path).resolve()
            if full_path and f.is_file() and f.is_relative_to(dist.resolve()):
                return FileResponse(f)
            return FileResponse(dist / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def no_front():
            return JSONResponse({"detail": "Interface non construite : lance `npm run build` dans frontend/."})

    return app
