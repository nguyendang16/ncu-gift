from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import i18n
from .db import SessionLocal
from .ai.client import AiError
from .ai.features import Blocked
from .routers import ai as ai_router, analytics, data, intelligence, outputs
from .seed import init_db, seed_if_empty
from .services.frame import InsufficientData


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as s:
        seed_if_empty(s)
    yield


class LanguageMiddleware:
    """Pure ASGI middleware: sets the request language (Accept-Language) for the whole request, including the
    worker threads FastAPI runs sync endpoints in, so service code can call t() without passing a language around."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        raw = dict(scope["headers"]).get(b"accept-language", b"").decode("latin-1")
        token = i18n.set_lang(i18n.parse_accept_language(raw))
        try:
            await self.app(scope, receive, send)
        finally:
            i18n.reset_lang(token)


app = FastAPI(title="NCU GIFT API", version="0.1.0", lifespan=lifespan,
              description="MVP running on SYNTHETIC mock data. Nothing here is real donor information.")
app.add_middleware(LanguageMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(InsufficientData)
async def insufficient(_req: Request, exc: InsufficientData):
    """Missing information is reported, never papered over (staff requirement)."""
    return JSONResponse(status_code=409, content={"detail": str(exc), "code": "insufficient_data"})


@app.exception_handler(AiError)
async def ai_error(_req: Request, exc: AiError):
    return JSONResponse(status_code=502, content={"detail": exc.message, "code": "ai_error", "ai_code": exc.code})


@app.exception_handler(Blocked)
async def ai_blocked(_req: Request, exc: Blocked):
    return JSONResponse(status_code=403, content={"detail": exc.message, "code": "ai_blocked", "ai_code": exc.code})


@app.get("/api/health")
def health():
    return {"status": "ok", "data": "synthetic mock"}


for r in (data.router, analytics.router, intelligence.router, outputs.router, ai_router.router):
    app.include_router(r, prefix="/api")
