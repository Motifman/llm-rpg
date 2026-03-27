"""Helpers for normalized dialogue tree persistence."""

from __future__ import annotations

from typing import Iterable

from ai_rpg_world.domain.conversation.value_object.dialogue_node import DialogueNode


def build_dialogue_node(
    *,
    row: object,
    choice_rows: Iterable[tuple[str, int]],
    reward_item_rows: Iterable[tuple[int, int]],
    unlock_rows: Iterable[int],
    completion_rows: Iterable[int],
) -> DialogueNode:
    return DialogueNode(
        node_id=int(row["node_id"]),
        text=row["text"],
        choices=tuple(choice_rows),
        next_node_id=row["next_node_id"],
        is_terminal=bool(row["is_terminal"]),
        reward_gold=int(row["reward_gold"]),
        reward_items=tuple(reward_item_rows),
        quest_unlock_ids=tuple(unlock_rows),
        quest_complete_quest_ids=tuple(completion_rows),
    )

