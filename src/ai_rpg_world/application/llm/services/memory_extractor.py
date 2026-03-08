"""記憶抽出のデフォルト実装（ルールベース）

保存方針: 量より質。以下のいずれかを満たす場合のみエピソードを保存する。
- causes_interrupt あり（話しかけ・ダメージ・アイテム発見など）
- entity_ids または location_id の抽出に成功
- 強い成功/失敗結果（入手・撃破・達成・購入等の明確な帰結）
- 明確な観測文脈あり（「（特になし）」以外で 5 文字以上）
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
        has_interrupt = any(
            o.output.causes_interrupt for o in overflow_observations
        )
        has_entity_or_location = bool(entity_ids) or location_id is not None
        has_strong_result = self._is_strong_result(result_summary)
        has_clear_context = (
            context_summary != "（特になし）"
            and len(context_summary.strip()) >= 5
        )

        if not (
            has_interrupt
            or has_entity_or_location
            or has_strong_result
            or has_clear_context
        ):
            return []

        importance = "high" if has_interrupt else "medium"
        if has_strong_result and not has_interrupt:
            importance = "medium"
        surprise = has_interrupt

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

    def _is_strong_result(self, result_summary: str) -> bool:
        """結果要約が強い成功/失敗（明確な帰結）を含むか判定する。"""
        if not result_summary or len(result_summary.strip()) < 5:
            return False
        normalized = result_summary.strip()
        return any(kw in normalized for kw in _STRONG_RESULT_KEYWORDS)

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
