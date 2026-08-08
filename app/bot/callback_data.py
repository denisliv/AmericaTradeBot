from aiogram.filters.callback_data import CallbackData

# Кнопка "Назад" на шагах подбора: step_back:<экран, на который возвращаемся>
STEP_BACK_PREFIX = "step_back:"


class SubscribeCB(CallbackData, prefix="sub_new"):
    source: str


class ViewSubscriptionCB(CallbackData, prefix="sub_view"):
    source: str
    subscription_id: int


class DeleteSubscriptionCB(CallbackData, prefix="sub_del"):
    source: str
    subscription_id: int
