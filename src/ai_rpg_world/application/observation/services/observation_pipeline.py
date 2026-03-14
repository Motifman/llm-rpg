"""Resolver と Formatter を用いて、イベントから各プレイヤー向け観測出力を生成するパイプライン"""

from typing import Any, List, Optional, Tuple

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationFormatter,
    IObservationRecipientResolver,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class ObservationPipeline:
    """
    Resolver → Formatter の流れで、各プレイヤーに対する観測出力を生成する。
    出力生成のみ担当し、buffer への append や副作用は行わない。
    """

    def __init__(
        self,
        resolver: IObservationRecipientResolver,
        formatter: IObservationFormatter,
        player_status_repository: Optional[Any] = None,
    ) -> None:
        self._resolver = resolver
        self._formatter = formatter
        self._player_status_repository = player_status_repository

    def run(self, event: Any) -> List[Tuple[PlayerId, ObservationOutput]]:
        """
        イベントから配信先を解決し、各プレイヤー向けの観測出力を生成する。
        返り値は (player_id, output) のリスト。formatter が None を返した場合は含めない。
        """
        recipients = self._resolver.resolve(event)
        result: List[Tuple[PlayerId, ObservationOutput]] = []
        for player_id in recipients:
            attention_level = self._get_attention_level(player_id)
            output = self._formatter.format(
                event, player_id, attention_level=attention_level
            )
            if output is not None:
                result.append((player_id, output))
        return result

    def _get_attention_level(self, player_id: PlayerId) -> AttentionLevel:
        """プレイヤーの注意レベルを取得。リポジトリ未設定時は FULL。"""
        if self._player_status_repository is None:
            return AttentionLevel.FULL
        status = self._player_status_repository.find_by_id(player_id)
        if status is None:
            return AttentionLevel.FULL
        return status.attention_level
