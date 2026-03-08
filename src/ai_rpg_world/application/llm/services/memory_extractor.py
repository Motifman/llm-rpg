"""記憶抽出のデフォルト実装（ルールベース）

保存方針: 量より質。以下のいずれかを満たす場合のみエピソードを保存する。
- breaks_movement あり（被ダメージ・会話開始・アイテム発見など即時反応が必要な観測）
- entity_ids または location_id の抽出に成功（stable id 対応後は world_object_ids 等も対象）
- 強い成功/失敗結果（入手・撃破・達成・購入等の明確な帰結）

has_clear_context 単独では保存しない。prose のみの文脈は importance 補正に留める。
"""

import uuid
from datetime import datetime
from typing import List

from ai_rpg_world.application.llm.contracts.dtos import EpisodeMemoryEntry
from ai_rpg_world.application.llm.contracts.interfaces import IMemoryExtractor
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

# 強い成功/失敗を示すキーワード（結果要約に含まれる場合に保存対象とする）
_STRONG_RESULT_KEYWORDS = (
    "入手", "撃破", "達成", "失敗", "成功", "倒した", "死亡", "レベル",
    "購入", "完了", "選択", "発見", "獲得", "経験値", "ゴールド", "到着",
)

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
        world_object_ids, spot_id_value = self._extract_stable_ids(overflow_observations)
        has_breaks_movement = any(
            o.output.breaks_movement for o in overflow_observations
        )
        has_entity_or_location = bool(entity_ids) or location_id is not None
        has_strong_result = self._is_strong_result(result_summary)

        if not (
            has_breaks_movement
            or has_entity_or_location
            or has_strong_result
        ):
            return []

        importance = "high" if has_breaks_movement else "medium"
        if has_strong_result and not has_breaks_movement:
            importance = "medium"
        if has_strong_result and self._is_combat_or_death_result(result_summary):
            importance = "high"
        surprise = has_breaks_movement

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
            world_object_ids=world_object_ids,
            spot_id_value=spot_id_value,
        )
        return [entry]

    def _is_strong_result(self, result_summary: str) -> bool:
        """結果要約が強い成功/失敗（明確な帰結）を含むか判定する。"""
        if not result_summary or len(result_summary.strip()) < 5:
            return False
        normalized = result_summary.strip()
        return any(kw in normalized for kw in _STRONG_RESULT_KEYWORDS)

    def _is_combat_or_death_result(self, result_summary: str) -> bool:
        """戦闘結果・死亡・撃破など urgency が高い帰結か。"""
        combat_keywords = ("撃破", "倒した", "死亡", "戦闘不能", "ダメージ")
        return any(kw in result_summary for kw in combat_keywords)

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

    def _extract_stable_ids(
        self,
        overflow_observations: List[ObservationEntry],
    ) -> tuple[tuple[int, ...], int | None]:
        """structured から world_object_id / spot_id を抽出。なければ空・None。"""
        world_object_ids: list[int] = []
        spot_id_value: int | None = None
        for observation in overflow_observations:
            structured = observation.output.structured
            wo_id = structured.get("world_object_id")
            if wo_id is not None and isinstance(wo_id, int):
                if wo_id not in world_object_ids:
                    world_object_ids.append(wo_id)
            sp_id = structured.get("spot_id_value")
            if sp_id is not None and isinstance(sp_id, int) and spot_id_value is None:
                spot_id_value = sp_id
        return tuple(world_object_ids), spot_id_value
