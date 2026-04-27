import logging

from aiogram import Router

from app.bot.enums.roles import UserRole
from app.bot.filters.filters import UserRoleFilter
from app.bot.handlers.admin_mailing import admin_mailing_router

logger = logging.getLogger(__name__)

admin_router = Router()

admin_router.message.filter(UserRoleFilter(UserRole.ADMIN))
admin_router.include_router(admin_mailing_router)
