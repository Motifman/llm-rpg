"""SQLite implementation of dialogue tree read repository and writer."""

from __future__ import annotations

import sqlite3
from typing import Dict, Optional

from ai_rpg_world.domain.conversation.repository.dialogue_tree_repository import (
    DialogueTreeRepository,
)
from ai_rpg_world.domain.conversation.value_object.dialogue_node import DialogueNode
from ai_rpg_world.domain.conversation.value_object.dialogue_node_id import DialogueNodeId
from ai_rpg_world.domain.conversation.value_object.dialogue_tree_id import DialogueTreeId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_dialogue_tree_state_codec import (
    build_dialogue_node,
)


class SqliteDialogueTreeRepository(DialogueTreeRepository):
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_connection(cls, connection: sqlite3.Connection) -> "SqliteDialogueTreeRepository":
        return cls(connection)

    def get_entry_node_id(self, tree_id: DialogueTreeId) -> Optional[DialogueNodeId]:
        cur = self._conn.execute(
            "SELECT entry_node_id FROM game_dialogue_trees WHERE tree_id = ?",
            (int(tree_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return DialogueNodeId(int(row["entry_node_id"]))

    def get_node(
        self, tree_id: DialogueTreeId, node_id: DialogueNodeId
    ) -> Optional[DialogueNode]:
        cur = self._conn.execute(
            """
            SELECT *
            FROM game_dialogue_tree_nodes
            WHERE tree_id = ? AND node_id = ?
            """,
            (int(tree_id), int(node_id)),
        )
        row = cur.fetchone()
        if row is None:
            return None
        choice_rows = self._conn.execute(
            """
            SELECT label, next_node_id
            FROM game_dialogue_node_choices
            WHERE tree_id = ? AND node_id = ?
            ORDER BY choice_index ASC
            """,
            (int(tree_id), int(node_id)),
        ).fetchall()
        reward_rows = self._conn.execute(
            """
            SELECT item_spec_id, quantity
            FROM game_dialogue_node_reward_items
            WHERE tree_id = ? AND node_id = ?
            ORDER BY reward_index ASC
            """,
            (int(tree_id), int(node_id)),
        ).fetchall()
        unlock_rows = self._conn.execute(
            """
            SELECT quest_id
            FROM game_dialogue_node_quest_unlocks
            WHERE tree_id = ? AND node_id = ?
            ORDER BY quest_index ASC
            """,
            (int(tree_id), int(node_id)),
        ).fetchall()
        completion_rows = self._conn.execute(
            """
            SELECT quest_id
            FROM game_dialogue_node_quest_completions
            WHERE tree_id = ? AND node_id = ?
            ORDER BY quest_index ASC
            """,
            (int(tree_id), int(node_id)),
        ).fetchall()
        return build_dialogue_node(
            row=row,
            choice_rows=[(choice_row["label"], int(choice_row["next_node_id"])) for choice_row in choice_rows],
            reward_item_rows=[
                (int(reward_row["item_spec_id"]), int(reward_row["quantity"]))
                for reward_row in reward_rows
            ],
            unlock_rows=[int(unlock_row["quest_id"]) for unlock_row in unlock_rows],
            completion_rows=[int(completion_row["quest_id"]) for completion_row in completion_rows],
        )


class SqliteDialogueTreeWriter:
    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> "SqliteDialogueTreeWriter":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(cls, connection: sqlite3.Connection) -> "SqliteDialogueTreeWriter":
        return cls(connection, _commits_after_write=False)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def _assert_shared_transaction_active(self) -> None:
        if self._commits_after_write:
            return
        if not self._conn.in_transaction:
            raise RuntimeError(
                "for_shared_unit_of_work で生成した writer の書き込みは、"
                "アクティブなトランザクション内（with uow）で実行してください"
            )

    def replace_tree(
        self,
        tree_id: DialogueTreeId,
        entry_node_id: DialogueNodeId,
        nodes: Dict[int, DialogueNode],
    ) -> None:
        self._assert_shared_transaction_active()
        self._conn.execute(
            """
            INSERT INTO game_dialogue_trees (tree_id, entry_node_id)
            VALUES (?, ?)
            ON CONFLICT(tree_id) DO UPDATE SET
                entry_node_id = excluded.entry_node_id
            """,
            (int(tree_id), int(entry_node_id)),
        )
        for table_name in (
            "game_dialogue_tree_nodes",
            "game_dialogue_node_choices",
            "game_dialogue_node_reward_items",
            "game_dialogue_node_quest_unlocks",
            "game_dialogue_node_quest_completions",
        ):
            self._conn.execute(f"DELETE FROM {table_name} WHERE tree_id = ?", (int(tree_id),))
        self._conn.executemany(
            """
            INSERT INTO game_dialogue_tree_nodes (
                tree_id, node_id, text, next_node_id, is_terminal, reward_gold
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(tree_id),
                    int(node_id),
                    node.text,
                    node.next_node_id,
                    int(node.is_terminal),
                    node.reward_gold,
                )
                for node_id, node in sorted(nodes.items())
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_dialogue_node_choices (
                tree_id, node_id, choice_index, label, next_node_id
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (int(tree_id), int(node_id), choice_index, label, next_node_id)
                for node_id, node in sorted(nodes.items())
                for choice_index, (label, next_node_id) in enumerate(node.choices)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_dialogue_node_reward_items (
                tree_id, node_id, reward_index, item_spec_id, quantity
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (int(tree_id), int(node_id), reward_index, item_spec_id, quantity)
                for node_id, node in sorted(nodes.items())
                for reward_index, (item_spec_id, quantity) in enumerate(node.reward_items)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_dialogue_node_quest_unlocks (
                tree_id, node_id, quest_index, quest_id
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (int(tree_id), int(node_id), quest_index, quest_id)
                for node_id, node in sorted(nodes.items())
                for quest_index, quest_id in enumerate(node.quest_unlock_ids)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_dialogue_node_quest_completions (
                tree_id, node_id, quest_index, quest_id
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (int(tree_id), int(node_id), quest_index, quest_id)
                for node_id, node in sorted(nodes.items())
                for quest_index, quest_id in enumerate(node.quest_complete_quest_ids)
            ],
        )
        self._finalize_write()


__all__ = ["SqliteDialogueTreeRepository", "SqliteDialogueTreeWriter"]
