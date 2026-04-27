"""Dataclasses and Pydantic schemas for the AI manager agent."""

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Purpose = Literal["personal", "resale"]


@dataclass
class UserContext:
    """Aggregated user profile loaded from DB (long-term memory)."""

    user_id: int
    username: str | None
    name: str | None
    active_car_count: int
    recent_self_selection_requests: list[dict[str, Any]] = field(default_factory=list)
    self_subscriptions: list[dict[str, Any]] = field(default_factory=list)
    recent_chat_messages: list[dict[str, Any]] = field(default_factory=list)
    latest_self_request: dict[str, Any] | None = None
    latest_assisted_request: dict[str, Any] | None = None


_RESETTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "brand",
        "model",
        "year_from",
        "year_to",
        "odometer_from_km",
        "odometer_to_km",
        "budget_from_usd",
        "budget_to_usd",
        "body_style",
        "fuel_type",
        "drive_preference",
        "benefit_eligible",
        "purpose",
        "buy_now_only",
    }
)


class CollectedInfoDelta(BaseModel):
    """Partial update to the working-memory CollectedInfo extracted on this turn."""

    brand: Optional[str] = None
    model: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    odometer_from_km: Optional[int] = None
    odometer_to_km: Optional[int] = None
    budget_from_usd: Optional[int] = None
    budget_to_usd: Optional[int] = None
    body_style: Optional[str] = None
    fuel_type: Optional[str] = Field(
        default=None,
        description=(
            "Powertrain / fuel preference mentioned by the user: 'electric', "
            "'hybrid', 'gasoline', 'diesel'. Maps to the CSV 'Fuel Type' column."
        ),
    )
    benefit_eligible: Optional[bool] = None
    purpose: Optional[Purpose] = None
    buy_now_only: Optional[bool] = None
    drive_preference: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_consent: Optional[bool] = None
    reset_fields: list[str] = Field(
        default_factory=list,
        description=(
            "Fields the user explicitly wants to clear in this turn. "
            "Use when the user asks for alternatives / any car / broader search "
            "and the previously saved constraint should be dropped "
            "(e.g. ['brand','model'] after 'предложи любой' / 'подбери альтернативы')."
        ),
    )


class CollectedInfo(BaseModel):
    """Working-memory snapshot of what the agent knows about the user's request."""

    brand: Optional[str] = None
    model: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    odometer_from_km: Optional[int] = None
    odometer_to_km: Optional[int] = None
    budget_from_usd: Optional[int] = None
    budget_to_usd: Optional[int] = None
    body_style: Optional[str] = None
    fuel_type: Optional[str] = None
    benefit_eligible: Optional[bool] = None
    purpose: Optional[Purpose] = None
    buy_now_only: Optional[bool] = None
    drive_preference: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_consent: bool = False

    def merge(self, delta: "CollectedInfoDelta") -> "CollectedInfo":
        data = self.model_dump()
        # Step 1: honour explicit reset requests ("любой", "альтернативы" ...)
        for name in delta.reset_fields or ():
            if name in _RESETTABLE_FIELDS and name in data:
                data[name] = None
        # Step 2: apply additive updates (only non-None fields overwrite)
        additive = delta.model_dump(exclude_none=True)
        additive.pop("reset_fields", None)
        for key, value in additive.items():
            data[key] = value
        return CollectedInfo.model_validate(data)

    def search_ready(self) -> bool:
        """Whether we have *enough* signal to run a meaningful CSV search.

        We accept any of the following patterns:
        - explicit brand+model with at least one of year-range/budget;
        - brand+year_range (e.g. 'любая Tesla 2022–2024');
        - a powertrain/body style preference together with a year-range or a budget
          (e.g. 'любой электромобиль до $25k' / 'SUV 2023–2025');
        - just a budget is NOT enough — it would return the whole CSV.
        """
        has_budget = (
            self.budget_from_usd is not None or self.budget_to_usd is not None
        )
        has_year = self.year_from is not None or self.year_to is not None

        if self.brand and self.model and (has_year or has_budget):
            return True
        if self.brand and has_year:
            return True
        if (self.fuel_type or self.body_style) and (has_year or has_budget):
            return True
        return False

    def missing_for_search(self) -> list[str]:
        """What the user still needs to provide for a meaningful search."""
        has_year = self.year_from is not None or self.year_to is not None
        has_budget = (
            self.budget_from_usd is not None or self.budget_to_usd is not None
        )
        has_category = bool(self.brand or self.fuel_type or self.body_style)

        miss: list[str] = []
        if not has_category:
            # Any of these three would unblock a search.
            miss.append("brand_or_category")
        if not has_year and not has_budget:
            miss.append("year_or_budget")
        return miss


class LeadDecision(BaseModel):
    """LLM judge output to decide whether to submit a lead to CRM."""

    ready: bool
    confidence: float = Field(ge=0.0, le=1.0)
    required_missing: list[str] = Field(default_factory=list)
    reason: str = ""
    manager_summary: str = Field(
        default="",
        description=(
            "2-3 short Russian sentences for the human manager: what the client "
            "wants, what criteria/services were discussed, and the next step."
        ),
    )


class CarCard(BaseModel):
    """Single car result rendered to the user."""

    lot_number: str
    year: int | None = None
    make: str | None = None
    model: str | None = None
    body_style: str | None = None
    color: str | None = None
    odometer: str | None = None
    engine: str | None = None
    drive: str | None = None
    transmission: str | None = None
    sale_date: str | None = None
    buy_now_price: float | None = None
    preview_image_url: str | None = None
    lot_url: str
    caption: str


@dataclass
class AIReply:
    """Structured response returned from the service to the bot handler."""

    text: str
    cars: list[CarCard] = field(default_factory=list)
    lead_sent: bool = False


class DecompositionHint(BaseModel):
    """Optional pre-step: split a complex user message into subtasks for ReAct."""

    needs_decomposition: bool = False
    subtasks: list[str] = Field(
        default_factory=list,
        description="1-3 short subtasks in Russian, empty if not needed",
    )
