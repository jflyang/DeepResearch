"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routes_export import router as export_router
from api.routes_research import router as research_router
from api.routes_sources import router as sources_router
from app.api.routes_settings import router as settings_router
from core.errors import ResearchError
from core.logging import setup_logging
from db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    yield


app = FastAPI(
    title="Research Collector",
    version="0.1.0",
    description="慢速深度研究资料收集器 API",
    lifespan=lifespan,
)


# === 统一错误处理 ===


@app.exception_handler(ResearchError)
async def research_error_handler(request: Request, exc: ResearchError):
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": exc.step or "research_error",
                "message": exc.message,
                "details": {"step": exc.step, "info": exc.details},
            }
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": str(exc),
                "details": {},
            }
        },
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred",
                "details": {"type": type(exc).__name__},
            }
        },
    )


# === 路由注册 ===

app.include_router(research_router, prefix="/research", tags=["research"])
app.include_router(sources_router, prefix="/sources", tags=["sources"])
app.include_router(export_router, prefix="/research", tags=["export"])
app.include_router(settings_router)


# === Health ===


@app.get("/settings/health")
async def health():
    from core.config import get_settings

    settings = get_settings()
    return {
        "status": "ok",
        "providers": {
            "tavily": {"enabled": settings.enable_tavily, "available": settings.tavily_available},
            "brave": {"enabled": settings.enable_brave, "available": settings.brave_available},
            "google_books": {
                "enabled": settings.enable_google_books,
                "available": settings.google_books_available,
            },
        },
        "obsidian_configured": settings.obsidian_configured,
        "llm": {
            "ollama_url": settings.ollama_base_url,
            "model": settings.ollama_model,
        },
    }
