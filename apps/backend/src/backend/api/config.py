from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.config import Settings, get_settings

router = APIRouter(prefix="/config", tags=["config"])


@router.get("")
def read_config(settings: Settings = Depends(get_settings)):
    """Public subset of backend settings — safe to expose to the frontend.
    Never returns secrets or filesystem paths."""
    return {
        "orchestrator_model_default": settings.orchestrator_model,
        "max_agent_iterations": settings.max_agent_iterations,
    }
