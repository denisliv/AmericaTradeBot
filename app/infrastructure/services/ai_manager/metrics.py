"""Lightweight in-process metrics for AI manager rollout and observability."""

import logging
from collections import Counter
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class MetricsSnapshot:
    messages_total: int = 0
    rag_hits: int = 0
    rag_miss: int = 0
    leads_ready: int = 0
    leads_sent: int = 0
    leads_rejected_by_judge: int = 0
    cars_shown: int = 0
    classifications: int = 0
    classification_confidence_sum: float = 0.0
    plan_executions: int = 0
    action_counter: Counter = field(default_factory=Counter)
    stage_counter: Counter = field(default_factory=Counter)
    tool_counter: Counter = field(default_factory=Counter)


class AIManagerMetrics:
    """Lightweight in-process metrics."""

    def __init__(self) -> None:
        self.snapshot = MetricsSnapshot()

    def inc_messages(self) -> None:
        self.snapshot.messages_total += 1

    def inc_rag_hits(self) -> None:
        self.snapshot.rag_hits += 1

    def inc_rag_miss(self) -> None:
        self.snapshot.rag_miss += 1

    def inc_leads_ready(self) -> None:
        self.snapshot.leads_ready += 1

    def inc_leads_sent(self) -> None:
        self.snapshot.leads_sent += 1

    def inc_leads_rejected_by_judge(self) -> None:
        self.snapshot.leads_rejected_by_judge += 1

    def add_cars_shown(self, count: int) -> None:
        if count > 0:
            self.snapshot.cars_shown += count

    def record_classification(self, *, confidence: float, stage: str) -> None:
        self.snapshot.classifications += 1
        self.snapshot.classification_confidence_sum += float(confidence)
        self.snapshot.stage_counter[stage] += 1

    def record_plan(self, action: str) -> None:
        self.snapshot.plan_executions += 1
        self.snapshot.action_counter[action] += 1

    def inc_tool(self, tool_name: str) -> None:
        self.snapshot.tool_counter[tool_name] += 1

    @property
    def avg_classification_confidence(self) -> float:
        if self.snapshot.classifications == 0:
            return 0.0
        return (
            self.snapshot.classification_confidence_sum / self.snapshot.classifications
        )

    def log_snapshot(self) -> None:
        logger.info(
            "AI manager metrics: messages=%s rag_hits=%s rag_miss=%s cars_shown=%s "
            "classifications=%s avg_conf=%.3f plan_executions=%s "
            "leads_ready=%s leads_sent=%s leads_rejected=%s top_actions=%s top_stages=%s "
            "tools=%s",
            self.snapshot.messages_total,
            self.snapshot.rag_hits,
            self.snapshot.rag_miss,
            self.snapshot.cars_shown,
            self.snapshot.classifications,
            self.avg_classification_confidence,
            self.snapshot.plan_executions,
            self.snapshot.leads_ready,
            self.snapshot.leads_sent,
            self.snapshot.leads_rejected_by_judge,
            dict(self.snapshot.action_counter.most_common(5)),
            dict(self.snapshot.stage_counter.most_common(5)),
            dict(self.snapshot.tool_counter.most_common(10)),
        )
