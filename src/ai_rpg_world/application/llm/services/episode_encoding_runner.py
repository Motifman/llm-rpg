"""ターン後に EpisodeEncodingProcessor を起動する IEpisodeEncodingRunner 実装。"""

from ai_rpg_world.application.llm.contracts.interfaces import IEpisodeEncodingRunner
from ai_rpg_world.application.llm.services.episode_encoding_processor import (
    EpisodeEncodingProcessor,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class EpisodeEncodingRunner(IEpisodeEncodingRunner):
    def __init__(self, processor: EpisodeEncodingProcessor) -> None:
        if not isinstance(processor, EpisodeEncodingProcessor):
            raise TypeError("processor must be EpisodeEncodingProcessor")
        self._processor = processor

    def run_after_turn(self, player_id: PlayerId) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        self._processor.process_pending(player_id)
