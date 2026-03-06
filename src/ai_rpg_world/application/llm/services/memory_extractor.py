"""記憶抽出のデフォルト実装（ルールベース）"""

import uuid
from datetime import datetime
from typing import List

from ai_rpg_world.application.llm.contracts.dtos import EpisodeMemoryEntry
from ai_rpg_world.application.llm.contracts.interfaces import IMemoryExtractor
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class RuleBasedMemoryExtractor(IMemoryExtractor):
    """
    観測と行動結果から 1 エピソードを生成するルールベース実装。
    LLM を使わず、溢れた観測のプローズとこのターンの行動・結果で要約を組み立てる。
    """

    def extract(
        self,
        player_id: PlayerId,
        overflow_observations: List[ObservationEntry],
        action_summary: str,
        result_summary: str,
    ) -> List[EpisodeMemoryEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(overflow_observations, list):
            raise TypeError("overflow_observations must be list")
        for o in overflow_observations:
            if not isinstance(o, ObservationEntry):
                raise TypeError(
                    "overflow_observations must contain only ObservationEntry"
                )
        if not isinstance(action_summary, str):
            raise TypeError("action_summary must be str")
        if not isinstance(result_summary, str):
            raise TypeError("result_summary must be str")

        context_parts = [o.output.prose for o in overflow_observations]
        context_summary = " ".join(context_parts).strip() or "（特になし）"

        entry = EpisodeMemoryEntry(
            id=str(uuid.uuid4()),
            context_summary=context_summary,
            action_taken=action_summary,
            outcome_summary=result_summary,
            entity_ids=(),
            location_id=None,
            timestamp=datetime.now(),
            importance="medium",
            surprise=False,
            recall_count=0,
        )
        return [entry]
