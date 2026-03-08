"""記憶抽出のデフォルト実装（ルールベース）

保存方針: 量より質。以下のいずれかを満たす場合のみエピソードを保存する。
- breaks_movement あり（被ダメージ・会話開始・死亡級など即時反応が必要な観測）
- stable id 抽出成功（world_object_ids または spot_id_value）
- 強い成功/失敗結果（入手・撃破・達成・購入等の明確な帰結）

has_entity_or_location（名前のみ）単独では保存しない。prose のみのノイズは保存しない。
importance: high=被ダメージ・死亡・戦闘勝敗・会話開始・重大報酬、medium=stable id 付き接触・クエスト更新・取得・発見、low=補助的。
観測ごとに複数候補を抽出し、scope_keys 単位でマージ・重複除去・件数上限で絞る。
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


# 複数候補の最大件数（scope マージ・重複除去後の上限）
_MAX_EPISODE_CANDIDATES = 5

# 高優先 scope プレフィックス（quest, conversation を優先）
_HIGH_PRIORITY_SCOPE_PREFIXES = ("quest:", "conversation:")


class RuleBasedMemoryExtractor(IMemoryExtractor):
    """
    観測と行動結果から複数エピソード候補を生成するルールベース実装。
    LLM を使わず、溢れた観測のプローズとこのターンの行動・結果で要約を組み立てる。
    観測ごとに候補を抽出し、scope_keys 単位でマージ・重複除去・件数上限で絞る。
    """

    def __init__(self, max_candidates: int = _MAX_EPISODE_CANDIDATES) -> None:
        self._max_candidates = max(1, max_candidates)

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

        has_breaks_movement = any(
            o.output.breaks_movement for o in overflow_observations
        )
        has_strong_result = self._is_strong_result(result_summary)

        # 観測ごとに候補を抽出
        candidates: list[EpisodeMemoryEntry] = []
        for obs in overflow_observations:
            wo_ids, sp_val = self._extract_stable_ids([obs])
            scope_keys = self._extract_scope_keys([obs])
            ent_ids, loc_id = self._extract_entity_context([obs])
            has_stable_this = bool(wo_ids) or sp_val is not None
            has_scope_this = bool(scope_keys)
            obs_breaks = bool(obs.output.breaks_movement)

            # この観測が候補に値するか
            if not (
                obs_breaks or has_stable_this or has_scope_this or has_strong_result
            ):
                continue

            importance = self._compute_importance(
                obs_breaks, has_stable_this or has_scope_this, has_strong_result, result_summary
            )
            surprise = obs_breaks
            context = (obs.output.prose or "").strip() or "（特になし）"

            entry = EpisodeMemoryEntry(
                id=str(uuid.uuid4()),
                context_summary=context,
                action_taken=action_summary,
                outcome_summary=result_summary,
                entity_ids=ent_ids,
                location_id=loc_id,
                timestamp=datetime.now(),
                importance=importance,
                surprise=surprise,
                recall_count=0,
                world_object_ids=wo_ids,
                spot_id_value=sp_val,
                scope_keys=scope_keys,
            )
            candidates.append(entry)

        # 1件も候補がなければ、従来どおり統合1件を返す（後方互換）
        if not candidates:
            wo_ids, sp_val = self._extract_stable_ids(overflow_observations)
            if not (has_breaks_movement or wo_ids or sp_val is not None or has_strong_result):
                return []
            context_summary = " ".join(
                (o.output.prose or "").strip() for o in overflow_observations
            ).strip() or "（特になし）"
            ent_ids, loc_id = self._extract_entity_context(overflow_observations)
            scope_keys = self._extract_scope_keys(overflow_observations)
            importance = self._compute_importance(
                has_breaks_movement, bool(wo_ids) or sp_val is not None,
                has_strong_result, result_summary
            )
            return [
                EpisodeMemoryEntry(
                    id=str(uuid.uuid4()),
                    context_summary=context_summary,
                    action_taken=action_summary,
                    outcome_summary=result_summary,
                    entity_ids=ent_ids,
                    location_id=loc_id,
                    timestamp=datetime.now(),
                    importance=importance,
                    surprise=has_breaks_movement,
                    recall_count=0,
                    world_object_ids=wo_ids,
                    spot_id_value=sp_val,
                    scope_keys=scope_keys,
                )
            ]

        # scope_keys 単位でマージ: 同じ scope の候補は context を連結して1件に
        merged = self._merge_by_scope(candidates)
        # 重要度でソート（high > medium > low）、件数上限
        merged.sort(key=lambda e: (0 if e.importance == "high" else 1 if e.importance == "medium" else 2, e.context_summary))
        return merged[: self._max_candidates]

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

    def _compute_importance(
        self,
        has_breaks_movement: bool,
        has_stable_id: bool,
        has_strong_result: bool,
        result_summary: str,
    ) -> str:
        """MMO 的優先度に合わせた importance を返す。"""
        if has_breaks_movement:
            return "high"
        if has_strong_result and self._is_combat_or_death_result(result_summary):
            return "high"
        if has_stable_id or has_strong_result:
            return "medium"
        return "low"

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
        """structured から world_object_id / spot_id を抽出。formatter の各種 stable id キーをカバー。"""
        world_object_ids: list[int] = []
        spot_id_value: int | None = None
        wo_keys = (
            "world_object_id",
            "owner_world_object_id",
            "target_world_object_id",
            "actor_world_object_id",
            "monster_id_value",
            "npc_id_value",
            "shop_id_value",
            "guild_id_value",
            "quest_id_value",
            "speaker_player_id",
            "killer_player_id",
        )
        for observation in overflow_observations:
            structured = observation.output.structured
            for key in wo_keys:
                val = structured.get(key)
                if val is not None and isinstance(val, int) and val not in world_object_ids:
                    world_object_ids.append(val)
            sp_id = structured.get("spot_id_value")
            if sp_id is not None and isinstance(sp_id, int) and spot_id_value is None:
                spot_id_value = sp_id
        return tuple(world_object_ids), spot_id_value

    def _extract_scope_keys(
        self,
        overflow_observations: List[ObservationEntry],
    ) -> tuple[str, ...]:
        """
        structured から scope_keys を抽出。
        例: quest:12, guild:3, shop:9, conversation:npc:42, conversation:tree:5
        """
        seen: set[str] = set()
        keys: list[str] = []

        def add(key: str) -> None:
            if key and key not in seen:
                seen.add(key)
                keys.append(key)

        for observation in overflow_observations:
            structured = observation.output.structured
            obs_type = structured.get("type")
            if obs_type in (
                "quest_issued", "quest_accepted", "quest_completed",
                "quest_pending_approval", "quest_approved", "quest_cancelled",
            ):
                qid = structured.get("quest_id_value")
                if isinstance(qid, int):
                    add(f"quest:{qid}")
            if obs_type in (
                "guild_created", "guild_member_joined", "guild_member_left",
                "guild_role_changed", "guild_bank_deposited", "guild_bank_withdrawn",
                "guild_disbanded",
            ):
                gid = structured.get("guild_id_value")
                if isinstance(gid, int):
                    add(f"guild:{gid}")
            if obs_type in (
                "shop_created", "shop_item_listed", "shop_item_unlisted",
                "shop_purchase", "shop_closed",
            ):
                sid = structured.get("shop_id_value")
                if isinstance(sid, int):
                    add(f"shop:{sid}")
            if obs_type in (
                "trade_offered", "trade_accepted", "trade_cancelled",
            ):
                tid = structured.get("trade_id_value")
                if isinstance(tid, int):
                    add(f"trade:{tid}")
            if obs_type in ("conversation_started", "conversation_ended"):
                nid = structured.get("npc_id_value")
                if isinstance(nid, int):
                    add(f"conversation:npc:{nid}")
                tid = structured.get("dialogue_tree_id_value")
                if isinstance(tid, int):
                    add(f"conversation:tree:{tid}")

        return tuple(keys)

    def _merge_by_scope(
        self, candidates: list[EpisodeMemoryEntry]
    ) -> list[EpisodeMemoryEntry]:
        """
        scope_keys 単位でマージ。同じ scope_keys の候補は context を連結して1件にする。
        重複除去も兼ねる。
        """
        from collections import defaultdict

        groups: dict[frozenset[str], list[EpisodeMemoryEntry]] = defaultdict(list)
        for c in candidates:
            key = frozenset(c.scope_keys) if c.scope_keys else frozenset({"_no_scope_"})
            groups[key].append(c)

        result: list[EpisodeMemoryEntry] = []
        for scope_key, entries in groups.items():
            if scope_key == frozenset({"_no_scope_"}):
                # scope のない候補は1件にマージ（従来の統合挙動）
                if len(entries) == 1:
                    result.append(entries[0])
                else:
                    best = max(entries, key=lambda e: 2 if e.importance == "high" else 1 if e.importance == "medium" else 0)
                    combined = " ".join(e.context_summary for e in entries if e.context_summary).strip()
                    all_wo = list(dict.fromkeys(w for e in entries for w in e.world_object_ids))
                    sp_val = next((e.spot_id_value for e in entries if e.spot_id_value is not None), None)
                    all_ent = list(dict.fromkeys(x for e in entries for x in e.entity_ids))
                    loc_id = next((e.location_id for e in entries if e.location_id is not None), None)
                    result.append(
                        EpisodeMemoryEntry(
                            id=best.id,
                            context_summary=combined or best.context_summary,
                            action_taken=best.action_taken,
                            outcome_summary=best.outcome_summary,
                            entity_ids=tuple(all_ent),
                            location_id=loc_id,
                            timestamp=best.timestamp,
                            importance=best.importance,
                            surprise=best.surprise,
                            recall_count=best.recall_count,
                            world_object_ids=tuple(all_wo),
                            spot_id_value=sp_val,
                            scope_keys=(),
                        )
                    )
            else:
                # 同一 scope は1件にマージ（最高重要度、context 連結）
                entries_sorted = sorted(
                    entries,
                    key=lambda e: (0 if e.importance == "high" else 1 if e.importance == "medium" else 2),
                )
                best = entries_sorted[0]
                contexts = [e.context_summary for e in entries if e.context_summary]
                combined = " ".join(contexts).strip() if contexts else best.context_summary
                all_wo: list[int] = []
                for e in entries:
                    for w in e.world_object_ids:
                        if w not in all_wo:
                            all_wo.append(w)
                sp_val: int | None = next(
                    (e.spot_id_value for e in entries if e.spot_id_value is not None),
                    None,
                )
                all_ent: list[str] = []
                for e in entries:
                    for x in e.entity_ids:
                        if x not in all_ent:
                            all_ent.append(x)
                loc_id: str | None = next(
                    (e.location_id for e in entries if e.location_id is not None),
                    None,
                )
                result.append(
                    EpisodeMemoryEntry(
                        id=best.id,
                        context_summary=combined,
                        action_taken=best.action_taken,
                        outcome_summary=best.outcome_summary,
                        entity_ids=tuple(all_ent),
                        location_id=loc_id,
                        timestamp=best.timestamp,
                        importance=best.importance,
                        surprise=best.surprise,
                        recall_count=best.recall_count,
                        world_object_ids=tuple(all_wo),
                        spot_id_value=sp_val,
                        scope_keys=best.scope_keys,
                    )
                )
        return result
