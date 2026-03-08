"""記憶抽出のデフォルト実装（ルールベース）"""

import uuid
from datetime import datetime
from typing import List

from ai_rpg_world.application.llm.contracts.dtos import EpisodeMemoryEntry
from ai_rpg_world.application.llm.contracts.interfaces import IMemoryExtractor
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_ENTITY_KEYS = (
    "actor",
    "speaker",
    "buyer",
    "seller",
    "member",
    "npc_name",
    "item_name",
    "skill_name",
    "monster_name",
    "player_name",
    "location_name",
    "spot_name",
    "area_name",
)
_LOCATION_KEYS = ("location_name", "spot_name", "area_name")


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
        entity_ids, location_id = self._extract_entity_context(overflow_observations)
        importance = (
            "high"
            if any(observation.output.causes_interrupt for observation in overflow_observations)
            else "medium"
        )
        surprise = any(
            observation.output.causes_interrupt for observation in overflow_observations
        )

        entry = EpisodeMemoryEntry(
            id=str(uuid.uuid4()),
            context_summary=context_summary,
            action_taken=action_summary,
            outcome_summary=result_summary,
            entity_ids=entity_ids,
            location_id=location_id,
            timestamp=datetime.now(),
            importance=importance,
            surprise=surprise,
            recall_count=0,
        )
        return [entry]

    def _extract_entity_context(
        self,
        overflow_observations: List[ObservationEntry],
    ) -> tuple[tuple[str, ...], str | None]:
        entity_ids: list[str] = []
        location_id: str | None = None

        def add_entity(value: object) -> None:
            if not isinstance(value, str):
                return
            normalized = value.strip()
            if normalized and normalized not in entity_ids:
                entity_ids.append(normalized)

        for observation in overflow_observations:
            structured = observation.output.structured
            for key in _ENTITY_KEYS:
                add_entity(structured.get(key))
            if location_id is None:
                for key in _LOCATION_KEYS:
                    value = structured.get(key)
                    if isinstance(value, str) and value.strip():
                        location_id = value.strip()
                        break
            items = structured.get("items")
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        add_entity(item.get("item_name"))

        if location_id is not None and location_id not in entity_ids:
            entity_ids.append(location_id)
        return tuple(entity_ids), location_id
