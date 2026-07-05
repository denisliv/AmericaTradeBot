import datetime
from typing import NamedTuple


class UserRow(NamedTuple):
    id: int
    user_id: int
    username: str
    name: str
    created_at: datetime.datetime
    last_activity: datetime.datetime
    role: str
    is_alive: bool
    banned: bool
    active_car_count: int


class SelfSelectionRow(NamedTuple):
    id: int
    user_id: int
    created_at: datetime.datetime
    brand: str
    model: str
    year: str
    odometer: str
    auction_status: str


class AssistedSelectionRow(NamedTuple):
    id: int
    user_id: int
    created_at: datetime.datetime
    body_style: str
    budget: str
