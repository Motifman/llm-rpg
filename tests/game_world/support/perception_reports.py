from __future__ import annotations

from ai_rpg_world.game_world.domain.perception.perception_delivery_report import PerceptionDeliveryReport


class PerceptionReportsReceived:
    def __init__(self) -> None:
        self.reports: list[PerceptionDeliveryReport] = []

    def receive(self, report: PerceptionDeliveryReport) -> None:
        self.reports.append(report)
