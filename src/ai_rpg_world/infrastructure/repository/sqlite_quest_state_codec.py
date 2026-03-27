"""Helpers for normalized quest aggregate persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.quest.aggregate.quest_aggregate import QuestAggregate
from ai_rpg_world.domain.quest.enum.quest_enum import QuestObjectiveType, QuestScopeType, QuestStatus
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.quest.value_object.quest_objective import QuestObjective
from ai_rpg_world.domain.quest.value_object.quest_reward import QuestReward
from ai_rpg_world.domain.quest.value_object.quest_scope import QuestScope


def build_quest(
    *,
    row: object,
    objective_rows: Iterable[tuple[str, int, int, int, int | None]],
    reward_rows: Iterable[tuple[int, int]],
    reserved_item_rows: Iterable[int],
) -> QuestAggregate:
    objectives = [
        QuestObjective(
            objective_type=QuestObjectiveType(objective_type),
            target_id=target_id,
            required_count=required_count,
            current_count=current_count,
            target_id_secondary=target_id_secondary,
        )
        for objective_type, target_id, required_count, current_count, target_id_secondary in objective_rows
    ]
    reward = QuestReward.of(
        gold=int(row["reward_gold"]),
        exp=int(row["reward_exp"]),
        item_rewards=[(ItemSpecId(item_spec_id), quantity) for item_spec_id, quantity in reward_rows],
    )
    scope_type = QuestScopeType(row["scope_type"])
    if scope_type == QuestScopeType.PUBLIC:
        scope = QuestScope.public_scope()
    elif scope_type == QuestScopeType.DIRECT:
        scope = QuestScope.direct_scope(PlayerId(int(row["scope_target_player_id"])))
    else:
        scope = QuestScope.guild_scope(int(row["scope_guild_id"]))
    issuer_player_id = row["issuer_player_id"]
    acceptor_player_id = row["acceptor_player_id"]
    return QuestAggregate(
        quest_id=QuestId(int(row["quest_id"])),
        status=QuestStatus(row["status"]),
        objectives=objectives,
        reward=reward,
        scope=scope,
        issuer_player_id=None if issuer_player_id is None else PlayerId(int(issuer_player_id)),
        guild_id=row["guild_id"],
        acceptor_player_id=None if acceptor_player_id is None else PlayerId(int(acceptor_player_id)),
        reserved_gold=int(row["reserved_gold"]),
        reserved_item_instance_ids=tuple(ItemInstanceId(item_id) for item_id in reserved_item_rows),
        version=int(row["version"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )

