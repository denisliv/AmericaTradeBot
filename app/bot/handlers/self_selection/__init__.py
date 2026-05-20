"""Self-selection handlers package — aggregated router from flow/results/lead."""

from aiogram import Router

from app.bot.handlers.self_selection.flow import router as _flow_router
from app.bot.handlers.self_selection.lead import router as _lead_router
from app.bot.handlers.self_selection.results import router as _results_router

self_selection_router = Router()
self_selection_router.include_router(_flow_router)
self_selection_router.include_router(_results_router)
self_selection_router.include_router(_lead_router)

__all__ = ["self_selection_router"]
