"""Admin mailing package — aggregated router from panel/moderation/content/button/confirm."""

from aiogram import Router

from app.bot.handlers.admin_mailing.button import router as _button_router
from app.bot.handlers.admin_mailing.confirm import router as _confirm_router
from app.bot.handlers.admin_mailing.content import router as _content_router
from app.bot.handlers.admin_mailing.moderation import router as _moderation_router
from app.bot.handlers.admin_mailing.panel import router as _panel_router

admin_mailing_router = Router()
admin_mailing_router.include_router(_panel_router)
admin_mailing_router.include_router(_moderation_router)
admin_mailing_router.include_router(_content_router)
admin_mailing_router.include_router(_button_router)
admin_mailing_router.include_router(_confirm_router)

__all__ = ["admin_mailing_router"]
