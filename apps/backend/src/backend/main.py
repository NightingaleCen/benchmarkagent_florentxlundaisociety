from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import __version__
from backend.api import artifact, chat, export, runs, sessions


def create_app() -> FastAPI:
    app = FastAPI(
        title="BenchmarkAgent Backend",
        version=__version__,
        description="Agent-assisted construction of LLM benchmark artifacts.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(sessions.router)
    app.include_router(artifact.router)
    app.include_router(chat.router)
    app.include_router(runs.router)
    app.include_router(export.router)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
