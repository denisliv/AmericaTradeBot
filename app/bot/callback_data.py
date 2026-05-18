from aiogram.filters.callback_data import CallbackData


class SubscribeCB(CallbackData, prefix="sub_new"):
    source: str


class ViewSubscriptionCB(CallbackData, prefix="sub_view"):
    source: str
    subscription_id: int


class DeleteSubscriptionCB(CallbackData, prefix="sub_del"):
    source: str
    subscription_id: int
