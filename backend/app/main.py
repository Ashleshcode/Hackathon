"""Single Veritas AI API process.

Startup creates SQLite tables, then creates the shared detector once.
Those steps stay separate. Campaign routes are registered here. Do not start
a second FastAPI application for those routes.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import analysis, campaigns, media, youtube


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.database.connection import initialize_database

    initialize_database()
    from app.models.deepfake_detector import get_shared_detector

    _app.state.detector = get_shared_detector()
    yield


app = FastAPI(title="Veritas AI", version="0.3.0", lifespan=lifespan)
app.include_router(campaigns.router)
app.include_router(analysis.router)
app.include_router(media.router)
app.include_router(youtube.router)


def _detector_status() -> dict:
    detector = getattr(app.state, "detector", None)
    if detector is None:
        return {"initialized": False, "device": None, "model_name": None}
    return {
        "initialized": True,
        "device": getattr(detector, "device", None),
        "model_name": getattr(detector, "model_name", None),
    }


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "veritas-ai-api",
        "version": "0.3.0",
        "detector": _detector_status(),
    }
