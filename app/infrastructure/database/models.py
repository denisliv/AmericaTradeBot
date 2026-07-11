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


class NurtureRow(NamedTuple):
    user_id: int
    name: str | None
    started_at: datetime.datetime
    shift_days: int
    last_step: int
